import { getDb, now } from "../db/index.js";

export interface Absence {
  id: number;
  person: string;
  reason: string | null;
  note: string | null;
  contactable: number;
  started_at: string;
  until: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface Inquiry {
  id: number;
  absence_id: number | null;
  about: string;
  asker: string;
  question: string;
  answer: string | null;
  seen: number;
  created_at: string;
}

function plusMinutes(minutes: number): string {
  const d = new Date(Date.now() + minutes * 60_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

/* ------------------------------------------------------------------ */
/* 부재 등록 / 복귀                                                     */
/* ------------------------------------------------------------------ */

export interface StartAbsenceInput {
  person: string;
  reason?: string;
  note?: string;
  /** 몇 분 뒤 복귀 예정인지 (예: 조기 퇴근 후 1시간 = 60) */
  minutes?: number;
  /** 복귀 예정 시각을 직접 지정할 때 'YYYY-MM-DD HH:MM' */
  until?: string;
  contactable?: boolean;
}

export function startAbsence(input: StartAbsenceInput): Absence {
  const db = getDb();
  const active = getActiveAbsence(input.person);
  if (active) endAbsence(input.person); // 이전 부재가 남아 있으면 정리하고 새로 시작

  const until = input.until
    ? input.until.length === 16
      ? `${input.until}:00`
      : input.until
    : input.minutes
      ? plusMinutes(input.minutes)
      : null;

  const info = db
    .prepare(
      `INSERT INTO absences (person, reason, note, contactable, started_at, until, ended_at, created_at)
       VALUES (?, ?, ?, ?, ?, ?, NULL, ?)`,
    )
    .run(input.person, input.reason ?? null, input.note ?? null, input.contactable ? 1 : 0, now(), until, now());

  return db.prepare<[number], Absence>("SELECT * FROM absences WHERE id = ?").get(Number(info.lastInsertRowid))!;
}

export function getActiveAbsence(person: string): Absence | undefined {
  return getDb()
    .prepare<[string], Absence>(
      "SELECT * FROM absences WHERE person = ? COLLATE NOCASE AND ended_at IS NULL ORDER BY id DESC LIMIT 1",
    )
    .get(person);
}

export function listActiveAbsences(): Absence[] {
  return getDb().prepare<[], Absence>("SELECT * FROM absences WHERE ended_at IS NULL ORDER BY id DESC").all();
}

/** 복귀 처리. 부재 중 쌓인 질문을 함께 돌려준다. */
export function endAbsence(person: string): { absence: Absence | null; inquiries: Inquiry[] } {
  const db = getDb();
  const active = getActiveAbsence(person);
  if (!active) return { absence: null, inquiries: listInquiries({ person, onlyUnseen: true }) };

  db.prepare("UPDATE absences SET ended_at = ? WHERE id = ?").run(now(), active.id);
  const inquiries = listInquiries({ person, onlyUnseen: true });
  return { absence: { ...active, ended_at: now() }, inquiries };
}

/** 부재 상태 설명 – 도구 응답에 그대로 실어 보낸다. */
export function describeAbsence(a: Absence): Record<string, unknown> {
  const overdue = Boolean(a.until && a.until < now());
  return {
    부재중: true,
    담당자: a.person,
    사유: a.reason,
    자리비운시각: a.started_at,
    복귀예정: a.until ?? "미정",
    복귀예정경과: overdue,
    급한건연락가능: Boolean(a.contactable),
    인수인계메모: a.note,
  };
}

/** 해당 담당자가 부재 중이면 설명을, 아니면 null 을 준다. */
export function absenceInfo(person: string | null | undefined): Record<string, unknown> | null {
  if (!person) return null;
  const a = getActiveAbsence(person);
  return a ? describeAbsence(a) : null;
}

/* ------------------------------------------------------------------ */
/* 부재 중 들어온 질문                                                  */
/* ------------------------------------------------------------------ */

export function logInquiry(input: { about: string; asker: string; question: string; answer?: string }): void {
  const db = getDb();
  const active = getActiveAbsence(input.about);
  db.prepare(
    "INSERT INTO inquiries (absence_id, about, asker, question, answer, seen, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
  ).run(active?.id ?? null, input.about, input.asker, input.question, input.answer?.slice(0, 800) ?? null, now());
}

export function listInquiries(filter: { person?: string; onlyUnseen?: boolean; sinceHours?: number; limit?: number } = {}): Inquiry[] {
  const db = getDb();
  const where: string[] = [];
  const params: unknown[] = [];
  if (filter.person) {
    where.push("about = ? COLLATE NOCASE");
    params.push(filter.person);
  }
  if (filter.onlyUnseen) where.push("seen = 0");
  if (filter.sinceHours) {
    where.push("created_at >= ?");
    params.push(new Date(Date.now() - filter.sinceHours * 3_600_000).toISOString().slice(0, 19).replace("T", " "));
  }
  return db
    .prepare<unknown[], Inquiry>(
      `SELECT * FROM inquiries ${where.length ? `WHERE ${where.join(" AND ")}` : ""} ORDER BY created_at DESC, id DESC LIMIT ?`,
    )
    .all(...params, filter.limit ?? 30);
}

export function markInquiriesSeen(person: string): number {
  return getDb().prepare("UPDATE inquiries SET seen = 1 WHERE about = ? COLLATE NOCASE AND seen = 0").run(person).changes;
}

export function unseenInquiryCount(person: string): number {
  return (
    getDb()
      .prepare<[string], { c: number }>("SELECT COUNT(*) AS c FROM inquiries WHERE about = ? COLLATE NOCASE AND seen = 0")
      .get(person)?.c ?? 0
  );
}
