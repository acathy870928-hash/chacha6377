"""되묻기에 답이 들어오는 입구 — 대화가 실제로 이어지는지 검증.

되묻기를 만들어 놓고 응답을 받는 경로가 없으면 플로우가 끊긴다.
칩 선택 · 자유 입력 · 유료 요청 동의를 각각 한 바퀴 돌려본다.
"""

import pytest

from orca.clarify import (
    NextAction,
    apply_choice,
    apply_contract_date,
    plan_turn,
    resolve_paid_request,
)
from orca.routing import Classification, route
from orca.types import QuestionType


def _plan(catalog, context=None, question_type=QuestionType.COVERAGE, **kwargs):
    decision = route(Classification(question_type=question_type, **kwargs))
    return plan_turn(decision, catalog, context)


class TestInsurerThenProduct:
    def test_보험사를_고르면_상품을_묻는다(self, catalog):
        first = _plan(catalog)
        assert first.action is NextAction.ASK_INSURER

        context = apply_choice(first, first.options[0].value)
        assert context.insurer == first.options[0].value

        second = _plan(catalog, context=context)
        assert second.action is NextAction.ASK_PRODUCT

    def test_선택지_밖의_값은_무시한다(self, catalog):
        # 임의 값으로 컨텍스트가 오염되면 엉뚱한 약관으로 답하게 된다.
        plan = _plan(catalog)
        assert plan.action is NextAction.ASK_INSURER
        assert apply_choice(plan, "없는보험사").insurer is None


class TestProductChoice:
    def test_상품을_고르면_다음_턴이_그_상품으로_간다(self, catalog):
        first = _plan(catalog, product_mentioned="더드림 암보험")
        assert first.action is NextAction.ASK_PRODUCT

        chosen = next(o for o in first.options if o.label == "더드림 암보험 플러스")
        context = apply_choice(first, chosen.value)

        second = _plan(catalog, context=context)
        assert second.product.product_id == "cancer-b"


class TestContractDate:
    def test_판을_직접_고르면_확정된다(self, catalog):
        first = _plan(catalog, product_mentioned="무배당 운전자보험")
        assert first.action is NextAction.ASK_CONTRACT_DATE

        context = apply_choice(first, first.options[1].value)
        assert context.edition_id == "driver-2"

    def test_연월을_입력하면_반영된다(self, catalog):
        first = _plan(catalog, product_mentioned="무배당 운전자보험")
        context = apply_contract_date(first, "2021년 6월")

        second = _plan(catalog, context=context, product_mentioned="무배당 운전자보험")
        assert second.action is NextAction.SEARCH
        assert second.edition.edition_id == "driver-2"

    def test_해석되지_않는_입력은_컨텍스트를_바꾸지_않는다(self, catalog):
        # 다시 물어야 하므로 이전 상태를 유지한다.
        first = _plan(catalog, product_mentioned="무배당 운전자보험")
        assert apply_contract_date(first, "기억 안 나요").contract_date is None

    def test_판이_많은_상품도_입력으로_확정된다(self, catalog):
        first = _plan(catalog, product_mentioned="실손의료비보장보험")
        assert first.options == ()  # 칩이 없다 — 입력이 유일한 경로다

        context = apply_contract_date(first, "2015년 3월")
        second = _plan(catalog, context=context, product_mentioned="실손의료비보장보험")
        assert second.action is NextAction.SEARCH


class TestPaidRequest:
    @pytest.fixture
    def confirm_plan(self, catalog):
        return _plan(
            catalog,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
            question="골절 진단금 나오나요?",
        )

    def test_동의해야_접수된다(self, confirm_plan):
        assert confirm_plan.action is NextAction.CONFIRM_PAID_REQUEST

        accepted = resolve_paid_request(confirm_plan, "confirm", requester_id="fa-1")
        assert accepted.action is NextAction.TERMS_NOT_REGISTERED
        assert accepted.terms_request.requester_id == "fa-1"
        assert "접수했습니다" in accepted.prompt

    def test_취소하면_접수되지_않는다(self, confirm_plan):
        cancelled = resolve_paid_request(confirm_plan, "cancel")
        assert cancelled.action is NextAction.REQUEST_CANCELLED
        assert cancelled.terms_request is None
        assert "비용도 발생하지 않습니다" in cancelled.prompt

    def test_동의_전에는_선택지가_남아_있다(self, confirm_plan):
        assert confirm_plan.options
        assert resolve_paid_request(confirm_plan, "confirm").options == ()

    def test_다른_상태에는_영향이_없다(self, catalog):
        plan = _plan(catalog, question_type=QuestionType.CONCEPT)
        assert resolve_paid_request(plan, "confirm") is plan
