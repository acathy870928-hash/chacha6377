"""SQLite 스키마와 쿼리 헬퍼."""
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from .config import DB_PATH

KST = timezone(timedelta(hours=9))

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    TEXT UNIQUE,           -- 수집기 쪽 고유 키(중복 방지)
    slug         TEXT UNIQUE NOT NULL,  -- 공개 링크용
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    summary      TEXT NOT NULL DEFAULT '',
    publisher    TEXT NOT NULL DEFAULT '',
    origin_url   TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    signal       INTEGER NOT NULL DEFAULT 0,   -- 기사 신호(우선순위 점수)
    tags         TEXT NOT NULL DEFAULT '[]',
    status       TEXT NOT NULL DEFAULT 'candidate', -- candidate|selected|rejected
    audience     TEXT NOT NULL DEFAULT 'both',      -- rep(대표용)|fa(FA용)|both
    fa_point     TEXT NOT NULL DEFAULT '',      -- 대표가 다는 'FA 활용 포인트'
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_status_signal ON articles(status, signal DESC);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_audience ON articles(audience);

CREATE TABLE IF NOT EXISTS briefings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE NOT NULL,  -- 카톡에 뿌리는 짧은 코드
    title        TEXT NOT NULL,
    intro        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'draft', -- draft|published
    audience     TEXT NOT NULL DEFAULT 'both',  -- rep|fa|both
    published_at TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS briefing_items (
    briefing_id INTEGER NOT NULL REFERENCES briefings(id) ON DELETE CASCADE,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (briefing_id, article_id)
);

CREATE TABLE IF NOT EXISTS views (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  INTEGER REFERENCES articles(id) ON DELETE CASCADE,
    briefing_id INTEGER REFERENCES briefings(id) ON DELETE SET NULL,
    viewed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_views_article ON views(article_id);
"""


def now_kst() -> datetime:
    return datetime.now(KST)


def now_iso() -> str:
    return now_kst().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def new_code(n: int = 7) -> str:
    """URL 에 들어갈 짧은 랜덤 코드."""
    alphabet = "abcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def row_to_article(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["tags"] = json.loads(data.get("tags") or "[]")
    except json.JSONDecodeError:
        data["tags"] = []
    return data


def rows_to_articles(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_article(r) for r in rows]
