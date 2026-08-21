import type Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import * as svc from "../domain/service.js";
import * as absence from "../domain/absence.js";
import { today } from "../db/index.js";
import { PRIORITIES, STEP_STATUSES, TASK_STATUSES } from "../domain/types.js";
import type { Task, TaskProgress } from "../domain/types.js";

/** 도구를 실행하는 사람의 정보 (이력의 actor, '내 업무'의 기준) */
export interface ToolContext {
  /** 말을 건 사람 이름 (Teams 표시 이름 등) */
  user: string;
  /** '내 업무' 조회 기본 담당자 */
  owner: string;
  /** 이번 대화에서 조회된 담당자들 — 부재 중인 사람이면 질문을 기록해 둔다 */
  touchedOwners: Set<string>;
}

interface ToolDef<S extends z.ZodType> {
  name: string;
  description: string;
  schema: S;
  run: (input: z.infer<S>, ctx: ToolContext) => unknown;
}

function defineTool<S extends z.ZodType>(t: ToolDef<S>): ToolDef<S> {
  return t;
}

/* ------------------------------------------------------------------ */
/* 응답 포맷 – Claude 가 그대로 읽고 요약하기 좋은 한국어 키              */
/* ------------------------------------------------------------------ */

function formatProgress(p: TaskProgress, ctx?: ToolContext) {
  if (p.task.owner) ctx?.touchedOwners.add(p.task.owner);
  return {
    담당자부재: absence.absenceInfo(p.task.owner),
    번호: p.task.id,
    코드: p.task.code,
    제목: p.task.title,
    플로우: p.templateName,
    담당자: p.task.owner,
    요청자: p.task.requester,
    우선순위: p.task.priority,
    업무상태: p.task.status,
    마감일: p.task.due_date,
    남은일수: p.daysLeft,
    지연여부: p.overdue,
    진행률: `${p.doneCount}/${p.totalCount} (${p.percent}%)`,
    현재단계: p.currentStep ? `${p.currentStep.seq}. ${p.currentStep.name} [${p.currentStep.status}]` : "없음(완료)",
    단계: p.steps.map((s) => ({
      순번: s.seq,
      단계명: s.name,
      상태: s.status,
      담당: s.assignee,
      목표일: s.due_date,
      착수: s.started_at,
      완료: s.completed_at,
      메모: s.note,
    })),
    최근이력: p.recentEvents.map((e) => `${e.created_at} [${e.actor ?? "-"}] ${e.message}`),
  };
}

function formatTaskRow(t: Task & { percent: number; currentStepName: string | null }, ctx?: ToolContext) {
  if (t.owner) ctx?.touchedOwners.add(t.owner);
  return {
    번호: t.id,
    코드: t.code,
    제목: t.title,
    업무상태: t.status,
    현재단계: t.currentStepName,
    진행률: `${t.percent}%`,
    마감일: t.due_date,
    지연여부: Boolean(t.due_date && t.due_date < today() && t.status === "진행중"),
    담당자: t.owner,
    담당자부재: absence.absenceInfo(t.owner) ? "부재 중" : null,
    우선순위: t.priority,
  };
}

/** 업무 한 건을 특정한다. 후보가 여러 개면 되묻도록 후보 목록을 돌려준다. */
function resolveOne(query: string): { task: Task } | { 후보: unknown[]; 안내: string } {
  const found = svc.resolveTasks(query);
  if (found.length === 1) return { task: found[0]! };
  if (found.length === 0) {
    return { 후보: [], 안내: `'${query}' 와 일치하는 업무가 없습니다. list_tasks 로 목록을 확인하세요.` };
  }
  return {
    후보: found.map((t) => ({ 번호: t.id, 코드: t.code, 제목: t.title, 업무상태: t.status })),
    안내: "업무가 여러 건 검색되었습니다. 사용자에게 어느 건인지 되물어보세요.",
  };
}

/* ------------------------------------------------------------------ */
/* 도구 정의                                                            */
/* ------------------------------------------------------------------ */

const taskQuery = z.string().describe("업무 번호, 코드(CT-2026-014 등) 또는 제목 일부");

export const TOOLS = [
  defineTool({
    name: "get_work_summary",
    description:
      "오늘 기준 전체 현황 요약. 진행중/보류/완료/지연 건수, 오늘·이번주 마감, 지금 손대야 할 업무 목록을 한 번에 준다. " +
      "'오늘 뭐 있어?', '나 뭐 해야 돼?', '현황 알려줘' 같은 포괄적 질문에 가장 먼저 쓴다.",
    schema: z.object({
      owner: z.string().optional().describe("담당자 이름. 비우면 대화 중인 사용자 기준"),
    }),
    run: (input, ctx) => {
      const owner = input.owner ?? ctx.owner;
      if (owner) ctx.touchedOwners.add(owner);
      return {
        ...svc.workSummary(owner),
        담당자부재: absence.absenceInfo(owner),
        부재중_다른_담당자: absence.listActiveAbsences().filter((a) => a.person !== owner).map(absence.describeAbsence),
      };
    },
  }),

  defineTool({
    name: "list_tasks",
    description: "조건에 맞는 업무 목록을 조회한다. 특정 업무의 상세 플로우가 필요하면 get_task_progress 를 쓴다.",
    schema: z.object({
      owner: z.string().optional().describe("담당자. 비우면 대화 중인 사용자 기준. 전체를 보려면 '전체' 입력"),
      status: z.enum(TASK_STATUSES).optional().describe("업무 상태 필터"),
      keyword: z.string().optional().describe("제목/코드 검색어"),
      overdue_only: z.boolean().optional().describe("true 면 마감이 지난 진행중 건만"),
      due_within_days: z.number().int().optional().describe("N일 이내 마감인 진행중 건만 (오늘=0, 이번주=7)"),
      limit: z.number().int().min(1).max(50).optional(),
    }),
    run: (input, ctx) => {
      const owner = input.owner === "전체" ? undefined : (input.owner ?? ctx.owner);
      const rows = svc.listTasks({
        owner: owner || undefined,
        status: input.status,
        keyword: input.keyword,
        overdueOnly: input.overdue_only,
        dueWithinDays: input.due_within_days,
        limit: input.limit,
      });
      return { 건수: rows.length, 목록: rows.map((row) => formatTaskRow(row, ctx)) };
    },
  }),

  defineTool({
    name: "get_task_progress",
    description:
      "업무 한 건이 플로우의 어느 단계까지 갔는지 상세 조회. 전체 단계 목록, 현재 멈춰 있는 단계, 진행률, 지연 여부, 최근 이력을 준다. " +
      "'OO건 어디까지 갔어?' 같은 질문의 기본 도구.",
    schema: z.object({ task_query: taskQuery }),
    run: (input, ctx) => {
      const r = resolveOne(input.task_query);
      if (!("task" in r)) return r;
      return formatProgress(svc.getTaskProgress(r.task.id)!, ctx);
    },
  }),

  defineTool({
    name: "get_recent_activity",
    description:
      "지정한 시점 이후에 업무에 생긴 변경 이력을 시간순으로 준다. " +
      "'내가 퇴근한 뒤에 뭐 바뀌었어?', '어제 이후로 진행된 거 있어?' 같은 질문에 쓴다.",
    schema: z.object({
      since_hours: z.number().int().min(1).max(720).optional().describe("최근 N시간 (예: 퇴근 후 = 6)"),
      since: z.string().optional().describe("기준 시각 'YYYY-MM-DD' 또는 'YYYY-MM-DD HH:MM:SS'. 비우면 오늘 0시"),
      owner: z.string().optional().describe("담당자 기준 필터. 비우면 대화 중인 사용자 기준"),
      task_query: z.string().optional().describe("특정 업무로 한정할 때"),
      limit: z.number().int().min(1).max(100).optional(),
    }),
    run: (input, ctx) => {
      let taskId: number | undefined;
      if (input.task_query) {
        const r = resolveOne(input.task_query);
        if (!("task" in r)) return r;
        taskId = r.task.id;
      }
      const events = svc.recentActivity({
        sinceHours: input.since_hours,
        since: input.since ? (input.since.length === 10 ? `${input.since} 00:00:00` : input.since) : undefined,
        owner: input.owner === "전체" ? undefined : (input.owner ?? ctx.owner),
        taskId,
        limit: input.limit,
      });
      return {
        건수: events.length,
        이력: events.map((e) => ({
          시각: e.created_at,
          업무: `${e.task_code ?? e.task_id} ${e.task_title}`,
          변경자: e.actor,
          종류: e.kind,
          내용: e.message,
        })),
      };
    },
  }),

  defineTool({
    name: "list_flow_templates",
    description: "등록된 업무 유형별 표준 플로우(단계 정의) 목록. 새 업무를 만들 때 어떤 플로우가 있는지 확인용.",
    schema: z.object({}),
    run: () =>
      svc.listFlowTemplates().map((t) => ({
        플로우: t.name,
        설명: t.description,
        단계: t.steps.map((s) => `${s.seq}. ${s.name}${s.owner_role ? ` (${s.owner_role}, 표준 ${s.sla_days}일)` : ""}`),
      })),
  }),

  defineTool({
    name: "create_task",
    description: "새 업무를 등록한다. template_name 을 주면 그 플로우의 단계가 자동 생성되고 1단계가 착수 상태가 된다.",
    schema: z.object({
      title: z.string().describe("업무 제목"),
      template_name: z.string().optional().describe("표준 플로우 이름 (list_flow_templates 참고)"),
      steps: z.array(z.string()).optional().describe("템플릿 대신 직접 지정할 단계 이름 목록"),
      code: z.string().optional().describe("업무 코드 (예: CT-2026-016)"),
      owner: z.string().optional(),
      requester: z.string().optional().describe("요청자 또는 요청 부서"),
      priority: z.enum(PRIORITIES).optional(),
      due_date: z.string().optional().describe("마감일 YYYY-MM-DD"),
    }),
    run: (input, ctx) =>
      formatProgress(
        svc.createTask({
          title: input.title,
          templateName: input.template_name,
          steps: input.steps,
          code: input.code,
          owner: input.owner ?? ctx.owner,
          requester: input.requester,
          priority: input.priority,
          dueDate: input.due_date,
          actor: ctx.user,
        }),
        ctx,
      ),
  }),

  defineTool({
    name: "update_step_status",
    description:
      "업무의 특정 단계 상태를 바꾼다. '완료' 로 바꾸면 다음 대기 단계가 자동으로 진행중이 되고, 모든 단계가 끝나면 업무도 완료된다.",
    schema: z.object({
      task_query: taskQuery,
      step: z.union([z.number().int(), z.string()]).describe("단계 순번(숫자) 또는 단계 이름"),
      status: z.enum(STEP_STATUSES),
      note: z.string().optional().describe("메모 (보류 사유 등)"),
      assignee: z.string().optional().describe("이 단계 담당자"),
    }),
    run: (input, ctx) => {
      const r = resolveOne(input.task_query);
      if (!("task" in r)) return r;
      return formatProgress(
        svc.setStepStatus({
          taskId: r.task.id,
          step: input.step,
          status: input.status,
          note: input.note,
          assignee: input.assignee,
          actor: ctx.user,
        }),
        ctx,
      );
    },
  }),

  defineTool({
    name: "update_task_status",
    description: "업무 전체의 상태를 바꾼다 (진행중/완료/보류/취소).",
    schema: z.object({
      task_query: taskQuery,
      status: z.enum(TASK_STATUSES),
      note: z.string().optional(),
    }),
    run: (input, ctx) => {
      const r = resolveOne(input.task_query);
      if (!("task" in r)) return r;
      return formatProgress(svc.setTaskStatus(r.task.id, input.status, input.note, ctx.user), ctx);
    },
  }),

  defineTool({
    name: "add_note",
    description: "업무에 메모를 남긴다. 상태 변경 없이 기록만 남길 때 사용.",
    schema: z.object({ task_query: taskQuery, message: z.string() }),
    run: (input, ctx) => {
      const r = resolveOne(input.task_query);
      if (!("task" in r)) return r;
      const e = svc.addNote(r.task.id, input.message, ctx.user);
      return { 결과: "메모 등록됨", 시각: e.created_at, 업무: r.task.title, 내용: e.message };
    },
  }),

  defineTool({
    name: "set_absence",
    description:
      "사용자가 자리를 비운다고 알릴 때 부재를 등록한다. ('나 지금 조기 퇴근', '1시간 자리 비울게', '3시부터 외근') " +
      "등록해 두면 그동안 다른 사람이 이 사람 업무를 물어봤을 때 봇이 복귀 예정 시각과 인수인계 메모까지 대신 안내한다.",
    schema: z.object({
      person: z.string().optional().describe("자리를 비우는 사람. 비우면 대화 중인 사용자"),
      minutes: z.number().int().min(5).max(1440).optional().describe("몇 분 뒤 복귀 예정인지 (1시간 = 60)"),
      until: z.string().optional().describe("복귀 예정 시각 'YYYY-MM-DD HH:MM'. minutes 대신 쓸 수 있다"),
      reason: z.string().optional().describe("사유 (조기 퇴근, 외근, 회의 등)"),
      note: z.string().optional().describe("인수인계 메모. 부재 중 질문에 그대로 안내된다"),
      contactable: z.boolean().optional().describe("급한 건은 연락 가능한지"),
    }),
    run: (input, ctx) => {
      const person = input.person ?? ctx.user;
      const a = absence.startAbsence({
        person,
        minutes: input.minutes,
        until: input.until,
        reason: input.reason,
        note: input.note,
        contactable: input.contactable,
      });
      return {
        결과: "부재 등록됨. 이제 다른 사람이 물어보면 대신 안내합니다.",
        ...absence.describeAbsence(a),
        현재_진행중_업무: svc.listTasks({ owner: person, status: "진행중", limit: 20 }).map((t) => ({
          제목: t.title,
          현재단계: t.currentStepName,
          마감일: t.due_date,
        })),
      };
    },
  }),

  defineTool({
    name: "end_absence",
    description:
      "복귀했을 때 부재를 해제한다. 자리를 비운 사이 다른 사람이 물어본 질문 목록을 함께 돌려주므로, 복귀 브리핑에 그대로 쓴다.",
    schema: z.object({ person: z.string().optional().describe("복귀한 사람. 비우면 대화 중인 사용자") }),
    run: (input, ctx) => {
      const person = input.person ?? ctx.user;
      const { absence: ended, inquiries } = absence.endAbsence(person);
      absence.markInquiriesSeen(person);
      return {
        결과: ended ? "복귀 처리했습니다." : "등록된 부재가 없었습니다.",
        자리비운시각: ended?.started_at ?? null,
        부재중_받은_질문수: inquiries.length,
        부재중_받은_질문: inquiries.map((q) => ({
          시각: q.created_at,
          질문자: q.asker,
          질문: q.question,
          대신_답한_내용: q.answer,
        })),
      };
    },
  }),

  defineTool({
    name: "get_absence_status",
    description:
      "특정 담당자가 지금 자리에 있는지, 없다면 언제 복귀 예정인지 확인한다. person 을 비우면 부재 중인 사람 전체를 준다. " +
      "다른 사람이 '○○님 지금 계세요?' 라고 물을 때 사용.",
    schema: z.object({ person: z.string().optional().describe("확인할 담당자. 비우면 부재 중인 사람 전체") }),
    run: (input) => {
      if (input.person) {
        const a = absence.getActiveAbsence(input.person);
        return a
          ? absence.describeAbsence(a)
          : { 부재중: false, 담당자: input.person, 안내: "부재 등록이 없습니다. 자리에 있는 것으로 봅니다." };
      }
      const all = absence.listActiveAbsences();
      return { 부재중_인원: all.length, 목록: all.map(absence.describeAbsence) };
    },
  }),

  defineTool({
    name: "list_inquiries",
    description:
      "자리를 비운 사이 다른 사람이 봇에게 물어본 내용을 시간순으로 준다. " +
      "'내가 없는 동안 누가 뭐 물어봤어?' 에 답할 때 사용. 복귀 처리는 end_absence 가 한다.",
    schema: z.object({
      person: z.string().optional().describe("누구 업무에 대한 질문인지. 비우면 대화 중인 사용자"),
      only_unseen: z.boolean().optional().describe("아직 확인하지 않은 질문만 (기본 false)"),
      since_hours: z.number().int().min(1).max(720).optional(),
      limit: z.number().int().min(1).max(100).optional(),
    }),
    run: (input, ctx) => {
      const person = input.person ?? ctx.owner ?? ctx.user;
      const rows = absence.listInquiries({
        person,
        onlyUnseen: input.only_unseen,
        sinceHours: input.since_hours,
        limit: input.limit,
      });
      return {
        건수: rows.length,
        질문: rows.map((q) => ({
          시각: q.created_at,
          질문자: q.asker,
          질문: q.question,
          대신_답한_내용: q.answer,
          확인함: Boolean(q.seen),
        })),
      };
    },
  }),
] as const;

/** 데이터를 바꾸는 도구 – 응답에 무엇을 바꿨는지 반드시 밝히도록 시스템 프롬프트에서 사용 */
export const WRITE_TOOLS = new Set([
  "create_task",
  "update_step_status",
  "update_task_status",
  "add_note",
  "set_absence",
  "end_absence",
]);

/** 스키마 타입을 지운 목록 – 런타임 조회/검증용 */
const TOOL_LIST = TOOLS as readonly ToolDef<z.ZodType>[];

function toJsonSchema(schema: z.ZodType): Record<string, unknown> {
  const json = z.toJSONSchema(schema, { io: "input" }) as Record<string, unknown>;
  delete json.$schema;
  return json;
}

/** Claude 에 넘길 도구 정의 (순서 고정 – 프롬프트 캐시 유지) */
export const TOOL_SPECS: Anthropic.Beta.BetaTool[] = TOOL_LIST.map((t) => ({
  name: t.name,
  description: t.description,
  input_schema: toJsonSchema(t.schema) as Anthropic.Beta.BetaTool["input_schema"],
}));

/** 도구 실행. 실패는 던지지 않고 오류 문자열로 돌려줘 대화가 이어지게 한다. */
export function executeTool(name: string, rawInput: unknown, ctx: ToolContext): { content: string; isError: boolean } {
  const tool = TOOL_LIST.find((t) => t.name === name);
  if (!tool) return { content: `알 수 없는 도구: ${name}`, isError: true };

  const parsed = tool.schema.safeParse(rawInput ?? {});
  if (!parsed.success) {
    const detail = parsed.error.issues.map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`).join(", ");
    return { content: `입력값 오류 – ${detail}`, isError: true };
  }

  try {
    const result = tool.run(parsed.data, ctx);
    return { content: JSON.stringify(result, null, 1), isError: false };
  } catch (err) {
    return { content: `실행 실패: ${err instanceof Error ? err.message : String(err)}`, isError: true };
  }
}
