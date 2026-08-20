import Anthropic from "@anthropic-ai/sdk";
import { config } from "../config.js";
import { today } from "../db/index.js";
import { getHistory, saveHistory } from "./session.js";
import { TOOL_SPECS, WRITE_TOOLS, executeTool, type ToolContext } from "./tools.js";

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

[기록 변경]
- 단계 완료, 상태 변경, 새 업무 등록 같은 변경은 대상 업무와 단계가 명확할 때만 실행합니다. 애매하면 실행하지 말고 먼저 확인 질문을 하세요.
- 변경한 뒤에는 무엇을 어떻게 바꿨는지 한 줄로 분명히 알립니다.

[말투]
- 한국어 존댓말. Teams와 휴대폰에서 읽기 쉽게 짧은 문단과 불릿을 씁니다.
- 요점을 먼저 말하고 세부는 뒤에. 인사말·사족은 생략합니다.
- 마크다운은 굵게와 불릿 정도만 씁니다. 표는 열이 3개 이하일 때만 씁니다.`;

export interface ChatResult {
  reply: string;
  toolCalls: string[];
  changed: boolean;
  usage: { input: number; output: number; cacheRead: number };
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

  const ctx: ToolContext = { user: opts.user, owner: opts.owner || config.defaultOwner || opts.user };

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
        { type: "text", text: `오늘 날짜: ${today()}\n대화 상대: ${opts.user}\n"내 업무"의 기본 담당자: ${ctx.owner}` },
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

  return { reply, toolCalls, changed: toolCalls.some((n) => WRITE_TOOLS.has(n)), usage };
}
