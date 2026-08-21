-- 업무 플로우 진행 상황 저장소
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 업무 유형별 표준 플로우 (템플릿)
CREATE TABLE IF NOT EXISTS flow_templates (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS flow_template_steps (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL REFERENCES flow_templates(id) ON DELETE CASCADE,
  seq         INTEGER NOT NULL,          -- 1부터 시작하는 단계 순서
  name        TEXT NOT NULL,
  owner_role  TEXT,                      -- 이 단계를 보통 누가 하는지 (예: 담당자, 팀장, 재무팀)
  sla_days    INTEGER,                   -- 이 단계 표준 소요일 (지연 판단 기준)
  UNIQUE (template_id, seq)
);

-- 실제 진행 중인 개별 업무 건
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  code        TEXT UNIQUE,               -- 사람이 부르는 식별자 (예: CT-2026-014)
  title       TEXT NOT NULL,
  template_id INTEGER REFERENCES flow_templates(id),
  owner       TEXT,                      -- 내 업무 구분용 담당자
  requester   TEXT,                      -- 요청자/유관부서
  priority    TEXT NOT NULL DEFAULT '보통' CHECK (priority IN ('높음','보통','낮음')),
  due_date    TEXT,                      -- YYYY-MM-DD
  status      TEXT NOT NULL DEFAULT '진행중' CHECK (status IN ('진행중','완료','보류','취소')),
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 업무 건별 실제 플로우 단계와 그 상태
CREATE TABLE IF NOT EXISTS task_steps (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  seq          INTEGER NOT NULL,
  name         TEXT NOT NULL,
  assignee     TEXT,
  status       TEXT NOT NULL DEFAULT '대기' CHECK (status IN ('대기','진행중','완료','보류','생략')),
  due_date     TEXT,
  started_at   TEXT,
  completed_at TEXT,
  note         TEXT,
  UNIQUE (task_id, seq)
);

-- 변경 이력: "내가 퇴근한 뒤에 뭐가 바뀌었나"를 답하기 위한 핵심 테이블
CREATE TABLE IF NOT EXISTS task_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  step_id    INTEGER REFERENCES task_steps(id) ON DELETE SET NULL,
  actor      TEXT,                       -- 변경한 사람
  kind       TEXT NOT NULL,              -- task_created / step_status / task_status / note
  message    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_owner   ON tasks(owner);
CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_steps_task    ON task_steps(task_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_task   ON task_events(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_time   ON task_events(created_at);

-- 자리 비움(조기 퇴근·외근) 기록: 부재 중 질문에 대신 답하기 위한 근거
CREATE TABLE IF NOT EXISTS absences (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  person      TEXT NOT NULL,              -- 자리를 비운 사람
  reason      TEXT,                       -- 조기 퇴근 / 외근 / 회의 등
  note        TEXT,                       -- 인수인계 메모 (부재 중 질문에 그대로 안내)
  contactable INTEGER NOT NULL DEFAULT 0, -- 급한 건 연락 가능 여부
  started_at  TEXT NOT NULL,
  until       TEXT,                       -- 복귀 예정 시각
  ended_at    TEXT,                       -- 실제 복귀 시각 (NULL 이면 부재 중)
  created_at  TEXT NOT NULL
);

-- 부재 중 다른 사람이 물어본 질문 (복귀 후 브리핑용)
CREATE TABLE IF NOT EXISTS inquiries (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  absence_id INTEGER REFERENCES absences(id) ON DELETE SET NULL,
  about      TEXT NOT NULL,               -- 누구 업무에 대한 질문인지
  asker      TEXT NOT NULL,
  question   TEXT NOT NULL,
  answer     TEXT,                        -- 봇이 대신 답한 내용 요약
  seen       INTEGER NOT NULL DEFAULT 0,  -- 복귀 후 확인 여부
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_absence_person ON absences(person, ended_at);
CREATE INDEX IF NOT EXISTS idx_inquiry_about  ON inquiries(about, seen, created_at);
