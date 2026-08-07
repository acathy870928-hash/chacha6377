"""약관·상품·FAQ 검색 (경량 키워드 스코어링 기반).

외부 벡터 DB 없이 동작하도록 형태소 분석 대신 문자 n-gram + 키워드 매칭을
사용한다. 한국어 질의에서 조사가 붙어도(예: "암보험은") 어간이 매칭되도록
2~3-gram 을 함께 본다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .config import DATA_DIR

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _ngrams(token: str, sizes: tuple[int, ...] = (2, 3)) -> set[str]:
    grams: set[str] = set()
    for n in sizes:
        if len(token) >= n:
            grams.update(token[i : i + n] for i in range(len(token) - n + 1))
    return grams


def _expand(text: str) -> set[str]:
    """토큰 + n-gram 집합. 조사·어미 변형에 어느 정도 견디게 한다."""
    terms: set[str] = set()
    for token in _tokenize(text):
        terms.add(token)
        terms.update(_ngrams(token))
    return terms


@dataclass
class Document:
    """검색 대상 문서 한 건."""

    doc_id: str
    kind: str  # "product" | "faq"
    title: str
    body: str
    keywords: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def searchable(self) -> str:
        return f"{self.title} {self.body} {' '.join(self.keywords)}"


@dataclass
class SearchHit:
    document: Document
    score: float


def _load_json(name: str) -> Any:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_products() -> list[dict[str, Any]]:
    return _load_json("products.json")


@lru_cache(maxsize=1)
def load_faqs() -> list[dict[str, Any]]:
    return _load_json("faq.json")


@lru_cache(maxsize=1)
def load_claim_guides() -> dict[str, Any]:
    return _load_json("claim_guides.json")


def get_product(product_id: str) -> dict[str, Any] | None:
    for product in load_products():
        if product["id"] == product_id:
            return product
    return None


@lru_cache(maxsize=1)
def _corpus() -> list[Document]:
    docs: list[Document] = []

    for product in load_products():
        body_parts = [
            product["summary"],
            "보장내용: " + " / ".join(product["coverage"]),
            "보장하지 않는 사항: " + " / ".join(product["exclusions"]),
            f"갱신·만기: {product['renewal']}",
            f"가입연령: 만 {product['min_age']}세 ~ {product['max_age']}세",
        ]
        if product["waiting_period_days"]:
            body_parts.append(f"면책기간: {product['waiting_period_days']}일")
        docs.append(
            Document(
                doc_id=product["id"],
                kind="product",
                title=product["name"],
                body="\n".join(body_parts),
                keywords=product["keywords"],
                raw=product,
            )
        )

    for faq in load_faqs():
        docs.append(
            Document(
                doc_id=faq["id"],
                kind="faq",
                title=faq["question"],
                body=faq["answer"],
                keywords=faq["keywords"],
                raw=faq,
            )
        )

    return docs


def search(query: str, limit: int = 3) -> list[SearchHit]:
    """질의와 관련된 문서를 점수 순으로 반환한다."""
    query_terms = _expand(query)
    if not query_terms:
        return []

    hits: list[SearchHit] = []
    for doc in _corpus():
        # 키워드 정확 매칭에 큰 가중치, 본문 n-gram 겹침에 작은 가중치를 준다.
        keyword_terms = _expand(" ".join(doc.keywords))
        title_terms = _expand(doc.title)
        body_terms = _expand(doc.searchable)

        score = (
            3.0 * len(query_terms & keyword_terms)
            + 2.0 * len(query_terms & title_terms)
            + 1.0 * len(query_terms & body_terms)
        )
        # 문서 길이에 따른 편향 보정
        score /= 1 + len(body_terms) ** 0.5
        if score > 0:
            hits.append(SearchHit(document=doc, score=score))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def format_hits(hits: list[SearchHit]) -> str:
    """검색 결과를 모델이 인용하기 좋은 형태의 텍스트로 만든다."""
    if not hits:
        return "관련 약관·FAQ 문서를 찾지 못했습니다."

    blocks = []
    for hit in hits:
        doc = hit.document
        label = "상품/약관" if doc.kind == "product" else "FAQ"
        blocks.append(f"[{label} · 출처ID: {doc.doc_id}]\n{doc.title}\n{doc.body}")
    return "\n\n---\n\n".join(blocks)
