import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Database from "better-sqlite3";
import { config } from "../config.js";

const here = path.dirname(fileURLToPath(import.meta.url));

let db: Database.Database | null = null;

/** 싱글턴 DB 핸들. 최초 호출 시 스키마를 적용한다. */
export function getDb(): Database.Database {
  if (db) return db;

  fs.mkdirSync(path.dirname(path.resolve(config.dbPath)), { recursive: true });
  db = new Database(config.dbPath);
  db.pragma("journal_mode = WAL");
  db.pragma("foreign_keys = ON");

  // 빌드 후에는 dist/db/ 에서 실행되므로 src 쪽 schema.sql 도 함께 찾는다.
  const candidates = [
    path.join(here, "schema.sql"),
    path.join(here, "../../src/db/schema.sql"),
  ];
  const schemaPath = candidates.find((p) => fs.existsSync(p));
  if (!schemaPath) throw new Error(`schema.sql 을 찾을 수 없습니다: ${candidates.join(", ")}`);
  db.exec(fs.readFileSync(schemaPath, "utf8"));

  return db;
}

/** 테스트/시드용 – 모든 업무 데이터를 지운다 (템플릿 포함). */
export function resetDb(): void {
  const d = getDb();
  d.exec(`
    DELETE FROM task_events;
    DELETE FROM task_steps;
    DELETE FROM tasks;
    DELETE FROM flow_template_steps;
    DELETE FROM flow_templates;
    DELETE FROM sqlite_sequence;
  `);
}

/** 'YYYY-MM-DD HH:MM:SS' (로컬 시간) */
export function now(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** 'YYYY-MM-DD' (로컬 시간) */
export function today(): string {
  return now().slice(0, 10);
}
