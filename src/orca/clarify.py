"""한 턴에서 무엇을 할지 결정한다: 바로 답할지, 되물을지.

되묻기는 정확도를 올리지만 매번 하면 FA가 도구를 쓰지 않게 된다.
따라서 '되묻지 않아도 되는 경우'를 최대한 걸러내는 것이 이 모듈의 목적이다.

  1. 약관이 필요 없는 질문(Micky)은 되묻지 않는다.
  2. 상품에 판이 하나뿐이면 가입 시점을 묻지 않는다.
  3. 직전에 특정한 상품 · 시점은 세션 안에서 유지한다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from .benefits import BenefitScope, scope_for
from .coverage import BenefitMatch, CoverageProfile, EnrolledContract
from .pricing import UNPRICED, TermsPricing
from .requests import TermsRequest
from .routing import RoutingDecision
from .types import PolicyEdition, Product, QuestionType, Source, VersionSensitivity
from .versioning import (
    ApproxDate,
    EditionStatus,
    parse_approx_date,
    resolve_edition,
    sorted_editions,
)


class NextAction(Enum):
    SEARCH = "search"
    """특정 완료. 소스를 검색해 답변한다."""

    ASK_INSURER = "ask_insurer"
    """어느 보험사인지 먼저 되묻는다.

    공시실 전량을 적재하면 상품이 수천 건이 되어 상품명만으로는 좁혀지지 않는다.
    후보가 칩으로 보여줄 수 있는 수를 넘으면 보험사부터 고르게 한다.
    """

    ASK_PRODUCT = "ask_product"
    """어느 상품인지 되묻는다."""

    ASK_CONTRACT_DATE = "ask_contract_date"
    """가입 시점을 되묻는다. 상품에 판이 여럿일 때만 발생한다."""

    ASK_EXACT_DATE = "ask_exact_date"
    """가입 일자까지 되묻는다. 말한 시점이 판 경계에 걸쳐 있을 때."""

    ANSWER_GENERAL = "answer_general"
    """특정되지 않았지만 시점 민감도가 낮아 일반론으로 답한다.
    임의로 최신 판을 고르지 않으며, 일반론임을 답변에 명시한다."""

    NOT_ENROLLED = "not_enrolled"
    """보장분석 결과 해당 담보에 가입한 계약이 없다.

    약관을 뒤질 필요 없이 즉시 답할 수 있는 경우다.
    다만 조회 범위 밖 계약(오래된 계약 · 단독실손)이 있을 수 있으므로 단정하지 않는다."""

    OUT_OF_SCOPE = "out_of_scope"
    """약관으로 답할 수 없는 질문(개별 계약 값 등). 이번 범위 밖임을 안내한다."""

    NO_TERMS_AVAILABLE = "no_terms_available"
    """해당 시점의 약관이 색인에 없다. 추측하지 않고 없다고 답한다."""

    SHOW_ENROLLMENT = "show_enrollment"
    """금액 질문에 보장분석의 **가입금액**으로 답한다.

    약관으로는 금액을 답할 수 없지만(OUT_OF_SCOPE), 보장분석이 있으면
    가입금액은 조회된 사실이므로 보여줄 수 있다.
    지급액이 아니라 가입금액임을 반드시 함께 밝힌다."""

    CONFIRM_PAID_REQUEST = "confirm_paid_request"
    """등록되지 않은 약관을 확보하려면 **요청자 부담 비용**이 발생한다.
    금액을 고지하고 동의를 받는다. 동의 전에는 요청을 접수하지 않는다."""

    REQUEST_CANCELLED = "request_cancelled"
    """FA가 유료 확보 요청을 취소했다. 접수하지 않았음을 확인해 준다."""

    TERMS_NOT_REGISTERED = "terms_not_registered"
    """상품은 알지만 약관이 아직 등록되지 않았다.
    없다고 안내하되, 상품 · 가입 시점을 확정해 등록 요청으로 남긴다(TurnPlan.terms_request).

    비용이 발생하는 요청이면 이 상태에 오기 전에 CONFIRM_PAID_REQUEST로 동의를 받는다.
    이미 다른 FA가 요청해 진행 중인 약관은 비용 없이 바로 이 상태로 온다."""


@dataclass(frozen=True)
class ConversationContext:
    """상담 한 건 동안 유지되는 특정 상태.

    FA는 한 상담에서 같은 상품을 두고 여러 번 묻는다.
    (「음주운전은요?」 → 「그럼 무면허는요?」)
    매번 상품을 다시 묻지 않기 위해 여기에 들고 간다.
    """

    customer_id: str | None = None
    customer_name: str | None = None
    """상담 대상 고객. 보장분석 · 약관북에서 열고 들어온 경우 채워진다.

    확보 요청(TermsRequest)과 약관북 연결이 이 값으로 고객에 귀속된다.
    """

    insurer: str | None = None
    """상담 중인 계약의 보험사. 상품 후보를 좁히는 데 쓴다."""

    product_id: str | None = None
    product_name: str | None = None
    """카탈로그로 되찾을 수 없는 상품(= 마스터에도 없는 미등록 상품)을 위해 이름도 들고 간다."""

    contract_date: ApproxDate | None = None
    edition_id: str | None = None

    def with_customer(self, customer_id: str, customer_name: str = "") -> ConversationContext:
        if customer_id == self.customer_id:
            return self
        # 고객이 바뀌면 그 아래 전부(보험사 · 상품 · 판)를 버린다.
        return ConversationContext(customer_id=customer_id, customer_name=customer_name)

    def with_insurer(self, insurer: str) -> ConversationContext:
        if insurer == self.insurer:
            return self
        # 보험사가 바뀌면 그 아래 상품 · 판 정보는 버린다. 고객은 유지한다.
        return ConversationContext(
            customer_id=self.customer_id, customer_name=self.customer_name, insurer=insurer
        )

    def with_product(self, product: Product) -> ConversationContext:
        if product.product_id == self.product_id:
            return self
        # 상품이 바뀌면 그 상품에 매인 판 정보는 버린다. 고객·보험사는 다시 채운다.
        return ConversationContext(
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            insurer=product.insurer or self.insurer,
            product_id=product.product_id,
            product_name=product.name,
        )

    def with_contract_date(self, contract_date: ApproxDate) -> ConversationContext:
        return replace(self, contract_date=contract_date, edition_id=None)

    def with_edition(self, edition_id: str) -> ConversationContext:
        return replace(self, edition_id=edition_id)


class ProductCatalog(Protocol):
    """벤더 인덱스에 존재하는 상품 목록.

    되묻기 선택지의 원천이다. 자유 입력으로 두면 상품명 표기가 제각각이라
    검색이 흔들리므로, 여기서 나온 후보를 칩으로 제시해 고르게 한다.
    """

    def search(self, name: str, *, insurer: str | None = None) -> list[Product]:
        """상품 후보를 찾는다. 빈 문자열이면 대표 목록을 돌려준다."""

    def search_registry(self, name: str) -> list[Product]:
        """등록 여부와 무관하게 상품 마스터에서 찾는다.

        약관은 우선 일부만 등록하고 나머지는 요청을 받아 채워나가므로,
        「아는 상품인데 약관이 아직 없다」를 구분할 수 있어야 한다.
        """

    def get(self, product_id: str) -> Product | None: ...


@dataclass(frozen=True)
class Option:
    """되묻기 선택지 하나. 화면에서는 칩으로 그린다."""

    label: str
    value: str
    """선택 시 넘길 식별자. 상품이면 product_id, 판이면 edition_id."""

    available: bool = True
    """약관이 등록되어 있는지. False여도 목록에는 보여준다.

    상품명 자체가 보여야 FA가 자료에 있는 상품인지 알 수 있고,
    등록 요청도 정확한 상품으로 쌓인다. 화면에서는 「약관 준비중」으로 표시한다.
    """

    note: str = ""
    """보조 표기. 보험사명이나 시행일처럼 같은 이름을 구분해 주는 정보."""


@dataclass(frozen=True)
class TurnPlan:
    action: NextAction
    decision: RoutingDecision
    sources: tuple[Source, ...] = ()
    product: Product | None = None
    edition: PolicyEdition | None = None
    context: ConversationContext = ConversationContext()
    prompt: str = ""
    """FA에게 보여줄 되묻기 문구. 되묻지 않는 경우 빈 문자열."""

    options: tuple[Option, ...] = ()
    """되묻기 선택지(칩). 자유 입력만 받아야 하면 비어 있다."""

    terms_request: TermsRequest | None = None
    """등록되지 않은 약관에 대한 요청. 누적해서 다음 등록 배치의 우선순위로 쓴다."""

    offer_customer_link: bool = False
    """답변 뒤에 「이 건은 어느 고객 건인가요?」를 물어 장부에 남길지.

    보상 답변에서 약관 판까지 특정됐을 때만 제안한다. 특정되지 않은 답변을
    고객에 묶으면 잘못된 연결이 쌓인다.

    쌓인 연결은 다음 상담에서 그 고객의 약관 후보가 되어 되묻기를 줄인다.
    (`links.TermsLedger`)
    """

    matches: tuple[BenefitMatch, ...] = ()
    """보장분석에서 걸린 가입 담보. 어느 계약에 얼마씩 있는지 답변에 그대로 싣는다.

    **여러 계약에 걸쳐 있으면 전부 보여준다.** 하나만 답하면 FA가 청구를 놓친다.
    """

    contracts: tuple[EnrolledContract, ...] = ()
    """이번 답변이 대상으로 삼는 보유 계약. 각 계약의 상품 · 계약년월로 약관 판이 정해진다."""

    pending_terms: tuple[EnrolledContract, ...] = ()
    """걸리기는 하지만 약관이 아직 등록되지 않은 보유 계약.

    일부만 등록된 상태로 답하면 FA는 나머지도 확인된 줄 안다.
    「이 계약들은 약관이 없어 확인하지 못했다」를 반드시 함께 알린다.
    """

    @property
    def benefit_scope(self) -> BenefitScope:
        """담보를 하나만 볼지, 걸리는 것을 모두 볼지.

        FA가 담보를 지목하지 않았으면 해당 상황에 걸릴 수 있는 담보를 모두 제시한다.
        하나만 답하면 청구 가능한 담보를 놓친다.
        """
        return scope_for(self.decision.classification.benefit_mentioned)

    @property
    def needs_enrollment_caveat(self) -> bool:
        """답변에 「가입한 담보에 한함」 전제를 붙여야 하는지.

        약관에는 그 상품에서 가입할 수 있는 담보가 전부 들어 있고,
        실제 계약은 그중 일부만 가입한다. 계약별 가입 담보는 이번 범위 밖이므로
        지급 여부를 다루는 답변은 언제나 조건부여야 한다.
        """
        return self.action in (NextAction.SEARCH, NextAction.ANSWER_GENERAL) and (
            self.decision.classification.question_type
            in (QuestionType.COVERAGE, QuestionType.BENEFIT_TERM)
        )

    @property
    def option_labels(self) -> tuple[str, ...]:
        return tuple(option.label for option in self.options)

    @property
    def needs_user_input(self) -> bool:
        return self.action in (
            NextAction.ASK_INSURER,
            NextAction.ASK_PRODUCT,
            NextAction.ASK_CONTRACT_DATE,
            NextAction.ASK_EXACT_DATE,
        )


def plan_turn(
    decision: RoutingDecision,
    catalog: ProductCatalog,
    context: ConversationContext | None = None,
    *,
    pricing: TermsPricing = UNPRICED,
    pending_keys: set[tuple[str, str, int | None]] | None = None,
    coverage: CoverageProfile | None = None,
) -> TurnPlan:
    """라우팅 결과와 세션 상태로 이번 턴의 행동을 정한다.

    `pricing` — 초기 등록분에 없는 약관을 확보할 때 요청자가 부담할 비용 기준.
    `pending_keys` — 이미 접수돼 진행 중인 약관(`RequestLog.pending_keys()`).
    여기 있으면 중복 과금 없이 대기 안내만 한다.
    `coverage` — 보장분석 결과. 있으면 상품 · 가입 시점을 되묻지 않고
    실제 가입 담보로 답한다.
    """
    context = context or ConversationContext()
    classification = decision.classification

    if not decision.in_scope:
        # 금액 질문 자체는 범위 밖이지만, 보장분석이 있으면 「가입금액」은 조회된 사실이다.
        # 지급액이 아님을 밝히고 가입금액으로 답한다.
        if coverage is not None and classification.benefit_mentioned:
            matches = coverage.find_benefits(classification.benefit_mentioned)
            if matches:
                return TurnPlan(
                    action=NextAction.SHOW_ENROLLMENT,
                    decision=decision,
                    matches=matches,
                    contracts=tuple(dict.fromkeys(m.contract for m in matches)),
                    context=_with_coverage_customer(context, coverage),
                    prompt=(
                        "가입금액 기준으로 안내합니다. 실제 지급액은 지급사유 해당 여부와 "
                        "심사에 따라 달라지며, 가입금액과 같지 않을 수 있습니다."
                    ),
                )
        return TurnPlan(
            action=NextAction.OUT_OF_SCOPE,
            decision=decision,
            context=context,
            prompt=(
                "이 질문은 개별 계약의 값을 확인해야 답할 수 있습니다. "
                "약관으로는 지급 대상에 해당하는지까지만 확인할 수 있습니다."
            ),
        )

    # 약관을 쓰지 않는 질문은 특정 절차가 필요 없다.
    if not decision.uses_veluga:
        return TurnPlan(
            action=NextAction.SEARCH,
            decision=decision,
            sources=decision.sources,
            context=context,
        )

    # 약관을 쓰지만 판 특정이 필요 없는 질문(담보 용어 설명 등)도 되묻지 않는다.
    # 정의는 약관 공통이므로 전체 약관에서 일반 설명으로 답한다.
    # 상품이 언급됐고 하나로 떨어지면 검색 범위만 조용히 좁힌다 — 못 좁혀도 묻지 않는다.
    if decision.version_sensitivity is VersionSensitivity.NONE:
        product = None
        if classification.product_mentioned:
            candidates = catalog.search(classification.product_mentioned, insurer=context.insurer)
            # 등록된 상품일 때만 검색 범위를 좁힌다.
            # 미등록 상품으로 좁히면 벤더 인덱스에 없는 범위를 검색하게 된다.
            if len(candidates) == 1 and candidates[0].indexed:
                product = candidates[0]
                context = context.with_product(product)
        return TurnPlan(
            action=NextAction.SEARCH,
            decision=decision,
            sources=decision.sources,
            product=product,
            context=context,
        )

    # 보장분석이 붙어 있으면 상품 · 가입 시점을 되묻지 않는다.
    # 리포트에 계약별 상품명과 계약년월이 있으므로 특정이 이미 끝나 있다.
    if coverage is not None:
        planned = _plan_with_coverage(
            decision, coverage, context, catalog, pricing, pending_keys or set()
        )
        if planned is not None:
            return planned

    product, ask_product = _resolve_product(
        classification.product_mentioned, catalog, context, decision
    )

    if product is None:
        if decision.version_sensitivity is VersionSensitivity.REQUIRED:
            return ask_product
        # 시점 민감도가 낮으면 상품 없이 일반론으로 답할 수 있다.
        return TurnPlan(
            action=NextAction.ANSWER_GENERAL,
            decision=decision,
            sources=decision.sources,
            context=context,
            prompt="상품을 특정하지 않아 일반적인 내용으로 안내합니다. 상품마다 다를 수 있습니다.",
        )

    context = context.with_product(product)

    contract_date = context.contract_date
    if classification.period_mentioned:
        parsed = parse_approx_date(classification.period_mentioned)
        if parsed is not None:
            contract_date = parsed
            context = context.with_contract_date(parsed)

    # 약관이 아직 등록되지 않은 상품.
    # 바로 「없다」고 끝내지 않고 가입 시점까지 확정한 뒤 요청으로 남긴다.
    # 상품명만으로는 어느 판을 등록해야 할지 정해지지 않기 때문이다.
    if not product.indexed:
        return _plan_unregistered(
            decision, product, contract_date, context, pricing, pending_keys or set()
        )

    resolution = resolve_edition(product, contract_date)

    if resolution.is_settled and resolution.edition is not None:
        return TurnPlan(
            action=NextAction.SEARCH,
            decision=decision,
            sources=decision.sources,
            product=product,
            edition=resolution.edition,
            context=context.with_edition(resolution.edition.edition_id),
            # 상품과 판이 모두 특정된 보상 답변이다. 고객에 묶어 둘 수 있다.
            offer_customer_link=(
                decision.classification.question_type is QuestionType.COVERAGE
            ),
        )

    if resolution.status in (EditionStatus.NO_EDITIONS, EditionStatus.BEFORE_COVERAGE):
        return TurnPlan(
            action=NextAction.NO_TERMS_AVAILABLE,
            decision=decision,
            product=product,
            context=context,
            prompt=(
                f"{product.name}의 해당 시점 약관이 자료에 없습니다. "
                "확인되지 않은 내용으로 답하지 않겠습니다."
            ),
        )

    # 여기부터는 판이 여럿인데 시점이 확정되지 않은 경우다.
    if decision.version_sensitivity is not VersionSensitivity.REQUIRED:
        return TurnPlan(
            action=NextAction.ANSWER_GENERAL,
            decision=decision,
            sources=decision.sources,
            product=product,
            context=context,
            prompt=(
                f"{product.name}은 약관 개정 이력이 있습니다. "
                "가입 시점에 따라 달라질 수 있어 일반적인 내용으로 안내합니다."
            ),
        )

    if resolution.status is EditionStatus.NEEDS_EXACT_DATE:
        return TurnPlan(
            action=NextAction.ASK_EXACT_DATE,
            decision=decision,
            product=product,
            context=context,
            prompt=(
                "말씀하신 시점에 약관이 개정되었습니다. "
                "가입일이 정확히 언제인지 알려주시면 해당 약관으로 확인하겠습니다."
            ),
            options=_edition_ask_options(resolution.candidates),
        )

    editions = sorted_editions(product)
    options = _edition_ask_options(editions)
    if options:
        prompt = (
            f"{product.name}은 약관이 여러 차례 개정되었습니다. "
            "보상은 가입 시점의 약관을 따르므로, 언제 가입한 계약인지 알려주세요."
        )
    else:
        # 판이 너무 많아 목록을 보여줄 수 없다. 연·월 입력으로 받는다.
        first_year = editions[0].effective_from.year
        prompt = (
            f"{product.name}은 약관 개정이 잦아 가입 시점으로 확인합니다. "
            f"몇 년 몇 월에 가입한 계약인가요? ({first_year}년부터 조회 가능)"
        )
    return TurnPlan(
        action=NextAction.ASK_CONTRACT_DATE,
        decision=decision,
        product=product,
        context=context,
        prompt=prompt,
        options=options,
    )


def apply_choice(plan: TurnPlan, value: str) -> ConversationContext:
    """되묻기 선택지를 고른 결과를 컨텍스트에 반영한다.

    되묻기를 만들어 놓고 답을 받는 입구가 없으면 대화가 이어지지 않는다.
    화면에서 칩을 고르면 그 `Option.value`를 여기에 넘기고,
    돌려받은 컨텍스트로 다음 `plan_turn`을 호출한다.

    선택지 밖의 값은 무시한다. 임의의 값으로 컨텍스트가 오염되면
    엉뚱한 약관으로 답하게 된다.
    """
    if not any(option.value == value for option in plan.options):
        return plan.context

    if plan.action is NextAction.ASK_INSURER:
        return plan.context.with_insurer(value)

    if plan.action is NextAction.ASK_PRODUCT:
        # 값은 product_id다. 다음 턴에서 카탈로그로 되찾는다.
        return replace(plan.context, product_id=value, product_name=None)

    if plan.action in (NextAction.ASK_CONTRACT_DATE, NextAction.ASK_EXACT_DATE):
        # 값은 edition_id다. 판을 직접 고른 경우 시점 추정을 건너뛴다.
        return plan.context.with_edition(value)

    return plan.context


def apply_contract_date(plan: TurnPlan, text: str) -> ConversationContext:
    """가입 시점을 자유 입력으로 받은 결과를 반영한다.

    판이 많아 칩을 띄우지 않는 상품(실손 등)에서는 이 경로로만 답이 들어온다.
    해석되지 않는 입력은 컨텍스트를 바꾸지 않는다 — 다시 물어야 한다.
    """
    parsed = parse_approx_date(text)
    if parsed is None:
        return plan.context
    return plan.context.with_contract_date(parsed)


def _with_coverage_customer(
    context: ConversationContext, coverage: CoverageProfile
) -> ConversationContext:
    """보장분석의 대상 고객을 대화 컨텍스트에 채운다.

    이 값이 있어야 확보 요청과 약관북 연결이 고객에 귀속된다.
    """
    if not coverage.customer_id or context.customer_id == coverage.customer_id:
        return context
    return replace(
        context,
        customer_id=coverage.customer_id,
        customer_name=coverage.customer_name,
    )


def _plan_with_coverage(
    decision: RoutingDecision,
    coverage: CoverageProfile,
    context: ConversationContext,
    catalog: ProductCatalog,
    pricing: TermsPricing,
    pending: set[tuple[str, str, int | None]],
) -> TurnPlan | None:
    """보장분석으로 답할 수 있으면 그 계획을 돌려준다. 아니면 None.

    되묻기를 건너뛰는 근거는 리포트 자체다.
    계약별 상품명과 계약년월이 있으므로 약관 판이 이미 정해진다.

    다만 **계약이 특정됐다고 약관이 등록된 것은 아니다.**
    보장분석은 계약만 알려주고 약관은 벤더에 따로 등록해야 하므로,
    미등록이면 검색으로 보내지 않고 확보 요청 경로로 넘긴다.
    """
    classification = decision.classification
    context = _with_coverage_customer(context, coverage)

    # FA가 상품을 지목했으면 그 계약으로 좁힌다.
    if classification.product_mentioned:
        contract = coverage.find_contract(classification.product_mentioned)
        contracts = (contract,) if contract else ()
    else:
        contracts = coverage.contracts

    if not contracts:
        # 보유 계약에 없는 상품을 물었다. 일반 약관 경로로 넘긴다.
        return None

    benefit = classification.benefit_mentioned

    if benefit:
        matches = tuple(m for m in coverage.find_benefits(benefit) if m.contract in contracts)
        if not matches:
            # 가입한 담보가 없다. 약관을 뒤질 필요 없이 바로 답한다.
            # 다만 조회 범위 밖 계약이 있을 수 있으므로 단정하지 않는다.
            return TurnPlan(
                action=NextAction.NOT_ENROLLED,
                decision=decision,
                contracts=contracts,
                context=context,
                prompt=(
                    f"보장분석 기준으로 「{benefit}」 담보에 가입한 계약이 없습니다. "
                    "조회되지 않는 계약(오래된 계약 · 단독실손 등)이 있을 수 있으니 "
                    "증권으로 한 번 더 확인해 주세요."
                ),
            )
        contracts = tuple(dict.fromkeys(m.contract for m in matches))
    else:
        matches = ()

    # 계약은 정해졌지만 그 약관이 벤더에 등록돼 있는지는 별개다.
    registered, missing = _split_by_registration(contracts, catalog)

    if not registered:
        # 걸린 계약의 약관이 하나도 등록돼 있지 않다. 확보 요청으로 넘긴다.
        return _plan_contract_terms_request(
            decision, missing[0], context, pricing, pending, coverage
        )

    return TurnPlan(
        action=NextAction.SEARCH,
        decision=decision,
        sources=decision.sources,
        matches=tuple(m for m in matches if m.contract in registered),
        contracts=registered,
        context=context,
        # 보장분석으로 답한 건도 약관북에 남긴다. 이미 고객이 정해져 있다.
        offer_customer_link=(
            classification.question_type is QuestionType.COVERAGE and bool(context.customer_id)
        ),
        # 일부만 등록된 경우 나머지를 확보 대상으로 알린다.
        pending_terms=missing,
    )


def _split_by_registration(
    contracts: tuple[EnrolledContract, ...],
    catalog: ProductCatalog,
) -> tuple[tuple[EnrolledContract, ...], tuple[EnrolledContract, ...]]:
    """보유 계약을 약관 등록 여부로 가른다."""
    registered: list[EnrolledContract] = []
    missing: list[EnrolledContract] = []
    for contract in contracts:
        found = catalog.search(contract.product_name, insurer=contract.insurer or None)
        if any(p.indexed for p in found):
            registered.append(contract)
        else:
            missing.append(contract)
    return tuple(registered), tuple(missing)


def _plan_contract_terms_request(
    decision: RoutingDecision,
    contract: EnrolledContract,
    context: ConversationContext,
    pricing: TermsPricing,
    pending: set[tuple[str, str, int | None]],
    coverage: CoverageProfile,
) -> TurnPlan:
    """보유 계약의 약관이 미등록일 때의 확보 요청.

    보장분석이 상품과 계약년월을 이미 알려주므로 되물을 것이 없다.
    바로 비용 고지 단계로 간다.
    """
    product = Product(
        product_id=f"{UNREGISTERED_PREFIX}{contract.insurer}:{contract.product_name}",
        name=contract.product_name,
        insurer=contract.insurer,
        indexed=False,
    )
    plan = _plan_unregistered(
        decision, product, contract.contract_start, context, pricing, pending
    )
    if plan.terms_request is None:
        return plan
    return replace(
        plan,
        terms_request=replace(
            plan.terms_request,
            customer_id=coverage.customer_id,
            customer_name=coverage.customer_name,
        ),
    )


#: 상품 마스터에도 없는 상품에 붙이는 식별자 접두어.
UNREGISTERED_PREFIX = "unregistered:"

#: 이 수를 넘으면 상품이 아니라 보험사부터 되묻는다.
#: 칩으로 한 화면에 보여줄 수 있는 수를 기준으로 잡았다.
_INSURER_NARROWING_THRESHOLD = 8

#: 판 선택지를 칩으로 보여줄 수 있는 최대 수.
#: 실손처럼 개정이 잦은 상품은 판이 150개를 넘을 수 있다. 그 목록을 칩으로
#: 늘어놓는 것은 성립하지 않으므로, 넘으면 가입 연·월을 입력으로 받고
#: 날짜 → 판 변환은 resolve_edition()이 뒤에서 처리한다.
EDITION_CHIP_LIMIT = 6


def _edition_ask_options(editions: tuple[PolicyEdition, ...]) -> tuple[Option, ...]:
    """가입 시점 되묻기에 붙일 선택지. 판이 많으면 칩을 포기하고 입력만 받는다."""
    if len(editions) > EDITION_CHIP_LIMIT:
        return ()
    return _edition_options(editions)


def _product_options(products: list[Product]) -> tuple[Option, ...]:
    """상품 선택지.

    약관이 없는 상품도 목록에 넣되 `available=False`로 표시한다.
    화면에서는 「약관 준비중」으로 그리고, 골라도 등록 요청 경로로 이어진다.
    """
    return tuple(
        Option(
            label=product.name,
            value=product.product_id,
            available=product.indexed,
            note=product.insurer,
        )
        for product in products
    )


def _edition_options(editions: tuple[PolicyEdition, ...]) -> tuple[Option, ...]:
    """약관 판 선택지. 시행일을 함께 보여 어느 시기 약관인지 알 수 있게 한다."""
    return tuple(
        Option(
            label=edition.label,
            value=edition.edition_id,
            note=f"{edition.effective_from:%Y.%m.%d} 시행",
        )
        for edition in editions
    )


def _unregistered_product(name: str) -> Product:
    """마스터에 없는 상품을 임시 Product로 감싼다.

    이후 흐름(가입 시점 확인 → 등록 요청)을 등록된 상품과 같은 경로로 태우기 위한 것이다.
    """
    return Product(product_id=f"{UNREGISTERED_PREFIX}{name}", name=name, indexed=False)


def _search_registry(catalog: ProductCatalog, name: str) -> list[Product]:
    """상품 마스터 조회. 마스터를 아직 붙이지 않은 카탈로그도 있으므로 없으면 건너뛴다."""
    search_registry = getattr(catalog, "search_registry", None)
    if not callable(search_registry):
        return []
    return list(search_registry(name) or [])


def _plan_unregistered(
    decision: RoutingDecision,
    product: Product,
    contract_date: ApproxDate | None,
    context: ConversationContext,
    pricing: TermsPricing = UNPRICED,
    pending: set[tuple[str, str, int | None]] | None = None,
) -> TurnPlan:
    """약관이 등록되지 않은 상품에 대한 처리.

    가입 시점을 먼저 확정한다. 등록 요청이 「상품명」이 아니라
    「상품 + 판」 단위여야 무엇을 등록할지 정해지기 때문이고,
    비용도 판 단위로 발생하므로 금액을 고지하려면 판이 정해져 있어야 한다.
    """
    pending = pending or set()
    editions = sorted_editions(product)

    if contract_date is None and decision.version_sensitivity is VersionSensitivity.REQUIRED:
        return TurnPlan(
            action=NextAction.ASK_CONTRACT_DATE,
            decision=decision,
            product=product,
            context=context,
            prompt=(
                f"{product.name}은 아직 약관이 등록되어 있지 않습니다. "
                "언제 가입한 계약인지 알려주시면 해당 약관을 확보 요청으로 남기겠습니다."
            ),
            # 판 정보가 없으면 자유 입력으로, 많으면 역시 자유 입력으로 받는다.
            options=_edition_ask_options(editions),
        )

    resolution = resolve_edition(product, contract_date)
    edition = resolution.edition if resolution.is_settled else None

    request = TermsRequest(
        product_name=product.name,
        insurer=product.insurer,
        product_id=(
            None if product.product_id.startswith(UNREGISTERED_PREFIX) else product.product_id
        ),
        contract_date=contract_date,
        edition_label=edition.label if edition else None,
        question=decision.classification.question,
    )

    # 같은 약관을 다른 FA가 이미 요청했다면 비용을 다시 받지 않는다.
    # 등록된 약관은 전사가 함께 쓰므로 같은 것을 두 번 사는 셈이 된다.
    if request.key in pending:
        return TurnPlan(
            action=NextAction.TERMS_NOT_REGISTERED,
            decision=decision,
            product=product,
            edition=edition,
            context=context,
            prompt=(
                f"{product.name}의 약관은 이미 다른 요청으로 확보가 진행 중입니다. "
                "추가 비용 없이 등록되면 알려드리겠습니다."
            ),
            terms_request=request,
        )

    # 초기 등록분에 없는 약관이다. 비용이 발생하므로 동의를 먼저 받는다.
    amount = pricing.price_for(1)
    where = f"{product.name} · {edition.label}" if edition else product.name

    if amount is None:
        # 단가 미확정. 금액 없이 「비용이 발생합니다」로 동의를 받으면 백지 동의가 된다.
        # 이 단계에서는 **요청 의사만** 받고, 금액은 확인해서 따로 안내한다.
        prompt = (
            f"{where} 약관은 등록되어 있지 않아 확인할 수 없습니다. "
            "확보에는 등록 비용이 발생할 수 있습니다. "
            "요청을 남기시면 비용과 진행 여부를 확인해 안내드리겠습니다."
        )
        options = (
            Option(label="확보 요청하기", value="confirm", note="비용 확인 후 안내"),
            Option(label="취소", value="cancel"),
        )
    else:
        prompt = (
            f"{where} 약관은 등록되어 있지 않아 확인할 수 없습니다. "
            f"확보를 요청하시면 {pricing.format(1)}의 등록 비용이 발생합니다. "
            "요청하시겠어요?"
        )
        options = (
            Option(label=f"요청하기 ({pricing.format(1)})", value="confirm"),
            Option(label="취소", value="cancel"),
        )

    return TurnPlan(
        action=NextAction.CONFIRM_PAID_REQUEST,
        decision=decision,
        product=product,
        edition=edition,
        context=context,
        prompt=prompt,
        options=options,
        terms_request=replace(request, billable=True, price=amount),
    )


def resolve_paid_request(plan: TurnPlan, value: str, *, requester_id: str = "") -> TurnPlan:
    """유료 확보 요청의 동의 · 취소를 처리한다.

    `CONFIRM_PAID_REQUEST`에 대한 응답을 받는 입구다.
    동의해야 비로소 접수되며, 그전까지 `terms_request`는 적재 대상이 아니다.
    """
    if plan.action is not NextAction.CONFIRM_PAID_REQUEST:
        return plan

    if value != "confirm":
        return replace(
            plan,
            action=NextAction.REQUEST_CANCELLED,
            prompt="확보 요청을 접수하지 않았습니다. 비용도 발생하지 않습니다.",
            options=(),
            terms_request=None,
        )

    request = plan.terms_request
    if request is not None and requester_id:
        request = replace(request, requester_id=requester_id)
    if request is not None and plan.context.customer_id:
        request = replace(
            request,
            customer_id=plan.context.customer_id,
            customer_name=plan.context.customer_name or "",
        )

    name = plan.product.name if plan.product else "해당 상품"
    return replace(
        plan,
        action=NextAction.TERMS_NOT_REGISTERED,
        prompt=(
            f"{name}의 약관 확보 요청을 접수했습니다. "
            "확인되지 않은 내용으로 답하지 않습니다. 등록이 끝나면 알려드리겠습니다."
        ),
        options=(),
        terms_request=request,
    )


def _resolve_product(
    mentioned: str | None,
    catalog: ProductCatalog,
    context: ConversationContext,
    decision: RoutingDecision,
) -> tuple[Product | None, TurnPlan]:
    """상품을 특정한다. 실패하면 되묻기 계획을 함께 돌려준다.

    되묻기 계획은 호출부에서 시점 민감도를 보고 쓸지 말지 정한다.
    """
    placeholder = TurnPlan(action=NextAction.ASK_PRODUCT, decision=decision, context=context)

    if mentioned:
        candidates = catalog.search(mentioned, insurer=context.insurer)
        if not candidates:
            # 없으면 상품 마스터까지 넓힌다. 여기서 걸리면 「아는 상품인데 약관만 없는」 경우다.
            candidates = _search_registry(catalog, mentioned)

        if len(candidates) == 1:
            return candidates[0], placeholder

        # 후보가 칩으로 보여줄 수 있는 수를 넘으면 보험사부터 좁힌다.
        ask_insurer = _maybe_ask_insurer(mentioned, catalog, context, decision)
        if ask_insurer is not None:
            return None, ask_insurer

        if candidates:
            return None, replace(
                placeholder,
                prompt=f"「{mentioned}」에 해당하는 상품이 여럿입니다. 어느 상품일까요?",
                options=_product_options(candidates),
            )

        # 마스터에도 없는 상품. 「모른다」로 끝내면 등록 요청이 쌓이지 않으므로,
        # 미등록 상품으로 보고 요청 경로를 태운다. 오타는 요청 건수가 낮아 우선순위에서 밀린다.
        return _unregistered_product(mentioned), placeholder

    # 질문에 상품이 없으면 세션에 남아 있는 직전 상품을 쓴다.
    if context.product_id:
        product = catalog.get(context.product_id)
        if product is None and context.product_name:
            # 카탈로그에 없는 미등록 상품을 되묻는 중이었던 경우.
            product = _unregistered_product(context.product_name)
        if product is not None:
            return product, placeholder

    ask_insurer = _maybe_ask_insurer("", catalog, context, decision)
    if ask_insurer is not None:
        return None, ask_insurer

    return None, replace(
        placeholder,
        context=context,
        prompt="상품에 따라 내용이 다릅니다. 어느 상품 기준으로 확인할까요?",
        options=_product_options(catalog.search("", insurer=context.insurer)),
    )


def _maybe_ask_insurer(
    mentioned: str,
    catalog: ProductCatalog,
    context: ConversationContext,
    decision: RoutingDecision,
) -> TurnPlan | None:
    """후보가 너무 많으면 보험사부터 묻는 계획을 돌려준다.

    공시실 상품명을 전량 적재하면 상품이 수천 건이 된다. 그 상태에서
    상품 칩만 8개 잘라 보여주면 FA가 찾는 상품이 그 안에 없을 확률이 높다.
    보험사를 먼저 고르면 후보가 한 자릿수로 줄어든다.
    """
    if context.insurer:
        return None

    count_matches = getattr(catalog, "count_matches", None)
    insurers_of = getattr(catalog, "insurers", None)
    if not callable(count_matches) or not callable(insurers_of):
        return None

    if count_matches(mentioned) <= _INSURER_NARROWING_THRESHOLD:
        return None

    insurers = list(insurers_of() or [])
    if len(insurers) < 2:
        return None

    prompt = (
        f"「{mentioned}」로 검색되는 상품이 많습니다. 어느 보험사 상품일까요?"
        if mentioned
        else "상품에 따라 내용이 다릅니다. 어느 보험사 상품일까요?"
    )
    return TurnPlan(
        action=NextAction.ASK_INSURER,
        decision=decision,
        context=context,
        prompt=prompt,
        options=tuple(Option(label=name, value=name) for name in insurers),
    )
