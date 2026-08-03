"""파이프라인이 주고받는 데이터 구조."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# 담당자 확인 단계의 상태값
STATUS_PENDING = "pending"  # 검수 대기
STATUS_APPROVED = "approved"  # 승인 → MD 변환 대상
STATUS_REJECTED = "rejected"  # 담당자가 반려
STATUS_AUTO_PROMO = "auto_promo"  # 상품·홍보로 자동 제외
STATUS_AUTO_LOWREL = "auto_lowrel"  # 제도 관련성 낮음으로 자동 제외

ALL_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_AUTO_PROMO,
    STATUS_AUTO_LOWREL,
)

STATUS_LABELS = {
    STATUS_PENDING: "검수 대기",
    STATUS_APPROVED: "승인",
    STATUS_REJECTED: "반려",
    STATUS_AUTO_PROMO: "자동제외(홍보)",
    STATUS_AUTO_LOWREL: "자동제외(관련성)",
}

# MD 변환 시 붙는 분류 태그. 담당자가 검수 화면에서 바꿀 수 있다.
CATEGORIES = [
    "미분류",
    "실손의료보험",
    "판매채널·수수료",
    "건전성·회계",
    "자동차보험",
    "보험사기·소비자보호",
    "세제·연금",
    "상품규제",
    "기타 제도",
]

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "from",
    "ref",
}


def normalize_url(url: str) -> str:
    """추적 파라미터와 프래그먼트를 걷어낸 정규 URL."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in _TRACKING_PARAMS]
    netloc = parts.netloc.lower()
    if netloc.startswith("m."):
        netloc = "www." + netloc[2:]
    path = parts.path.rstrip("/") or "/"
    # http/https 로 같은 기사가 두 번 들어오지 않도록 스킴을 통일한다.
    # (http-only 사이트는 요청 시 리다이렉트를 따라가므로 수집에 지장 없음)
    scheme = "https" if parts.scheme in ("", "http", "https") else parts.scheme
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def make_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def slugify(text: str, max_len: int = 60) -> str:
    """한글은 살리고 파일명에 못 쓰는 문자만 제거한다."""
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]", " ", text)
    text = re.sub(r"[\[\]()]", " ", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = text.strip("-.")
    return text[:max_len] or "article"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Article:
    # ── 수집 단계에서 채워지는 값 ────────────────────────────────
    id: str
    url: str
    title: str
    source: str
    published_at: str = ""  # ISO8601, 원문에서 못 뽑으면 빈 문자열
    summary: str = ""
    content: str = ""
    collected_at: str = field(default_factory=_now)

    # ── 자동 분류 결과 ───────────────────────────────────────────
    policy_score: float = 0.0
    promo_score: float = 0.0
    matched_policy: list[str] = field(default_factory=list)
    matched_promo: list[str] = field(default_factory=list)
    auto_reason: str = ""

    # ── 담당자 확인 단계에서 채워지는 값 ─────────────────────────
    status: str = STATUS_PENDING
    category: str = "미분류"
    tags: list[str] = field(default_factory=list)
    effective_date: str = ""  # 제도 시행일 (담당자 입력, 예: 2026-07-01)
    reviewer: str = ""
    reviewer_note: str = ""
    edited_title: str = ""  # 비어 있으면 원 제목 사용
    edited_summary: str = ""  # 비어 있으면 자동 요약 사용
    reviewed_at: str = ""

    # ── MD 변환 단계 ─────────────────────────────────────────────
    exported_at: str = ""
    exported_path: str = ""

    @property
    def display_title(self) -> str:
        return self.edited_title.strip() or self.title.strip()

    @property
    def display_summary(self) -> str:
        return self.edited_summary.strip() or self.summary.strip()

    @property
    def is_decided(self) -> bool:
        return self.status in (STATUS_APPROVED, STATUS_REJECTED)

    def touch_review(self, reviewer: str = "") -> None:
        self.reviewed_at = _now()
        if reviewer:
            self.reviewer = reviewer

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        known = {f for f in cls.__dataclass_fields__}  # noqa: SLF001
        payload = {k: v for k, v in data.items() if k in known}
        # 수기로 작성한 JSON 처럼 id 가 빠져 있으면 URL 에서 만들어 준다.
        if not payload.get("id"):
            payload["id"] = make_id(payload.get("url", ""))
        payload["url"] = normalize_url(payload.get("url", ""))
        return cls(**payload)
