"""Orca AI — 질문 라우팅과 약관 판 특정.

이번 범위는 두 가지다.
  1. 어느 질문에서 약관(VELUGA)을 써야 하는지 판단한다.        → routing
  2. 보상 질문에 필요한 가입 시점 = 적용 약관 판을 특정한다.    → versioning, clarify

검색과 생성 자체는 각 소스가 담당한다.
  · Micky  : 자체 RAG (적재 → 임베딩 → 검색 → LLM 생성)
  · VELUGA : 벤더 API (모델만 지정하면 생성 답변까지 반환)
"""

from .benefits import ENROLLMENT_CAVEAT, ENUMERATE_HINT, BenefitScope, scope_for
from .links import CustomerTermsLink, LinkSource, TermsLedger
from .customers import (
    CustomerCategory,
    CustomerDirectory,
    CustomerSummary,
)
from .coverage import (
    BenefitMatch,
    CoverageProfile,
    EnrolledBenefit,
    EnrolledContract,
    normalize_benefit_name,
)
from .catalog import (
    CatalogEntry,
    InMemoryProductCatalog,
    normalize_product_name,
)
from .clarify import (
    ConversationContext,
    NextAction,
    ProductCatalog,
    TurnPlan,
    plan_turn,
)
from .pricing import (
    UNPRICED,
    CostEstimate,
    TermsPricing,
    estimate_by_contract,
    estimate_by_product,
    products_within_budget,
)
from .requests import (
    RegistrationCandidate,
    RequestLog,
    RequestStatus,
    TermsRequest,
    select_within_budget,
)
from .routing import (
    Classification,
    RoutingDecision,
    build_classification_prompt,
    classify,
    parse_classification,
    route,
)
from .types import (
    ROUTING_TABLE,
    PolicyEdition,
    Product,
    QuestionType,
    Source,
    VersionSensitivity,
)
from .vendor_query import TermsQuery, build_queries, strip_pii
from .versioning import (
    ApproxDate,
    EditionResolution,
    EditionStatus,
    parse_approx_date,
    resolve_edition,
)

__all__ = [
    "ROUTING_TABLE",
    "ENROLLMENT_CAVEAT",
    "ENUMERATE_HINT",
    "UNPRICED",
    "ApproxDate",
    "BenefitMatch",
    "BenefitScope",
    "CoverageProfile",
    "CatalogEntry",
    "Classification",
    "ConversationContext",
    "CostEstimate",
    "CustomerCategory",
    "CustomerDirectory",
    "CustomerSummary",
    "CustomerTermsLink",
    "LinkSource",
    "TermsLedger",
    "EditionResolution",
    "EnrolledBenefit",
    "EnrolledContract",
    "EditionStatus",
    "InMemoryProductCatalog",
    "NextAction",
    "PolicyEdition",
    "Product",
    "ProductCatalog",
    "QuestionType",
    "RegistrationCandidate",
    "RequestLog",
    "RequestStatus",
    "RoutingDecision",
    "Source",
    "TermsPricing",
    "TermsQuery",
    "TermsRequest",
    "TurnPlan",
    "VersionSensitivity",
    "build_classification_prompt",
    "build_queries",
    "classify",
    "estimate_by_contract",
    "estimate_by_product",
    "normalize_benefit_name",
    "normalize_product_name",
    "parse_approx_date",
    "parse_classification",
    "plan_turn",
    "products_within_budget",
    "resolve_edition",
    "route",
    "scope_for",
    "select_within_budget",
    "strip_pii",
]
