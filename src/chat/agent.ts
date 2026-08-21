import Anthropic from "@anthropic-ai/sdk";
import { config } from "../config.js";
import { now as nowText, today } from "../db/index.js";
import { getHistory, saveHistory } from "./session.js";
import { TOOL_SPECS, WRITE_TOOLS, executeTool, type ToolContext } from "./tools.js";
import { getActiveAbsence, listActiveAbsences, logInquiry, unseenInquiryCount } from "../domain/absence.js";

// 인자 없이 만들면 ANTHROPIC_API_KEY 또는 `ant auth login` 프로필을 자동으로 쓴다.
const client = new Anthropic();

/** 요청마다 바뀌지 않는 부분 — 프롬프트 캐시가 걸리도록 앞에 고정한다. */
const SYSTEM_STABLE = `당신은 사내 업무 플로우 비서입니다. 사용자가 맡은 업무가 지금 어느 단계까지 진행됐는지 확인해 주고, 요청하면 진행 상태를 대신 기록합니다.

[사실 확인]
- 모든 사실은 반드시 도구 호출 결과로만 말합니다. 기억이나 추측으로 단계·날짜·담당자를 지어내지 마세요.
- 도구 결과에 없는 내용은 "기록에 없습니다"라고 솔직히 답합니다.
- 사용자가 업무를 애매하게 부르면(예: "그 계약 건") 먼저 검색해 보고, 후보가 여러 개면 목록을 보여주고 어느 건인지 되묻습니다.

[진행 상황 답변 형식]
업무 하나의 진행 상황을 말할 때는 아래를 빠뜨리지 마세요.
- 현재 멈춰 있는 단계와 그 단계 담당자
- 진행률 (완료 단계 수 / 전체 단계 수)
- 다음에 무엇이 되어야 하는지
- 마감 대비 지연 여부

[도구 선택]
- "현황", "오늘 뭐 있지", "나 뭐 해야 돼" → get_work_summary
- "OO건 어디까지 갔어" → get_task_progress
- "내가 나간 뒤에 뭐 바뀌었어", "어제 이후 진행된 거" → get_recent_activity
- 목록·검색·지연 건 추리기 → list_tasks

[자리를 비운 사람 대신 답하기]
- 담당자가 부재 중이면 도구 결과에 "담당자부재" 정보가 함께 옵니다. 그 사람 업무를 다른 사람이 물으면 반드시 이렇게 답하세요.
  1) 기록 기준의 현재 진행 상황
  2) "○○님은 지금 자리에 안 계시고 △△에 복귀 예정입니다"
  3) 인수인계 메모가 있으면 그대로 전달
  4) 복귀 예정 시각이 지났으면 그 사실도 알립니다
- 부재자 본인인 척하지 마세요. 기록을 대신 확인해 드리는 입장으로 말합니다. ("제가 기록으로 확인해 보니…")
- 급한 건 연락이 가능하다고 등록돼 있으면 그 점을 알려주고, 아니면 복귀 후 처리 예정이라고 안내합니다.
- 사용자가 자리를 비운다고 하면(조기 퇴근, 외근, 자리 비움) set_absence 로 등록하고, 돌아왔다고 하면 end_absence 로 해제하면서 그동안 들어온 질문을 브리핑합니다.
- 다른 사람 업무를 물으면 도구의 owner 파라미터에 그 사람 이름을 넣습니다. 그냥 두면 대화 상대 기준으로 조회됩니다.

[기록 변경]
- 단계 완료, 상태 변경, 새 업무 등록 같은 변경은 대상 업무와 단계가 명확할 때만 실행합니다. 애매하면 실행하지 말고 먼저 확인 질문을 하세요.
- 대화 상대가 아닌 다른 사람의 업무를 변경할 때는, 누구 업무를 누가 바꿨는지 답변에 분명히 남깁니다.
- 변경한 뒤에는 무엇을 어떻게 바꿨는지 한 줄로 분명히 알립니다.

[말투]
- 한국어 존댓말. Teams와 휴대폰에서 읽기 쉽게 짧은 문단과 불릿을 씁니다.
- 요점을 먼저 말하고 세부는 뒤에. 인사말·사족은 생략합니다.
- 마크다운은 굵게와 불릿 정도만 씁니다. 표는 열이 3개 이하일 때만 씁니다.`;

/** 매 요청마다 바뀌는 맥락 — 캐시되지 않는 두 번째 시스템 블록에 넣는다. */
function volatileContext(user: string, owner: string): string {
  const lines = [`오늘 날짜와 시각: ${nowText()}`, `대화 상대: ${user}`, `"내 업무"의 기본 담당자: ${owner}`];

  const absences = listActiveAbsences();
  if (absences.length) {
    lines.push(
      "현재 자리를 비운 사람:",
      ...absences.map(
        (a) =>
          `- ${a.person} (${a.reason ?? "부재"}, ${a.until ? `${a.until} 복귀 예정` : "복귀 시각 미정"}` +
          `${a.until && a.until < nowText() ? ", 복귀 예정 시각 지남" : ""}` +
          `${a.contactable ? ", 급한 건 연락 가능" : ""})`,
      ),
    );
  } else {
    lines.push("현재 자리를 비운 사람: 없음");
  }

  const unseen = unseenInquiryCount(owner);
  if (unseen > 0) lines.push(`${owner} 님이 아직 확인하지 않은, 부재 중 들어온 질문 ${unseen}건이 있습니다.`);

  return lines.join("\n");
}

export interface ChatResult {
  reply: string;
  toolCalls: string[];
  changed: boolean;
  usage: { input: number; output: number; cacheRead: number };
  /** 부재 중인 담당자를 대신해 답한 경우 그 사람 이름들 */
  answeredFor: string[];
}

export interface ChatOptions {
  conversationId: string;
  message: string;
  user: string;
  owner?: string;
}

function textOf(content: Anthropic.Beta.BetaContentBlock[]): string {
  return content
    .filter((b): b is Anthropic.Beta.BetaTextBlock => b.type === "text")
    .map((b) => b.text)
    .join("\n")
    .trim();
}

export async function chat(opts: ChatOptions): Promise<ChatResult> {
  if (!config.anthropicApiKey && !process.env.ANTHROPIC_AUTH_TOKEN) {
    throw new Error("ANTHROPIC_API_KEY 가 설정되지 않았습니다. .env 파일에 키를 넣고 다시 실행해 주세요.");
  }

  const ctx: ToolContext = {
    user: opts.user,
    owner: opts.owner || config.defaultOwner || opts.user,
    touchedOwners: new Set<string>(),
  };

  const messages: Anthropic.Beta.BetaMessageParam[] = [
    ...getHistory(opts.conversationId),
    { role: "user", content: opts.message },
  ];

  const toolCalls: string[] = [];
  const usage = { input: 0, output: 0, cacheRead: 0 };
  let reply = "";

  for (let i = 0; i < config.maxToolIterations; i += 1) {
    const response = await client.beta.messages.create({
      model: config.model,
      max_tokens: config.maxTokens,
      thinking: { type: "adaptive" },
      output_config: { effort: config.effort },
      // 안전 분류기가 요청을 거절하면 서버가 다른 모델로 자동 우회한다.
      ...(config.serverSideFallback
        ? { betas: ["server-side-fallback-2026-07-01"], fallbacks: "default" as const }
        : {}),
      system: [
        { type: "text", text: SYSTEM_STABLE, cache_control: { type: "ephemeral" } },
        { type: "text", text: volatileContext(opts.user, ctx.owner) },
      ],
      tools: TOOL_SPECS,
      messages,
    });

    usage.input += response.usage.input_tokens ?? 0;
    usage.output += response.usage.output_tokens ?? 0;
    usage.cacheRead += response.usage.cache_read_input_tokens ?? 0;

    if (response.stop_reason === "refusal") {
      return {
        reply: "죄송합니다. 이 요청은 처리할 수 없습니다. 다르게 표현해서 다시 물어봐 주세요.",
        toolCalls,
        changed: false,
        usage,
        answeredFor: [],
      };
    }

    messages.push({ role: "assistant", content: response.content });

    if (response.stop_reason === "pause_turn") continue;

    const toolUses = response.content.filter(
      (b): b is Anthropic.Beta.BetaToolUseBlock => b.type === "tool_use",
    );

    if (!toolUses.length) {
      reply = textOf(response.content);
      if (response.stop_reason === "max_tokens" && reply) reply += "\n\n(답변이 길어 잘렸습니다. 범위를 좁혀 다시 물어봐 주세요.)";
      break;
    }

    const results: Anthropic.Beta.BetaToolResultBlockParam[] = toolUses.map((use) => {
      toolCalls.push(use.name);
      const { content, isError } = executeTool(use.name, use.input, ctx);
      return { type: "tool_result", tool_use_id: use.id, content, is_error: isError };
    });

    messages.push({ role: "user", content: results });
  }

  if (!reply) {
    reply = "확인에 시간이 너무 오래 걸렸습니다. 업무 이름을 구체적으로 알려주시면 다시 찾아보겠습니다.";
  }

  saveHistory(opts.conversationId, messages);

  // 자리를 비운 사람의 업무를 다른 사람이 물어본 것이면, 복귀 후 브리핑할 수 있게 기록해 둔다.
  const answeredFor: string[] = [];
  for (const person of ctx.touchedOwners) {
    if (person === opts.user) continue;
    if (!getActiveAbsence(person)) continue;
    logInquiry({ about: person, asker: opts.user, question: opts.message, answer: reply });
    answeredFor.push(person);
  }

  return { reply, toolCalls, changed: toolCalls.some((n) => WRITE_TOOLS.has(n)), usage, answeredFor };
}
