"""문서 메타데이터 — 보험사·상품·시행일.

보험 약관 검색이 무너지는 지점은 대부분 본문이 아니라 **메타데이터**다.
"흥국화재 암보험" 이라고 물었는데 삼성생명 자료가 먼저 나오는 문제는 임베딩을
아무리 좋게 해도 안 풀린다. 문서마다 보험사·상품·시행일을 붙여 두고 그걸로
거르거나 밀어 올려야 한다.

출처 두 가지를 병합한다(뒤가 우선).
1. **파일명 규칙** — ``20090801_20091001_현대해상_약관_무배당 하이라이프퍼펙트종합보험(Hi0908)_S367.pdf``
2. **사이드카 JSON** — 원본 옆의 ``<파일명>.meta.json``. 파싱이 틀렸을 때 사람이 고쳐 넣는 자리.

상품명은 원문(`product_name_raw`)과 정규화형(`product_name_standard`)을 함께 둔다.
"무배당" 접두어 하나 때문에 검색이 실패하는 사례가 실제로 보고돼 있어서, 접두어·
상품코드·개정 표기를 떼어낸 형태를 따로 들고 있어야 한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

META_SUFFIX = ".meta.json"

# 상품명 앞에 붙는 상품 성격 표기 — 검색어에는 거의 안 쓰인다
RE_NAME_PREFIX = re.compile(r"^(?:\(?무배당\)?|무배당|\(무\)|무·?|\(갱신형\)|갱신형|\(순수보장형\))\s*")
# 상품명 뒤의 상품코드/개정 표기: (Hi0908), (26.03), [2601]
RE_NAME_SUFFIX = re.compile(r"[\s]*[(\[（]\s*[A-Za-z0-9.\-]+\s*[)\]）]\s*$")
RE_CODE = re.compile(r"[(\[（]\s*([A-Za-z]{1,4}\s?\d{2,6}[A-Za-z0-9]*)\s*[)\]）]")
RE_YYYYMMDD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")

DOCUMENT_TYPES = {
    "약관": "보험약관",
    "보험약관": "보험약관",
    "사업방법서": "사업방법서",
    "상품안내장": "상품안내장",
    "상품요약서": "상품요약서",
    "요약서": "상품요약서",
    "가입설계서": "가입설계서",
    "이용약관": "이용약관",
}

# 표기 흔들림 → 대표 이름. 질의에서 보험사를 찾아낼 때도 쓴다.
INSURER_ALIASES: dict[str, tuple[str, ...]] = {
    "현대해상": ("현대해상화재보험", "현대해상화재", "현대해상"),
    "삼성생명": ("삼성생명보험", "삼성생명"),
    "삼성화재": ("삼성화재해상보험", "삼성화재"),
    "흥국화재": ("흥국화재해상보험", "흥국화재"),
    "흥국생명": ("흥국생명보험", "흥국생명"),
    "KB손해보험": ("KB손해보험", "KB손보", "케이비손해보험"),
    "DB손해보험": ("DB손해보험", "DB손보", "동부화재"),
    "메리츠화재": ("메리츠화재해상보험", "메리츠화재", "메리츠"),
    "MG손해보험": ("MG손해보험", "MG손보"),
    "롯데손해보험": ("롯데손해보험", "롯데손보"),
    "한화생명": ("한화생명보험", "한화생명"),
    "한화손해보험": ("한화손해보험", "한화손보"),
    "교보생명": ("교보생명보험", "교보생명"),
    "AIA생명": ("AIA생명보험", "AIA생명", "AIA"),
    "신한라이프": ("신한라이프생명보험", "신한라이프"),
    "NH농협손해보험": ("NH농협손해보험", "농협손해보험", "NH손해보험"),
    "NH농협생명": ("NH농협생명보험", "농협생명", "NH농협생명"),
    "하나손해보험": ("하나손해보험", "하나손보"),
    "미래에셋생명": ("미래에셋생명보험", "미래에셋생명"),
    "동양생명": ("동양생명보험", "동양생명"),
    "KDB생명": ("KDB생명보험", "KDB생명"),
    "라이나생명": ("라이나생명보험", "라이나생명"),
    "메트라이프": ("메트라이프생명보험", "메트라이프생명", "메트라이프"),
    "AIG손해보험": ("AIG손해보험", "AIG손보", "AIG"),
    "캐롯손해보험": ("캐롯손해보험", "캐롯"),
}


@dataclass
class DocumentMeta:
    """문서 한 건의 신원. 모르는 값은 None 으로 둔다(추측해서 채우지 않는다)."""

    insurer: str | None = None
    product_name_raw: str | None = None
    product_name_standard: str | None = None
    product_code: str | None = None
    document_type: str | None = None
    effective_from: str | None = None  # ISO (YYYY-MM-DD)
    effective_to: str | None = None
    serial: str | None = None
    source_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentMeta":
        """사이드카 JSON 을 읽는다. {"document": {...}} 로 감싼 형태도 받는다."""
        payload = data.get("document", data) if isinstance(data, dict) else {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in known and v not in ("", None)})

    def merge(self, other: "DocumentMeta") -> "DocumentMeta":
        """other 의 값이 있으면 그쪽을 쓴다(사이드카가 파일명 파싱을 덮어쓴다)."""
        merged = {}
        for field in fields(self):
            merged[field.name] = getattr(other, field.name) or getattr(self, field.name)
        return DocumentMeta(**merged)

    @property
    def label(self) -> str:
        """인용에 붙일 짧은 표기: "현대해상 하이라이프퍼펙트종합보험(HI0908)"."""
        parts = [p for p in (self.insurer, self.product_name_standard or self.product_name_raw) if p]
        label = " ".join(parts)
        if self.product_code and self.product_code not in label:
            label = f"{label}({self.product_code})" if label else self.product_code
        return label

    def effective_on(self, when: str | date) -> bool:
        """그 시점에 유효한 문서인가. 시행일 정보가 없으면 배제하지 않는다."""
        target = _to_date(when if isinstance(when, str) else when.isoformat())
        if target is None:
            return True
        start, end = _to_date(self.effective_from), _to_date(self.effective_to)
        if start and target < start:
            return False
        if end and target > end:
            return False
        return True

    def __str__(self) -> str:
        rows = [
            ("보험사", self.insurer),
            ("상품(원문)", self.product_name_raw),
            ("상품(정규화)", self.product_name_standard),
            ("상품코드", self.product_code),
            ("문서종류", self.document_type),
            ("시행", _period(self.effective_from, self.effective_to)),
        ]
        return "\n".join(f"  {name:<12}: {value}" for name, value in rows if value)


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------


def parse_filename(path: str | Path) -> DocumentMeta:
    """파일명 규칙에서 메타데이터를 뽑는다.

    기대 형식:
        ``{시행일}_{종료일}_{보험사}_{문서종류}_{상품명(코드)}_{일련번호}``

    형식이 어긋나도 알아본 조각만 채우고 나머지는 None 으로 둔다.
    """
    path = Path(path)
    stem = path.stem
    for suffix in (".ocr", ):  # 파생 파일은 원본 이름으로 되돌린다
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]

    parts = [p.strip() for p in stem.split("_") if p.strip()]
    meta = DocumentMeta(source_file=path.name)

    dates = [p for p in parts[:2] if RE_YYYYMMDD.match(p)]
    if dates:
        meta.effective_from = _iso(dates[0])
        if len(dates) > 1:
            meta.effective_to = _iso(dates[1])
    rest = parts[len(dates) :]

    if rest and (canonical := canonical_insurer(rest[0])):
        meta.insurer = canonical
        rest = rest[1:]

    if rest and rest[0] in DOCUMENT_TYPES:
        meta.document_type = DOCUMENT_TYPES[rest[0]]
        rest = rest[1:]

    if rest and re.fullmatch(r"[A-Za-z]\d{1,6}", rest[-1]):
        meta.serial = rest[-1].upper()
        rest = rest[:-1]

    if rest:
        raw = " ".join(rest).strip()
        meta.product_name_raw = raw
        meta.product_code = extract_code(raw)
        meta.product_name_standard = normalize_product_name(raw)

    return meta


def load_sidecar(path: str | Path) -> DocumentMeta | None:
    """원본 옆의 ``<파일명>.meta.json`` 을 읽는다. 없으면 None."""
    path = Path(path)
    for candidate in (path.with_suffix(path.suffix + META_SUFFIX), path.with_suffix(META_SUFFIX)):
        if candidate.is_file():
            try:
                return DocumentMeta.from_dict(json.loads(candidate.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{candidate.name}: JSON 을 읽을 수 없습니다 — {exc}") from exc
    return None


def read_meta(path: str | Path) -> DocumentMeta:
    """파일명 파싱 + 사이드카 병합. 사이드카가 이긴다."""
    meta = parse_filename(path)
    sidecar = load_sidecar(path)
    return meta.merge(sidecar) if sidecar else meta


def extract_code(name: str) -> str | None:
    """상품명에서 상품코드를 뽑는다: "…종합보험(Hi0908)" → "HI0908"."""
    match = RE_CODE.search(name)
    if not match:
        return None
    return match.group(1).replace(" ", "").upper()


def normalize_product_name(name: str) -> str:
    """검색용 상품명. 접두어·상품코드·개정 표기를 떼어낸다.

    "무배당 하이라이프퍼펙트종합보험(Hi0908)" → "하이라이프퍼펙트종합보험"
    """
    cleaned = name.strip()
    while True:
        stripped = RE_NAME_SUFFIX.sub("", cleaned).strip()
        stripped = RE_NAME_PREFIX.sub("", stripped).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned or name.strip()


def canonical_insurer(text: str) -> str | None:
    """표기가 흔들려도 대표 이름으로 맞춘다. 못 찾으면 None."""
    probe = text.strip().replace(" ", "")
    if not probe:
        return None
    for canonical, aliases in INSURER_ALIASES.items():
        if any(probe == alias.replace(" ", "") for alias in aliases):
            return canonical
    return None


def detect_insurers(text: str) -> list[str]:
    """질의나 본문에 등장하는 보험사를 찾는다(긴 별칭 우선).

    "흥국화재 암보험 가입했어요" → ["흥국화재"]
    """
    probe = text.replace(" ", "")
    found: list[str] = []
    for canonical, aliases in INSURER_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias.replace(" ", "") in probe:
                found.append(canonical)
                break
    return found


def apply_to_chunks(chunks, meta: DocumentMeta) -> None:
    """청킹이 끝난 뒤 각 청크에 문서 신원을 찍는다.

    청킹기(`chunker` / `doc_chunker`)는 메타데이터를 모른 채 구조만 본다.
    신원은 여기서 따로 붙인다 — 청킹 규칙과 문서 신원은 서로 바뀔 이유가 다르다.
    """
    for chunk in chunks:
        chunk.insurer = meta.insurer or ""
        chunk.product_name = meta.product_name_standard or meta.product_name_raw or ""
        chunk.product_code = meta.product_code or ""
        chunk.document_type = meta.document_type or ""
        chunk.effective_from = meta.effective_from or ""
        chunk.effective_to = meta.effective_to or ""


# ---------------------------------------------------------------------------
# 날짜 헬퍼
# ---------------------------------------------------------------------------


def _iso(yyyymmdd: str) -> str | None:
    match = RE_YYYYMMDD.match(yyyymmdd)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _period(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} ~ {end}"
    return start or end or ""
