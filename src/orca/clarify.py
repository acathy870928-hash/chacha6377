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

from .routing import RoutingDecision
from .types import PolicyEdition, Product, Source, VersionSensitivity
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

    ASK_PRODUCT = "ask_product"
    """어느 상품인지 되묻는다."""

    ASK_CONTRACT_DATE = "ask_contract_date"
    """가입 시점을 되묻는다. 상품에 판이 여럿일 때만 발생한다."""

    ASK_EXACT_DATE = "ask_exact_date"
    """가입 일자까지 되묻는다. 말한 시점이 판 경계에 걸쳐 있을 때."""

    ANSWER_GENERAL = "answer_general"
    """특정되지 않았지만 시점 민감도가 낮아 일반론으로 답한다.
    임의로 최신 판을 고르지 않으며, 일반론임을 답변에 명시한다."""

    OUT_OF_SCOPE = "out_of_scope"
    """약관으로 답할 수 없는 질문(개별 계약 값 등). 이번 범위 밖임을 안내한다."""

    NO_TERMS_AVAILABLE = "no_terms_available"
    """해당 시점의 약관이 색인에 없다. 추측하지 않고 없다고 답한다."""


@dataclass(frozen=True)
class ConversationContext:
    """상담 한 건 동안 유지되는 특정 상태.

    FA는 한 상담에서 같은 상품을 두고 여러 번 묻는다.
    (「음주운전은요?」 → 「그럼 무면허는요?」)
    매번 상품을 다시 묻지 않기 위해 여기에 들고 간다.
    """

    product_id: str | None = None
    contract_date: ApproxDate | None = None
    edition_id: str | None = None

    def with_product(self, product_id: str) -> ConversationContext:
        if product_id == self.product_id:
            return self
        # 상품이 바뀌면 그 상품에 매인 판 정보는 버린다.
        return ConversationContext(product_id=product_id)

    def with_contract_date(self, contract_date: ApproxDate) -> ConversationContext:
        return replace(self, contract_date=contract_date, edition_id=None)

    def with_edition(self, edition_id: str) -> ConversationContext:
        return replace(self, edition_id=edition_id)


class ProductCatalog(Protocol):
    """벤더 인덱스에 존재하는 상품 목록.

    되묻기 선택지의 원천이다. 자유 입력으로 두면 상품명 표기가 제각각이라
    검색이 흔들리므로, 여기서 나온 후보를 칩으로 제시해 고르게 한다.
    """

    def search(self, name: str) -> list[Product]:
        """이름으로 상품 후보를 찾는다. 빈 문자열이면 대표 목록을 돌려준다."""

    def get(self, product_id: str) -> Product | None: ...


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

    options: tuple[str, ...] = ()
    """되묻기 선택지(칩). 자유 입력만 받아야 하면 비어 있다."""

    @property
    def needs_user_input(self) -> bool:
        return self.action in (
            NextAction.ASK_PRODUCT,
            NextAction.ASK_CONTRACT_DATE,
            NextAction.ASK_EXACT_DATE,
        )


def plan_turn(
    decision: RoutingDecision,
    catalog: ProductCatalog,
    context: ConversationContext | None = None,
) -> TurnPlan:
    """라우팅 결과와 세션 상태로 이번 턴의 행동을 정한다."""
    context = context or ConversationContext()
    classification = decision.classification

    if not decision.in_scope:
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

    context = context.with_product(product.product_id)

    contract_date = context.contract_date
    if classification.period_mentioned:
        parsed = parse_approx_date(classification.period_mentioned)
        if parsed is not None:
            contract_date = parsed
            context = context.with_contract_date(parsed)

    resolution = resolve_edition(product, contract_date)

    if resolution.is_settled and resolution.edition is not None:
        return TurnPlan(
            action=NextAction.SEARCH,
            decision=decision,
            sources=decision.sources,
            product=product,
            edition=resolution.edition,
            context=context.with_edition(resolution.edition.edition_id),
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
            options=tuple(e.label for e in resolution.candidates),
        )

    return TurnPlan(
        action=NextAction.ASK_CONTRACT_DATE,
        decision=decision,
        product=product,
        context=context,
        prompt=(
            f"{product.name}은 약관이 여러 차례 개정되었습니다. "
            "보상은 가입 시점의 약관을 따르므로, 언제 가입한 계약인지 알려주세요."
        ),
        options=tuple(e.label for e in sorted_editions(product)),
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
        candidates = catalog.search(mentioned)
        if len(candidates) == 1:
            return candidates[0], placeholder
        if candidates:
            return None, replace(
                placeholder,
                context=context,
                prompt=f"「{mentioned}」에 해당하는 상품이 여럿입니다. 어느 상품일까요?",
                options=tuple(p.name for p in candidates),
            )
        return None, replace(
            placeholder,
            context=context,
            prompt=f"「{mentioned}」에 해당하는 상품 약관을 찾지 못했습니다. 상품명을 확인해 주세요.",
        )

    # 질문에 상품이 없으면 세션에 남아 있는 직전 상품을 쓴다.
    if context.product_id:
        product = catalog.get(context.product_id)
        if product is not None:
            return product, placeholder

    return None, replace(
        placeholder,
        context=context,
        prompt="상품에 따라 내용이 다릅니다. 어느 상품 기준으로 확인할까요?",
        options=tuple(p.name for p in catalog.search("")),
    )
