import { getDb, now, today } from "../db/index.js";
import type {
  FlowTemplate,
  FlowTemplateStep,
  Priority,
  StepStatus,
  Task,
  TaskEvent,
  TaskProgress,
  TaskStatus,
  TaskStep,
} from "./types.js";

/* ------------------------------------------------------------------ */
/* 날짜 유틸                                                            */
/* ------------------------------------------------------------------ */

function addDays(date: string, days: number): string {
  const d = new Date(`${date}T00:00:00`);
  d.setDate(d.getDate() + days);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function diffDays(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00`).getTime();
  const b = new Date(`${to}T00:00:00`).getTime();
  return Math.round((b - a) / 86_400_000);
}

/* ------------------------------------------------------------------ */
/* 플로우 템플릿                                                        */
/* ------------------------------------------------------------------ */

export function listFlowTemplates(): Array<FlowTemplate & { steps: FlowTemplateStep[] }> {
  const db = getDb();
  const templates = db.prepare<[], FlowTemplate>("SELECT id, name, description FROM flow_templates ORDER BY id").all();
  const stepsStmt = db.prepare<[number], FlowTemplateStep>(
    "SELECT * FROM flow_template_steps WHERE template_id = ? ORDER BY seq",
  );
  return templates.map((t) => ({ ...t, steps: stepsStmt.all(t.id) }));
}

export function findTemplateByName(name: string): FlowTemplate | undefined {
  const db = getDb();
  return (
    db.prepare<[string], FlowTemplate>("SELECT id, name, description FROM flow_templates WHERE name = ?").get(name) ??
    db
      .prepare<[string], FlowTemplate>(
        "SELECT id, name, description FROM flow_templates WHERE name LIKE ? ORDER BY length(name) LIMIT 1",
      )
      .get(`%${name}%`)
  );
}

/* ------------------------------------------------------------------ */
/* 이력                                                                */
/* ------------------------------------------------------------------ */

function logEvent(taskId: number, kind: string, message: string, actor?: string | null, stepId?: number | null): void {
  getDb()
    .prepare("INSERT INTO task_events (task_id, step_id, actor, kind, message, created_at) VALUES (?, ?, ?, ?, ?, ?)")
    .run(taskId, stepId ?? null, actor ?? null, kind, message, now());
}

/* ------------------------------------------------------------------ */
/* 업무 조회                                                            */
/* ------------------------------------------------------------------ */

export function getTask(id: number): Task | undefined {
  return getDb().prepare<[number], Task>("SELECT * FROM tasks WHERE id = ?").get(id);
}

/**
 * 사람이 말하는 표현("계약검토 건", "CT-2026-014", "3번")으로 업무를 찾는다.
 * 정확히 하나로 좁혀지지 않으면 후보 목록을 돌려준다.
 */
export function resolveTasks(query: string, limit = 8): Task[] {
  const db = getDb();
  const q = query.trim();
  if (!q) return [];

  const exact = db
    .prepare<[string, string], Task>("SELECT * FROM tasks WHERE code = ? COLLATE NOCASE OR title = ? COLLATE NOCASE")
    .all(q, q);
  if (exact.length) return exact;

  if (/^\d+$/.test(q)) {
    const byId = getTask(Number(q));
    if (byId) return [byId];
  }

  // 공백/특수문자를 무시한 부분 일치 (예: "계약 검토" -> "신규 계약 검토")
  const like = `%${q.replace(/\s+/g, "%")}%`;
  return db
    .prepare<[string, string, number], Task>(
      `SELECT * FROM tasks
        WHERE title LIKE ? OR code LIKE ?
        ORDER BY CASE status WHEN '진행중' THEN 0 WHEN '보류' THEN 1 ELSE 2 END, updated_at DESC
        LIMIT ?`,
    )
    .all(like, like, limit);
}

export interface ListTasksFilter {
  owner?: string;
  status?: TaskStatus;
  keyword?: string;
  overdueOnly?: boolean;
  dueWithinDays?: number;
  limit?: number;
}

export function listTasks(filter: ListTasksFilter = {}): Array<Task & { percent: number; currentStepName: string | null }> {
  const db = getDb();
  const where: string[] = [];
  const params: unknown[] = [];

  if (filter.owner) {
    where.push("(t.owner = ? COLLATE NOCASE OR EXISTS (SELECT 1 FROM task_steps s WHERE s.task_id = t.id AND s.assignee = ? COLLATE NOCASE))");
    params.push(filter.owner, filter.owner);
  }
  if (filter.status) {
    where.push("t.status = ?");
    params.push(filter.status);
  }
  if (filter.keyword) {
    where.push("(t.title LIKE ? OR t.code LIKE ?)");
    const like = `%${filter.keyword.replace(/\s+/g, "%")}%`;
    params.push(like, like);
  }
  if (filter.overdueOnly) {
    where.push("t.due_date IS NOT NULL AND t.due_date < ? AND t.status = '진행중'");
    params.push(today());
  }
  if (typeof filter.dueWithinDays === "number") {
    where.push("t.due_date IS NOT NULL AND t.due_date <= ? AND t.status = '진행중'");
    params.push(addDays(today(), filter.dueWithinDays));
  }

  const sql = `
    SELECT t.* FROM tasks t
    ${where.length ? `WHERE ${where.join(" AND ")}` : ""}
    ORDER BY CASE t.status WHEN '진행중' THEN 0 WHEN '보류' THEN 1 ELSE 2 END,
             CASE t.priority WHEN '높음' THEN 0 WHEN '보통' THEN 1 ELSE 2 END,
             COALESCE(t.due_date, '9999-12-31'), t.id
    LIMIT ?`;
  const rows = db.prepare<unknown[], Task>(sql).all(...params, filter.limit ?? 20);

  return rows.map((t) => {
    const steps = getSteps(t.id);
    return {
      ...t,
      percent: percentOf(steps),
      currentStepName: currentStepOf(steps)?.name ?? null,
    };
  });
}

export function getSteps(taskId: number): TaskStep[] {
  return getDb().prepare<[number], TaskStep>("SELECT * FROM task_steps WHERE task_id = ? ORDER BY seq").all(taskId);
}

function percentOf(steps: TaskStep[]): number {
  const counted = steps.filter((s) => s.status !== "생략");
  if (!counted.length) return 0;
  const done = counted.filter((s) => s.status === "완료").length;
  return Math.round((done / counted.length) * 100);
}

/** 지금 플로우가 멈춰 있는 지점 = 아직 끝나지 않은 가장 앞선 단계 (보류 포함). */
function currentStepOf(steps: TaskStep[]): TaskStep | null {
  return steps.find((s) => s.status !== "완료" && s.status !== "생략") ?? null;
}

export function getTaskProgress(taskId: number, eventLimit = 5): TaskProgress | null {
  const task = getTask(taskId);
  if (!task) return null;
  const db = getDb();
  const steps = getSteps(taskId);
  const counted = steps.filter((s) => s.status !== "생략");
  const templateName = task.template_id
    ? (db.prepare<[number], { name: string }>("SELECT name FROM flow_templates WHERE id = ?").get(task.template_id)?.name ?? null)
    : null;

  return {
    task,
    templateName,
    steps,
    currentStep: currentStepOf(steps),
    doneCount: counted.filter((s) => s.status === "완료").length,
    totalCount: counted.length,
    percent: percentOf(steps),
    overdue: Boolean(task.due_date && task.due_date < today() && task.status === "진행중"),
    daysLeft: task.due_date ? diffDays(today(), task.due_date) : null,
    blockedSteps: steps.filter((s) => s.status === "보류"),
    recentEvents: db
      .prepare<[number, number], TaskEvent>("SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at DESC, id DESC LIMIT ?")
      .all(taskId, eventLimit),
  };
}

/* ------------------------------------------------------------------ */
/* 업무 생성 / 변경                                                     */
/* ------------------------------------------------------------------ */

export interface CreateTaskInput {
  title: string;
  templateName?: string;
  code?: string;
  owner?: string;
  requester?: string;
  priority?: Priority;
  dueDate?: string;
  steps?: string[];
  actor?: string;
}

export function createTask(input: CreateTaskInput): TaskProgress {
  const db = getDb();
  const template = input.templateName ? findTemplateByName(input.templateName) : undefined;
  if (input.templateName && !template) {
    throw new Error(`'${input.templateName}' 이라는 플로우 템플릿이 없습니다. list_flow_templates 로 확인하세요.`);
  }

  const templateSteps = template
    ? db
        .prepare<[number], FlowTemplateStep>("SELECT * FROM flow_template_steps WHERE template_id = ? ORDER BY seq")
        .all(template.id)
    : [];

  const stepNames = input.steps?.length ? input.steps : templateSteps.map((s) => s.name);
  if (!stepNames.length) {
    throw new Error("플로우 단계가 없습니다. template_name 을 지정하거나 steps 를 직접 넘겨주세요.");
  }

  const create = db.transaction(() => {
    const info = db
      .prepare(
        `INSERT INTO tasks (code, title, template_id, owner, requester, priority, due_date, status, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, '진행중', ?, ?)`,
      )
      .run(
        input.code ?? null,
        input.title,
        template?.id ?? null,
        input.owner ?? null,
        input.requester ?? null,
        input.priority ?? "보통",
        input.dueDate ?? null,
        now(),
        now(),
      );
    const taskId = Number(info.lastInsertRowid);

    // 템플릿의 표준 소요일(sla_days)을 누적해 단계별 목표일을 잡는다.
    let cursor = today();
    const insertStep = db.prepare(
      "INSERT INTO task_steps (task_id, seq, name, assignee, status, due_date) VALUES (?, ?, ?, ?, ?, ?)",
    );
    stepNames.forEach((name, i) => {
      const sla = templateSteps[i]?.sla_days ?? null;
      if (sla) cursor = addDays(cursor, sla);
      insertStep.run(taskId, i + 1, name, i === 0 ? (input.owner ?? null) : null, i === 0 ? "진행중" : "대기", sla ? cursor : null);
    });

    logEvent(taskId, "task_created", `업무 등록: ${input.title} (${stepNames.length}단계)`, input.actor);
    return taskId;
  });

  return getTaskProgress(create())!;
}

export interface SetStepStatusInput {
  taskId: number;
  /** 단계 번호(seq) 또는 단계 이름 */
  step: number | string;
  status: StepStatus;
  note?: string;
  assignee?: string;
  actor?: string;
  /** 완료 시 다음 대기 단계를 자동으로 '진행중' 으로 올릴지 (기본 true) */
  autoAdvance?: boolean;
}

export function setStepStatus(input: SetStepStatusInput): TaskProgress {
  const db = getDb();
  const steps = getSteps(input.taskId);
  if (!steps.length) throw new Error(`업무 #${input.taskId} 를 찾을 수 없습니다.`);

  const target =
    typeof input.step === "number"
      ? steps.find((s) => s.seq === input.step)
      : (steps.find((s) => s.name === input.step) ??
        steps.find((s) => s.name.replace(/\s+/g, "").includes(String(input.step).replace(/\s+/g, ""))));
  if (!target) {
    throw new Error(`'${input.step}' 단계를 찾을 수 없습니다. 단계: ${steps.map((s) => `${s.seq}.${s.name}`).join(", ")}`);
  }

  const apply = db.transaction(() => {
    const startedAt = input.status === "대기" ? null : (target.started_at ?? now());
    const completedAt = input.status === "완료" ? (target.completed_at ?? now()) : null;

    db.prepare(
      `UPDATE task_steps
          SET status = ?, started_at = ?, completed_at = ?,
              assignee = COALESCE(?, assignee),
              note = COALESCE(?, note)
        WHERE id = ?`,
    ).run(input.status, startedAt, completedAt, input.assignee ?? null, input.note ?? null, target.id);

    logEvent(
      input.taskId,
      "step_status",
      `${target.seq}단계 '${target.name}' ${target.status} → ${input.status}${input.note ? ` (${input.note})` : ""}`,
      input.actor,
      target.id,
    );

    if (input.status === "완료" && (input.autoAdvance ?? true)) {
      const next = steps.find((s) => s.seq > target.seq && s.status === "대기");
      if (next) {
        db.prepare("UPDATE task_steps SET status = '진행중', started_at = COALESCE(started_at, ?) WHERE id = ?").run(now(), next.id);
        logEvent(input.taskId, "step_status", `${next.seq}단계 '${next.name}' 자동 착수 (대기 → 진행중)`, input.actor, next.id);
      }
    }

    // 모든 단계가 끝나면 업무 자체를 완료 처리
    const after = getSteps(input.taskId).filter((s) => s.status !== "생략");
    if (after.length && after.every((s) => s.status === "완료")) {
      db.prepare("UPDATE tasks SET status = '완료', updated_at = ? WHERE id = ?").run(now(), input.taskId);
      logEvent(input.taskId, "task_status", "모든 단계 완료 → 업무 완료", input.actor);
    } else {
      db.prepare("UPDATE tasks SET updated_at = ? WHERE id = ?").run(now(), input.taskId);
    }
  });

  apply();
  return getTaskProgress(input.taskId)!;
}

export function setTaskStatus(taskId: number, status: TaskStatus, note?: string, actor?: string): TaskProgress {
  const db = getDb();
  const task = getTask(taskId);
  if (!task) throw new Error(`업무 #${taskId} 를 찾을 수 없습니다.`);
  db.prepare("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?").run(status, now(), taskId);
  logEvent(taskId, "task_status", `업무 상태 ${task.status} → ${status}${note ? ` (${note})` : ""}`, actor);
  return getTaskProgress(taskId)!;
}

export function addNote(taskId: number, message: string, actor?: string): TaskEvent {
  const db = getDb();
  if (!getTask(taskId)) throw new Error(`업무 #${taskId} 를 찾을 수 없습니다.`);
  logEvent(taskId, "note", message, actor);
  db.prepare("UPDATE tasks SET updated_at = ? WHERE id = ?").run(now(), taskId);
  return db.prepare<[number], TaskEvent>("SELECT * FROM task_events WHERE task_id = ? ORDER BY id DESC LIMIT 1").get(taskId)!;
}

/* ------------------------------------------------------------------ */
/* 조기 퇴근용: 내가 자리를 비운 사이 무슨 일이 있었나                    */
/* ------------------------------------------------------------------ */

export interface ActivityFilter {
  sinceHours?: number;
  since?: string;
  owner?: string;
  taskId?: number;
  limit?: number;
}

export function recentActivity(filter: ActivityFilter = {}): Array<TaskEvent & { task_title: string; task_code: string | null }> {
  const db = getDb();
  const since =
    filter.since ??
    (filter.sinceHours ? new Date(Date.now() - filter.sinceHours * 3_600_000).toISOString().slice(0, 19).replace("T", " ") : `${today()} 00:00:00`);

  const where = ["e.created_at >= ?"];
  const params: unknown[] = [since];
  if (filter.owner) {
    where.push("(t.owner = ? COLLATE NOCASE OR e.actor = ? COLLATE NOCASE OR EXISTS (SELECT 1 FROM task_steps s WHERE s.task_id = t.id AND s.assignee = ? COLLATE NOCASE))");
    params.push(filter.owner, filter.owner, filter.owner);
  }
  if (filter.taskId) {
    where.push("e.task_id = ?");
    params.push(filter.taskId);
  }

  return db
    .prepare<unknown[], TaskEvent & { task_title: string; task_code: string | null }>(
      `SELECT e.*, t.title AS task_title, t.code AS task_code
         FROM task_events e JOIN tasks t ON t.id = e.task_id
        WHERE ${where.join(" AND ")}
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT ?`,
    )
    .all(...params, filter.limit ?? 30);
}

export interface WorkSummary {
  기준일: string;
  담당자: string | null;
  진행중: number;
  보류: number;
  완료: number;
  지연: number;
  오늘마감: number;
  이번주마감: number;
  내가_지금_할_일: Array<{ id: number; code: string | null; title: string; 현재단계: string; 마감: string | null }>;
  지연건: Array<{ id: number; code: string | null; title: string; 마감: string | null; 지연일수: number }>;
}

export function workSummary(owner?: string): WorkSummary {
  const t = today();
  const all = listTasks({ owner, limit: 500 });
  const active = all.filter((x) => x.status === "진행중");

  const overdue = active.filter((x) => x.due_date && x.due_date < t);
  const mine = active
    .filter((x) => {
      const steps = getSteps(x.id);
      const cur = currentStepOf(steps);
      return cur !== null && (!owner || !cur.assignee || cur.assignee === owner || x.owner === owner);
    })
    .slice(0, 10);

  return {
    기준일: t,
    담당자: owner ?? null,
    진행중: active.length,
    보류: all.filter((x) => x.status === "보류").length,
    완료: all.filter((x) => x.status === "완료").length,
    지연: overdue.length,
    오늘마감: active.filter((x) => x.due_date === t).length,
    이번주마감: active.filter((x) => x.due_date && x.due_date >= t && x.due_date <= addDays(t, 7)).length,
    내가_지금_할_일: mine.map((x) => ({
      id: x.id,
      code: x.code,
      title: x.title,
      현재단계: x.currentStepName ?? "-",
      마감: x.due_date,
    })),
    지연건: overdue.map((x) => ({
      id: x.id,
      code: x.code,
      title: x.title,
      마감: x.due_date,
      지연일수: x.due_date ? diffDays(x.due_date, t) : 0,
    })),
  };
}

export { addDays, diffDays };
