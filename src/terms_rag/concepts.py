"""보험 개념 정규화와 관계 생성 — 3차·4차 단계.

원칙: **약관이 정의하지 않은 개념은 만들지 않는다.**

"고액치료비암" 이라는 단어를 봤다고 곧바로 "암진단비" 로 바꾸면 안 된다. 같은 단어라도
약관마다 정의가 다르고, 2009년 약관과 2024년 약관이 다르다. 그래서 이 모듈은
**정의 조항에서 실제로 정의된 용어만** 개념으로 승격시키고, 승격시킬 때 반드시
근거(특약·조·페이지·청크)를 함께 붙인다. 정의를 못 찾으면 개념을 만들지 않는다.

만들어지는 관계는 사용자가 원한 사슬 그대로다::

    보험사 → 상품 → 적용기간 → 특약 → 조항 → 보장대상 → 지급조건 → 면책조건 → 감액조건 → 정의 → 원문 근거

즉 "고액치료비암" 하나에 대해 **같은 특약 안에서** 정의(제5조) / 지급사유(제1조) /
면책(제6조) / 감액(제7조) 조항을 모아 준다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

from .models import Chunk

# 약관의 정의 문형:
#   "고액치료비암"이라 함은 … 을 말합니다.
#   "진단확정"은 … 이어야 하며
#   "상해"라 함은 … 을 말합니다.
RE_DEFINITION = re.compile(
    r"[\"“'‘「『]\s*(?P<term>[^\"“”'’「」『』\n]{2,40}?)\s*[\"”'’」』]"
    r"\s*(?:이?라\s*함은|이?란|은|는|이라고\s*함은)\s*"
    r"(?P<body>.{5,500}?)"
    r"(?=(?:말합니다|말한다|합니다\.|이어야|의미합니다|를\s*말함))",
    re.S,
)

# 분류 근거 — 정의 본문에서 찾는다(용어 이름만 보고 추측하지 않는다)
CATEGORY_RULES: list[tuple[str, str | None, re.Pattern]] = [
    ("질병", "암", re.compile(r"악성신생물|암(?:으로|을|의|,|\s|$)|한국표준질병사인분류")),
    ("상해", None, re.compile(r"급격하고도?\s*우연한\s*외래의?\s*사고|상해")),
    ("질병", None, re.compile(r"질병|질환|진단분류")),
    ("치료행위", None, re.compile(r"입원|수술|통원|치료를?\s*받은|요양")),
    ("재해", None, re.compile(r"재해분류표|재해")),
]

# 개념의 성격
CONCEPT_TYPES: list[tuple[str, re.Pattern]] = [
    ("지급조건", re.compile(r"진단확정|보장개시|책임개시|대기\s*기간|면책\s*기간|자격증을?\s*가진")),
    ("면책조건", re.compile(r"지급하지\s*(?:아니|않)|보상하지\s*(?:아니|않)")),
    ("감액조건", re.compile(r"감액|\d{1,3}\s*%\s*(?:를|을)?\s*지급")),
]

# 조항 성격 → 그 조항이 개념에 대해 규정하는 것
ROLE_TO_RELATION = {
    "정의": "정의",
    "지급사유": "지급조건",
    "면책": "면책조건",
    "감액": "감액조건",
    "보험기간": "지급조건",
}


@dataclass
class Evidence:
    """원문 근거 — 이게 없으면 개념도 관계도 만들지 않는다."""

    chunk_id: str
    special_clause: str = ""
    article_no: str = ""
    article_title: str = ""
    page: int = 0

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "special_clause": self.special_clause or None,
            "article_no": _as_int(self.article_no),
            "article_title": self.article_title or None,
            "page": self.page,
        }


@dataclass
class Concept:
    """약관이 정의한 개념 하나."""

    raw_term: str
    standard_term: str
    concept_type: str
    category: str | None = None
    sub_category: str | None = None
    definition: str = ""
    defined_in: Evidence | None = None
    mentions: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = {
            "raw_term": self.raw_term,
            "standard_term": self.standard_term,
            "category": self.category,
            "sub_category": self.sub_category,
            "concept_type": self.concept_type,
        }
        return {k: v for k, v in payload.items() if v is not None}

    def to_full_dict(self) -> dict:
        payload = self.to_dict()
        payload["definition"] = self.definition
        payload["defined_in"] = self.defined_in.to_dict() if self.defined_in else None
        payload["mentions"] = [m.to_dict() for m in self.mentions]
        return payload


@dataclass
class Relation:
    """개념 ↔ 조항. "이 개념에 대해 이 조항이 무엇을 규정하는가"."""

    term: str
    relation: str  # 정의 | 지급조건 | 면책조건 | 감액조건
    evidence: Evidence

    def to_dict(self) -> dict:
        return {"term": self.term, "relation": self.relation, **self.evidence.to_dict()}


# ---------------------------------------------------------------------------
# 추출
# ---------------------------------------------------------------------------


def _evidence(chunk: Chunk) -> Evidence:
    return Evidence(
        chunk_id=chunk.chunk_id,
        special_clause=chunk.special_clause,
        article_no=chunk.article_no,
        article_title=chunk.article_title,
        page=chunk.page_start,
    )


def extract_definitions(chunks: Iterable[Chunk]) -> list[Concept]:
    """정의 조항에서만 개념을 뽑는다.

    정의 조항(`article_role == "정의"`)에 한정한다. 본문 아무 데서나 따옴표를 주워 오면
    "이른바 '실손'" 같은 것까지 개념이 되어 버린다.
    """
    concepts: dict[tuple[str, str], Concept] = {}
    for chunk in chunks:
        if chunk.article_role != "정의":
            continue
        for match in RE_DEFINITION.finditer(chunk.text):
            term = _clean_term(match.group("term"))
            if not _is_definable(term):
                continue
            body = " ".join(match.group("body").split())
            key = (chunk.special_clause, term)
            if key in concepts:
                continue
            category, sub_category = classify_category(body, term)
            concepts[key] = Concept(
                raw_term=term,
                standard_term=term,  # 표준용어 사전이 붙기 전까지는 원문을 그대로 쓴다
                concept_type=classify_concept_type(term, body, chunk),
                category=category,
                sub_category=sub_category,
                definition=body,
                defined_in=_evidence(chunk),
            )
    return list(concepts.values())


def classify_category(definition: str, term: str = "") -> tuple[str | None, str | None]:
    """정의 **본문**을 근거로 분류한다. 용어 이름만 보고 추측하지 않는다."""
    for category, sub_category, pattern in CATEGORY_RULES:
        if pattern.search(definition):
            return category, sub_category
    return None, None


def classify_concept_type(term: str, definition: str, chunk: Chunk) -> str:
    """개념의 성격. 절차·상태를 규정하면 지급조건, 대상을 규정하면 보장대상 정의."""
    for concept_type, pattern in CONCEPT_TYPES:
        if pattern.search(term) or pattern.search(definition):
            return concept_type
    return "보장대상 정의"


def link_mentions(concepts: list[Concept], chunks: Iterable[Chunk]) -> list[Relation]:
    """개념이 실제로 등장하는 조항을 찾아 관계를 만든다.

    **같은 특약 안으로 범위를 한정한다.** 특약이 다르면 같은 단어라도 다른 정의일 수 있다.
    """
    relations: list[Relation] = []
    for chunk in chunks:
        for concept in concepts:
            scope = concept.defined_in.special_clause if concept.defined_in else ""
            if scope and chunk.special_clause != scope:
                continue
            if concept.raw_term not in chunk.text:
                continue
            evidence = _evidence(chunk)
            concept.mentions.append(evidence)
            relation = ROLE_TO_RELATION.get(chunk.article_role)
            if relation:
                relations.append(Relation(term=concept.raw_term, relation=relation, evidence=evidence))
    return relations


def build_graph(chunks: list[Chunk]) -> dict:
    """문서 하나의 관계 그래프.

    보험사 → 상품 → 적용기간 → 특약 → 조항 → 개념(정의/지급/면책/감액) → 원문 근거
    """
    concepts = extract_definitions(chunks)
    relations = link_mentions(concepts, chunks)
    head = chunks[0] if chunks else None

    clauses: dict[str, dict] = {}
    for chunk in chunks:
        name = chunk.special_clause or "보통약관"
        entry = clauses.setdefault(
            name,
            {"name": name, "kind": chunk.clause_kind or "보통약관", "articles": []},
        )
        entry["articles"].append(
            {
                "article_no": _as_int(chunk.article_no),
                "article_title": chunk.article_title or None,
                "article_role": chunk.article_role or None,
                "page": chunk.page_start,
                "chunk_id": chunk.chunk_id,
            }
        )

    by_term: dict[str, dict] = {}
    for concept in concepts:
        entry = concept.to_full_dict()
        entry["relations"] = [
            r.to_dict() for r in relations if r.term == concept.raw_term
        ]
        by_term[concept.raw_term] = entry

    return {
        "document": {
            "insurer": head.insurer or None if head else None,
            "product_name": head.product_name or None if head else None,
            "product_code": head.product_code or None if head else None,
            "effective_from": head.effective_from or None if head else None,
            "effective_to": head.effective_to or None if head else None,
            "source": head.source if head else None,
        },
        "clauses": list(clauses.values()),
        "concepts": list(by_term.values()),
        "relations": [r.to_dict() for r in relations],
    }


def concept_schema(chunk: Chunk, concepts: list[Concept]) -> dict:
    """청크 하나에 등장하는 개념 목록.

    {"insurance_concepts": [{"raw_term": ..., "standard_term": ..., "category": ..., ...}]}
    """
    scope_ok = lambda c: not c.defined_in or not c.defined_in.special_clause or c.defined_in.special_clause == chunk.special_clause  # noqa: E731
    found = [c for c in concepts if scope_ok(c) and c.raw_term in chunk.text]
    return {"insurance_concepts": [c.to_dict() for c in found]}


# ---------------------------------------------------------------------------
# 질의 라우팅 (5차)
# ---------------------------------------------------------------------------

RE_KO_TOKEN = re.compile(r"[가-힣]{2,20}")


def index_entries(concepts: list[Concept]) -> list[dict]:
    """검색 인덱스에 저장할 최소 정보."""
    return [
        {
            "raw_term": c.raw_term,
            "standard_term": c.standard_term,
            "category": c.category,
            "sub_category": c.sub_category,
            "concept_type": c.concept_type,
            "special_clause": c.defined_in.special_clause if c.defined_in else "",
            "article_no": _as_int(c.defined_in.article_no) if c.defined_in else None,
            "page": c.defined_in.page if c.defined_in else 0,
        }
        for c in concepts
    ]


def route_query(query: str, entries: list[dict]) -> list[dict]:
    """질의에 등장하는 개념을 찾는다. 줄임말도 잡는다.

    "고액암 조건?" → "고액치료비암" (고·액·암이 순서대로 들어 있고 첫 글자가 같다)

    이게 없으면 사용자가 쓰는 말과 약관 용어가 달라서 영영 만나지 못한다.
    다만 **약관이 실제로 정의한 용어에만** 붙인다 — 임의로 동의어를 만들지 않는다.
    """
    tokens = RE_KO_TOKEN.findall(query)
    matched: list[dict] = []
    for entry in entries:
        term = entry.get("raw_term") or ""
        if not term:
            continue
        if term in query:
            matched.append(entry)
            continue
        if any(_abbreviates(token, term) for token in tokens):
            matched.append(entry)
    return matched


def _abbreviates(token: str, term: str) -> bool:
    """token 이 term 의 줄임말인가. 첫 글자가 같고, 글자들이 순서대로 들어 있어야 한다."""
    if len(token) < 2 or len(term) <= len(token) or token[0] != term[0]:
        return False
    position = 0
    for char in token:
        position = term.find(char, position)
        if position < 0:
            return False
        position += 1
    return True


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

_STOPWORDS = {"회사", "계약자", "피보험자", "보험수익자", "이 약관", "약관", "그", "이"}


def _clean_term(term: str) -> str:
    return " ".join(term.split()).strip(" ·,.")


def _is_definable(term: str) -> bool:
    if len(term) < 2 or len(term) > 40:
        return False
    if term in _STOPWORDS:
        return False
    return bool(re.search(r"[가-힣A-Za-z]", term))


def _as_int(value: str) -> int | str | None:
    if not value:
        return None
    return int(value) if value.isdigit() else value


def as_dicts(concepts: list[Concept]) -> list[dict]:
    return [asdict(c) for c in concepts]
