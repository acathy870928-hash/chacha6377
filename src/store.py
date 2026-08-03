"""기사 저장소. 단일 JSON 파일로 상태를 보관한다.

담당자가 내린 판단(status/category/메모 등)은 재수집해도 덮어쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Article, STATUS_PENDING

DEFAULT_DB = Path("data/articles.json")

# 재수집 시에도 보존해야 하는 담당자 입력 필드
_REVIEW_FIELDS = (
    "status",
    "category",
    "tags",
    "effective_date",
    "reviewer",
    "reviewer_note",
    "edited_title",
    "edited_summary",
    "reviewed_at",
    "exported_at",
    "exported_path",
)


class ArticleStore:
    def __init__(self, path: str | os.PathLike = DEFAULT_DB):
        self.path = Path(path)
        self._items: dict[str, Article] = {}
        self.load()

    # ── 입출력 ────────────────────────────────────────────────────
    def load(self) -> None:
        if not self.path.exists():
            self._items = {}
            return
        raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        self._items = {
            item["id"]: Article.from_dict(item) for item in raw.get("articles", [])
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "articles": [a.to_dict() for a in self.sorted_items()],
        }
        # 검수 중 크래시로 큐가 날아가지 않도록 원자적 교체
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ── 조회 ──────────────────────────────────────────────────────
    def get(self, article_id: str) -> Article | None:
        return self._items.get(article_id)

    def all(self) -> list[Article]:
        return self.sorted_items()

    def by_status(self, status: str) -> list[Article]:
        return [a for a in self.sorted_items() if a.status == status]

    def sorted_items(self) -> list[Article]:
        """발행일 최신순. 발행일이 없으면 수집일로 대체."""
        return sorted(
            self._items.values(),
            key=lambda a: (a.published_at or a.collected_at, a.id),
            reverse=True,
        )

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self._items.values():
            out[a.status] = out.get(a.status, 0) + 1
        return out

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, article_id: object) -> bool:
        return article_id in self._items

    # ── 갱신 ──────────────────────────────────────────────────────
    def upsert(self, article: Article) -> str:
        """새 기사면 'new', 기존 기사면 'updated'/'skipped' 를 돌려준다.

        이미 담당자가 손댄 기사는 본문만 갱신하고 판단은 그대로 둔다.
        """
        existing = self._items.get(article.id)
        if existing is None:
            self._items[article.id] = article
            return "new"

        # 담당자 입력은 보존
        for fname in _REVIEW_FIELDS:
            setattr(article, fname, getattr(existing, fname))
        article.collected_at = existing.collected_at

        # 아직 아무도 안 본 기사만 자동 분류 결과를 새로 반영
        if existing.status == STATUS_PENDING or not existing.reviewed_at:
            self._items[article.id] = article
            return "updated"

        # 검수가 끝난 기사는 본문 보강만
        if len(article.content) > len(existing.content):
            existing.content = article.content
            existing.summary = article.summary or existing.summary
            return "updated"
        return "skipped"

    def update_review(
        self,
        article_id: str,
        *,
        status: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        effective_date: str | None = None,
        reviewer: str | None = None,
        reviewer_note: str | None = None,
        edited_title: str | None = None,
        edited_summary: str | None = None,
    ) -> Article | None:
        article = self._items.get(article_id)
        if article is None:
            return None
        for name, value in (
            ("status", status),
            ("category", category),
            ("tags", tags),
            ("effective_date", effective_date),
            ("reviewer_note", reviewer_note),
            ("edited_title", edited_title),
            ("edited_summary", edited_summary),
        ):
            if value is not None:
                setattr(article, name, value)
        article.touch_review(reviewer or "")
        return article

    def delete(self, article_id: str) -> bool:
        return self._items.pop(article_id, None) is not None
