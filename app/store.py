"""기사/브리핑 조회·수정 로직."""
import json
import re
from typing import Any

from .db import new_code, now_iso, rows_to_articles, row_to_article, session
from .scoring import compute_signal, signal_reason


def slugify(title: str, fallback: str = "") -> str:
    """공개 URL 조각.

    한글 제목을 그대로 쓰면 카톡에 붙였을 때 퍼센트 인코딩돼 주소가 길고 지저분해진다.
    사람이 URL을 읽을 일은 없으므로 짧은 랜덤 코드를 쓴다.
    """
    return fallback or new_code(8)


def _unique_slug(conn, base: str) -> str:
    slug = base
    for attempt in range(50):
        hit = conn.execute("SELECT 1 FROM articles WHERE slug = ?", (slug,)).fetchone()
        if not hit:
            return slug
        slug = f"{base}-{new_code(4)}"
    return new_code(12)


def upsert_article(conn, payload: dict[str, Any]) -> tuple[int, str]:
    """수집기가 보낸 기사 하나를 저장/갱신. (article_id, 'created'|'updated') 반환."""
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("title 은 필수입니다")

    body = (payload.get("body") or "").strip()
    publisher = (payload.get("publisher") or "").strip()
    published_at = (payload.get("published_at") or "").strip()
    source_id = (payload.get("source_id") or payload.get("origin_url") or "").strip() or None

    signal = payload.get("signal")
    if signal is None:
        signal = compute_signal(title, body, publisher, published_at)
    signal = max(0, min(99, int(signal)))

    summary = (payload.get("summary") or "").strip()
    if not summary and body:
        summary = re.sub(r"\s+", " ", body)[:120]

    audience = (payload.get("audience") or "both").strip()
    if audience not in ("rep", "fa", "both"):
        audience = "both"

    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    now = now_iso()
    existing = None
    if source_id:
        existing = conn.execute(
            "SELECT * FROM articles WHERE source_id = ?", (source_id,)
        ).fetchone()

    if existing:
        conn.execute(
            """UPDATE articles
                  SET title=?, body=?, summary=?, publisher=?, origin_url=?,
                      published_at=?, signal=?, tags=?, updated_at=?
                WHERE id=?""",
            (
                title, body, summary, publisher,
                (payload.get("origin_url") or "").strip(),
                published_at, signal, json.dumps(tags, ensure_ascii=False), now,
                existing["id"],
            ),
        )
        if payload.get("audience"):
            conn.execute(
                "UPDATE articles SET audience=? WHERE id=?", (audience, existing["id"])
            )
        return existing["id"], "updated"

    slug = _unique_slug(conn, slugify(title))
    cur = conn.execute(
        """INSERT INTO articles
             (source_id, slug, title, body, summary, publisher, origin_url,
              published_at, signal, tags, status, audience, fa_point, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,'candidate',?,'',?,?)""",
        (
            source_id, slug, title, body, summary, publisher,
            (payload.get("origin_url") or "").strip(),
            published_at, signal, json.dumps(tags, ensure_ascii=False), audience, now, now,
        ),
    )
    return int(cur.lastrowid), "created"


def list_candidates(
    status: str = "candidate",
    publisher: str = "",
    query: str = "",
    audience: str = "",
    limit: int = 60,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM articles WHERE 1=1"
    params: list[Any] = []
    if audience in ("rep", "fa"):
        # 'both'로 들어온 기사는 양쪽 탭에 모두 보인다
        sql += " AND audience IN (?, 'both')"
        params.append(audience)
    if status and status != "all":
        sql += " AND status = ?"
        params.append(status)
    if publisher:
        sql += " AND publisher = ?"
        params.append(publisher)
    if query:
        sql += " AND (title LIKE ? OR body LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    sql += " ORDER BY signal DESC, published_at DESC, id DESC LIMIT ?"
    params.append(limit)

    with session() as conn:
        rows = conn.execute(sql, params).fetchall()
    articles = rows_to_articles(rows)
    for a in articles:
        a["reason"] = signal_reason(a["title"], a["body"], a["publisher"])
    return articles


def publishers() -> list[str]:
    with session() as conn:
        rows = conn.execute(
            "SELECT publisher, COUNT(*) c FROM articles"
            " WHERE publisher <> '' GROUP BY publisher ORDER BY c DESC"
        ).fetchall()
    return [r["publisher"] for r in rows]


def get_article_by_slug(slug: str) -> dict[str, Any] | None:
    with session() as conn:
        row = conn.execute("SELECT * FROM articles WHERE slug = ?", (slug,)).fetchone()
    return row_to_article(row) if row else None


def set_status(article_ids: list[int], status: str) -> int:
    if not article_ids:
        return 0
    placeholders = ",".join("?" * len(article_ids))
    with session() as conn:
        cur = conn.execute(
            f"UPDATE articles SET status=?, updated_at=? WHERE id IN ({placeholders})",
            [status, now_iso(), *article_ids],
        )
    return cur.rowcount


def set_audience(article_ids: list[int], audience: str) -> int:
    if not article_ids or audience not in ("rep", "fa", "both"):
        return 0
    placeholders = ",".join("?" * len(article_ids))
    with session() as conn:
        cur = conn.execute(
            f"UPDATE articles SET audience=?, updated_at=? WHERE id IN ({placeholders})",
            [audience, now_iso(), *article_ids],
        )
    return cur.rowcount


def set_fa_point(article_id: int, text: str) -> None:
    with session() as conn:
        conn.execute(
            "UPDATE articles SET fa_point=?, updated_at=? WHERE id=?",
            (text.strip(), now_iso(), article_id),
        )


# ---------------------------------------------------------------- 브리핑

def create_briefing(
    title: str, intro: str, article_ids: list[int], audience: str = "both"
) -> dict[str, Any]:
    if audience not in ("rep", "fa", "both"):
        audience = "both"
    with session() as conn:
        code = new_code()
        cur = conn.execute(
            "INSERT INTO briefings (code, title, intro, status, audience, published_at, created_at)"
            " VALUES (?,?,?,'published',?,?,?)",
            (code, title.strip(), intro.strip(), audience, now_iso(), now_iso()),
        )
        briefing_id = int(cur.lastrowid)
        for pos, aid in enumerate(article_ids):
            conn.execute(
                "INSERT OR REPLACE INTO briefing_items (briefing_id, article_id, position)"
                " VALUES (?,?,?)",
                (briefing_id, aid, pos),
            )
        if article_ids:
            placeholders = ",".join("?" * len(article_ids))
            conn.execute(
                f"UPDATE articles SET status='selected', updated_at=?"
                f" WHERE id IN ({placeholders})",
                [now_iso(), *article_ids],
            )
        row = conn.execute("SELECT * FROM briefings WHERE id=?", (briefing_id,)).fetchone()
    return dict(row)


def get_briefing(code: str) -> dict[str, Any] | None:
    with session() as conn:
        row = conn.execute("SELECT * FROM briefings WHERE code=?", (code,)).fetchone()
        if not row:
            return None
        items = conn.execute(
            """SELECT a.* FROM briefing_items bi
                 JOIN articles a ON a.id = bi.article_id
                WHERE bi.briefing_id = ?
                ORDER BY bi.position""",
            (row["id"],),
        ).fetchall()
    briefing = dict(row)
    briefing["articles"] = rows_to_articles(items)
    return briefing


def list_briefings(limit: int = 30) -> list[dict[str, Any]]:
    with session() as conn:
        rows = conn.execute(
            """SELECT b.*, COUNT(bi.article_id) AS item_count,
                      (SELECT COUNT(*) FROM views v WHERE v.briefing_id = b.id) AS view_count
                 FROM briefings b
                 LEFT JOIN briefing_items bi ON bi.briefing_id = b.id
                GROUP BY b.id ORDER BY b.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def log_view(article_id: int | None, briefing_id: int | None) -> None:
    with session() as conn:
        conn.execute(
            "INSERT INTO views (article_id, briefing_id, viewed_at) VALUES (?,?,?)",
            (article_id, briefing_id, now_iso()),
        )


def view_counts(article_ids: list[int]) -> dict[int, int]:
    if not article_ids:
        return {}
    placeholders = ",".join("?" * len(article_ids))
    with session() as conn:
        rows = conn.execute(
            f"SELECT article_id, COUNT(*) c FROM views"
            f" WHERE article_id IN ({placeholders}) GROUP BY article_id",
            article_ids,
        ).fetchall()
    return {r["article_id"]: r["c"] for r in rows}
