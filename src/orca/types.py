"""Orca AI 질문 라우팅 · 약관 판 특정에 쓰이는 공통 타입."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Source(Enum):
    """답변 근거로 쓰는 데이터 소스. 이번 범위는 2종."""

    MICKY = "micky"
    """보험 전문지식. 자체 RAG (데이터 적재 → 임베딩 → 검색 → LLM 생성)."""

    VELUGA = "veluga"
    """보험약관 자료. 벤더 API (검색 + 생성까지 벤더가 수행)."""


class QuestionType(Enum):
    """질문 의도 분류.

    분류는 LLM이 하고, 이 분류값으로부터 '어느 소스를 쓸지'와
    '가입 시점 특정이 필요한지'는 코드가 결정한다(ROUTING_TABLE).
    보상 판단이 걸린 영역이라 라우팅 자체는 결정적이어야 한다.
    """

    CONCEPT = "concept"
    """개념 · 이론 · 제도. 예) 「글라이드패스가 뭔가요?」"""

    SALES = "sales"
    """세일즈 화법 · 상담 전략. 예) 「변액연금 잘 팔려면?」"""

    PRODUCT_INFO = "product_info"
    """특정 상품의 구조 · 특징. 예) 「오토파일럿 변액연금 어떤 상품이야?」"""

    COVERAGE = "coverage"
    """보장 범위 · 지급 여부 · 면책. 보상 질문의 핵심.
    예) 「음주운전 사고인데 보험금 나오나요?」"""

    UNDERWRITING = "underwriting"
    """가입 · 인수 조건 · 고지의무. 예) 「고혈압 있어도 가입되나요?」"""

    PROCEDURE = "procedure"
    """청구 절차 · 필요 서류. 예) 「진단금 청구할 때 뭐 필요해요?」"""

    CONTRACT_VALUE = "contract_value"
    """개별 계약에 귀속된 값. 예) 「이 고객 진단금 얼마 나와요?」
    약관으로는 답할 수 없다(가입금액은 계약 정보 = Cloud DATA, 이번 범위 밖)."""


class VersionSensitivity(Enum):
    """가입 시점(= 적용 약관 판) 특정이 얼마나 필요한지."""

    REQUIRED = "required"
    """판이 다르면 답이 달라진다. 특정 없이 답하면 안 된다."""

    PREFERRED = "preferred"
    """특정하면 정확하지만, 없으면 일반론임을 밝히고 답할 수 있다."""

    NONE = "none"
    """약관 판과 무관하다."""


@dataclass(frozen=True)
class RoutingPolicy:
    """질문 유형별 처리 방침."""

    sources: tuple[Source, ...]
    version_sensitivity: VersionSensitivity
    note: str = ""


#: 질문 유형 → 소스 · 시점 민감도. 라우팅의 단일 기준점.
ROUTING_TABLE: dict[QuestionType, RoutingPolicy] = {
    QuestionType.CONCEPT: RoutingPolicy(
        sources=(Source.MICKY,),
        version_sensitivity=VersionSensitivity.NONE,
    ),
    QuestionType.SALES: RoutingPolicy(
        sources=(Source.MICKY,),
        version_sensitivity=VersionSensitivity.NONE,
        note="상품이 특정된 세일즈 질문은 분류 단계에서 MIXED 신호로 VELUGA가 함께 붙는다.",
    ),
    QuestionType.PRODUCT_INFO: RoutingPolicy(
        sources=(Source.VELUGA,),
        version_sensitivity=VersionSensitivity.PREFERRED,
        note="상품해설서 · 방법서. 개정으로 내용이 바뀔 수 있으나 개요 수준은 판 무관한 경우가 많다.",
    ),
    QuestionType.COVERAGE: RoutingPolicy(
        sources=(Source.VELUGA,),
        version_sensitivity=VersionSensitivity.REQUIRED,
        note="보상 질문. 지급사유와 면책을 함께 제시하고 근거 조항을 인용한다.",
    ),
    QuestionType.UNDERWRITING: RoutingPolicy(
        sources=(Source.VELUGA,),
        version_sensitivity=VersionSensitivity.REQUIRED,
        note="인수 기준은 개정 영향을 크게 받는다.",
    ),
    QuestionType.PROCEDURE: RoutingPolicy(
        sources=(Source.VELUGA,),
        version_sensitivity=VersionSensitivity.PREFERRED,
        note="사내 절차는 BumE_F 소관이나 이번 범위 밖이라 약관 기준으로만 답한다.",
    ),
    QuestionType.CONTRACT_VALUE: RoutingPolicy(
        sources=(),
        version_sensitivity=VersionSensitivity.NONE,
        note="이번 범위 밖. 약관은 '지급사유에 해당하는지'까지만 답한다. 금액은 계약 정보가 있어야 한다.",
    ),
}


@dataclass(frozen=True)
class PolicyEdition:
    """약관 판(개정 차수).

    보상은 '계약 체결 시점에 적용되던 판'을 따른다.
    최신 판으로 답하면 개정 전 가입 계약에 틀린 답을 주게 된다.
    """

    product_id: str
    edition_id: str
    label: str
    """FA에게 보여줄 이름. 예) 「3판 (2023.04 시행)」"""

    effective_from: date
    """시행일. 이 날짜 이후 체결된 계약에 적용된다."""

    effective_to: date | None = None
    """판매 종료일. None이면 현재 유효한 판."""

    def covers(self, contract_date: date) -> bool:
        if contract_date < self.effective_from:
            return False
        if self.effective_to is not None and contract_date > self.effective_to:
            return False
        return True


@dataclass(frozen=True)
class Product:
    """되묻기 선택지가 되는 상품."""

    product_id: str
    name: str
    insurer: str = ""
    category: str = ""
    """종별. 건강보험 · 운전자 · 실손의료 등. 되묻기에서 후보를 좁히는 데 쓴다."""

    editions: tuple[PolicyEdition, ...] = field(default_factory=tuple)

    indexed: bool = True
    """벤더 인덱스에 이 상품의 약관이 실제로 들어 있는지.

    상품 목록은 공시실에서도 얻을 수 있지만, 약관 검색은 벤더 인덱스에서만 된다.
    인덱스에 없는 상품을 선택지로 띄우면 FA가 고른 뒤에 「자료 없음」이 나온다.
    되묻기 후보는 이 값이 True인 상품으로만 구성한다.
    """
