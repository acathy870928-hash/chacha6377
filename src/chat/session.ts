import type Anthropic from "@anthropic-ai/sdk";
import { config } from "../config.js";

interface Session {
  messages: Anthropic.Beta.BetaMessageParam[];
  updatedAt: number;
}

const sessions = new Map<string, Session>();

/** 평범한 사용자 발화(문자열 content)만 잘라내기 안전 지점이다 — tool_use/tool_result 쌍을 깨뜨리지 않는다. */
function trim(messages: Anthropic.Beta.BetaMessageParam[]): Anthropic.Beta.BetaMessageParam[] {
  const cutPoints = messages
    .map((m, i) => (m.role === "user" && typeof m.content === "string" ? i : -1))
    .filter((i) => i >= 0);
  if (cutPoints.length <= config.maxHistoryTurns) return messages;
  const from = cutPoints[cutPoints.length - config.maxHistoryTurns]!;
  return messages.slice(from);
}

function sweep(): void {
  const ttl = config.sessionTtlMinutes * 60_000;
  const cutoff = Date.now() - ttl;
  for (const [key, s] of sessions) if (s.updatedAt < cutoff) sessions.delete(key);
}

export function getHistory(conversationId: string): Anthropic.Beta.BetaMessageParam[] {
  sweep();
  return sessions.get(conversationId)?.messages ?? [];
}

export function saveHistory(conversationId: string, messages: Anthropic.Beta.BetaMessageParam[]): void {
  sessions.set(conversationId, { messages: trim(messages), updatedAt: Date.now() });
}

export function clearHistory(conversationId: string): void {
  sessions.delete(conversationId);
}

export function sessionCount(): number {
  sweep();
  return sessions.size;
}
