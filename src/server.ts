import path from "node:path";
import { fileURLToPath } from "node:url";
import express, { type NextFunction, type Request, type Response } from "express";
import { config, claudeEnabled, teamsEnabled } from "./config.js";
import { getDb } from "./db/index.js";
import { chat } from "./chat/agent.js";
import { clearHistory, sessionCount } from "./chat/session.js";
import { workSummary } from "./domain/service.js";
import { WorkFlowBot, createTeamsAdapter } from "./teams/bot.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.resolve(here, "../public");

const app = express();
app.use(express.json({ limit: "256kb" }));

getDb(); // 시작 시 스키마 적용 및 DB 연결 확인

/* ------------------------------------------------------------------ */
/* Teams 엔드포인트 (Bot Framework 가 서명한 요청만 통과한다)            */
/* ------------------------------------------------------------------ */

const adapter = createTeamsAdapter();
const bot = new WorkFlowBot();

app.post("/api/messages", async (req, res) => {
  if (!adapter) {
    res.status(503).json({ error: "Teams 설정(MICROSOFT_APP_ID/PASSWORD)이 없어 봇이 비활성 상태입니다." });
    return;
  }
  await adapter.process(req, res, (context) => bot.run(context));
});

/* ------------------------------------------------------------------ */
/* 웹 UI 및 API                                                        */
/* ------------------------------------------------------------------ */

/** 토큰이 설정돼 있으면 토큰 검사, 없으면 로컬 접속만 허용한다. */
function guard(req: Request, res: Response, next: NextFunction): void {
  if (config.webAccessToken) {
    const supplied = req.header("x-access-token") ?? (req.query.token as string | undefined);
    if (supplied !== config.webAccessToken) {
      res.status(401).json({ error: "접근 토큰이 올바르지 않습니다." });
      return;
    }
    next();
    return;
  }
  const ip = req.ip ?? "";
  if (ip.includes("127.0.0.1") || ip === "::1" || ip.includes("::ffff:127.0.0.1")) {
    next();
    return;
  }
  res.status(403).json({
    error: "BOT_WEB_ACCESS_TOKEN 이 설정되지 않아 로컬 접속만 허용됩니다. 외부에서 쓰려면 .env 에 BOT_WEB_ACCESS_TOKEN 을 설정하세요.",
  });
}

app.get("/healthz", (_req, res) => {
  res.json({ ok: true, claude: claudeEnabled, teams: teamsEnabled, sessions: sessionCount() });
});

app.post("/api/chat", guard, async (req, res) => {
  const { message, conversationId, user, owner } = req.body ?? {};
  if (typeof message !== "string" || !message.trim()) {
    res.status(400).json({ error: "message 가 필요합니다." });
    return;
  }
  try {
    const result = await chat({
      conversationId: typeof conversationId === "string" && conversationId ? conversationId : "web",
      message: message.trim(),
      user: typeof user === "string" && user ? user : (config.defaultOwner || "사용자"),
      owner: typeof owner === "string" ? owner : undefined,
    });
    res.json(result);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    console.error("[web] chat 실패:", detail);
    res.status(500).json({ error: `응답 생성 실패: ${detail}` });
  }
});

/** 토큰을 쓰지 않고 바로 보는 현황판 (LLM 호출 없음) */
app.get("/api/summary", guard, (req, res) => {
  const owner = (req.query.owner as string | undefined) ?? config.defaultOwner ?? undefined;
  res.json(workSummary(owner || undefined));
});

app.post("/api/reset", guard, (req, res) => {
  clearHistory(typeof req.body?.conversationId === "string" ? req.body.conversationId : "web");
  res.json({ ok: true });
});

app.use(express.static(publicDir));

app.listen(config.port, config.host, () => {
  console.log(`▶ 업무 플로우 챗봇 실행 중 → http://${config.host}:${config.port}`);
  console.log(`  · DB          : ${config.dbPath}`);
  console.log(`  · Claude      : ${claudeEnabled ? config.model : "API 키 없음 (ANTHROPIC_API_KEY 설정 필요)"}`);
  console.log(`  · Teams 봇    : ${teamsEnabled ? "활성 (/api/messages)" : "비활성 (MICROSOFT_APP_ID/PASSWORD 미설정)"}`);
  if (!config.webAccessToken) console.log("  · 웹 UI       : 로컬 접속만 허용 (BOT_WEB_ACCESS_TOKEN 미설정)");
});
