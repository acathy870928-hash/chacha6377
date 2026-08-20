import "dotenv/config";

function bool(v: string | undefined, fallback = false): boolean {
  if (v === undefined) return fallback;
  return ["1", "true", "yes", "y", "on"].includes(v.toLowerCase());
}

export const config = {
  // --- 서버 ---
  port: Number(process.env.BOT_PORT ?? 3978),
  host: process.env.BOT_HOST ?? "127.0.0.1",
  /** 웹 UI 접근 토큰. 비워두면 로컬(127.0.0.1) 접속만 허용된다. */
  webAccessToken: process.env.BOT_WEB_ACCESS_TOKEN ?? "",

  // --- 데이터 ---
  dbPath: process.env.BOT_DB_PATH ?? "./data/workflow.db",

  // --- Claude ---
  anthropicApiKey: process.env.ANTHROPIC_API_KEY ?? "",
  model: process.env.BOT_MODEL ?? "claude-opus-5",
  /** low = 빠르고 저렴 (단순 조회 챗봇에 적합), high 이상 = 복잡한 추론 */
  effort: (process.env.BOT_EFFORT ?? "low") as "low" | "medium" | "high" | "xhigh" | "max",
  maxTokens: Number(process.env.BOT_MAX_TOKENS ?? 16000),
  /** 안전 분류기가 요청을 거절했을 때 다른 모델로 자동 우회 */
  serverSideFallback: bool(process.env.BOT_SERVER_SIDE_FALLBACK, true),

  // --- 대화 기본값 ---
  /** 사용자를 특정할 수 없을 때 "내 업무"의 기본 담당자 */
  defaultOwner: process.env.BOT_DEFAULT_OWNER ?? "",
  /** 한 대화에서 유지할 최대 턴 수 (초과 시 오래된 것부터 버림) */
  maxHistoryTurns: Number(process.env.BOT_MAX_HISTORY_TURNS ?? 20),
  /** 대화 세션 만료 (분) */
  sessionTtlMinutes: Number(process.env.BOT_SESSION_TTL_MINUTES ?? 120),
  /** 한 질문당 도구 호출 왕복 상한 (무한 루프 방지) */
  maxToolIterations: Number(process.env.BOT_MAX_TOOL_ITERATIONS ?? 8),

  // --- Microsoft Teams ---
  teams: {
    appId: process.env.MICROSOFT_APP_ID ?? "",
    appPassword: process.env.MICROSOFT_APP_PASSWORD ?? "",
    appTenantId: process.env.MICROSOFT_APP_TENANT_ID ?? "",
    appType: process.env.MICROSOFT_APP_TYPE ?? "MultiTenant",
  },
};

export const teamsEnabled = Boolean(config.teams.appId && config.teams.appPassword);
export const claudeEnabled = Boolean(config.anthropicApiKey);
