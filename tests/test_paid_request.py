"""요청자 부담 약관 확보 — 비용 고지와 동의.

초기 등록분(회사 부담)에 없는 약관은 요청한 FA가 비용을 부담한다.
따라서 접수 전에 금액을 고지하고 동의를 받아야 하며,
같은 약관을 이미 다른 FA가 요청했다면 다시 받지 않는다.
"""

import pytest

from orca.clarify import ConversationContext, NextAction, plan_turn
from orca.pricing import UNPRICED, TermsPricing
from orca.requests import RequestLog, TermsRequest
from orca.routing import Classification, route
from orca.types import QuestionType
from orca.versioning import ApproxDate

PRICING = TermsPricing(price_per_file=30000)


def _plan(catalog, *, pricing=PRICING, pending=None, context=None, **kwargs):
    decision = route(Classification(question_type=QuestionType.COVERAGE, **kwargs))
    return plan_turn(decision, catalog, context, pricing=pricing, pending_keys=pending)


@pytest.fixture
def legacy_plan(catalog):
    return _plan(
        catalog,
        product_mentioned="옛날든든보험",
        period_mentioned="2018년 5월",
        question="골절 진단금 나오나요?",
    )


class TestPriceDisclosure:
    def test_금액을_고지하고_동의를_받는다(self, legacy_plan):
        assert legacy_plan.action is NextAction.CONFIRM_PAID_REQUEST
        assert "30,000원" in legacy_plan.prompt
        assert legacy_plan.option_labels == ("요청하기 (30,000원)", "취소")

    def test_동의_전에는_접수되지_않는다(self, legacy_plan):
        # terms_request는 동의 시 적재할 내용일 뿐, 아직 접수가 아니다.
        assert legacy_plan.action is not NextAction.TERMS_NOT_REGISTERED
        assert legacy_plan.terms_request.billable is True
        assert legacy_plan.terms_request.price == 30000

    def test_취소_선택지가_항상_있다(self, legacy_plan):
        assert "취소" in legacy_plan.option_labels

    def test_판까지_특정해_무엇에_대한_비용인지_밝힌다(self, legacy_plan):
        assert "1판 (2016.01 시행)" in legacy_plan.prompt


class TestUnpricedIsDefault:
    """단가 미확정이 현재 기본 상태다."""

    def test_기본값이_미확정이다(self, catalog):
        decision = route(
            Classification(
                question_type=QuestionType.COVERAGE,
                product_mentioned="옛날든든보험",
                period_mentioned="2018년 5월",
            )
        )
        # pricing을 넘기지 않으면 UNPRICED로 동작한다.
        plan = plan_turn(decision, catalog)
        assert plan.action is NextAction.CONFIRM_PAID_REQUEST
        assert plan.terms_request.price is None

    def test_숫자를_지어내지_않는다(self, catalog):
        plan = _plan(
            catalog,
            pricing=UNPRICED,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert "원" not in plan.prompt.replace("등록 비용", "")
        assert all("원" not in label for label in plan.option_labels)

    def test_금액_없이는_확정_동의를_받지_않는다(self, catalog):
        # 「비용이 발생합니다, 요청하시겠어요?」는 백지 동의가 된다.
        # 요청 의사만 받고 금액은 확인 후 안내한다.
        plan = _plan(
            catalog,
            pricing=UNPRICED,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert "발생할 수 있습니다" in plan.prompt
        assert "확인해 안내" in plan.prompt
        assert plan.option_labels == ("확보 요청하기", "취소")

    def test_비용_확인_후_안내라는_점을_선택지에도_남긴다(self, catalog):
        plan = _plan(
            catalog,
            pricing=UNPRICED,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        confirm = plan.options[0]
        assert confirm.value == "confirm"
        assert confirm.note == "비용 확인 후 안내"

    def test_단가가_정해지면_금액_동의로_바뀐다(self, catalog):
        plan = _plan(
            catalog,
            pricing=TermsPricing(price_per_file=30000),
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert plan.option_labels == ("요청하기 (30,000원)", "취소")
        assert plan.terms_request.price == 30000


class TestNoDoubleCharge:
    def test_이미_진행_중이면_비용을_받지_않는다(self, catalog, legacy_plan):
        pending = {legacy_plan.terms_request.key}
        plan = _plan(
            catalog,
            pending=pending,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert plan.action is NextAction.TERMS_NOT_REGISTERED
        assert "추가 비용 없이" in plan.prompt
        assert plan.terms_request.billable is False

    def test_다른_판이면_별도_비용이다(self, catalog, legacy_plan):
        # 판마다 따로 등록해야 하므로 비용도 따로 발생한다.
        pending = {legacy_plan.terms_request.key}
        plan = _plan(
            catalog,
            pending=pending,
            product_mentioned="옛날든든보험",
            period_mentioned="2021년 5월",
        )
        assert plan.action is NextAction.CONFIRM_PAID_REQUEST

    def test_RequestLog에서_진행_중_목록을_얻는다(self, catalog, legacy_plan):
        log = RequestLog()
        log.record(legacy_plan.terms_request)

        plan = _plan(
            catalog,
            pending=log.pending_keys(),
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert plan.action is NextAction.TERMS_NOT_REGISTERED


class TestPricing:
    def test_판_수만큼_곱한다(self):
        assert PRICING.price_for(3) == 90000
        assert PRICING.format(3) == "90,000원"

    def test_미확정이면_None(self):
        assert UNPRICED.price_for(2) is None
        assert UNPRICED.format(2) == "등록 비용"


class TestRequestRecord:
    def test_동의한_금액을_그대로_남긴다(self):
        # 사후 단가가 바뀌어도 청구 근거는 동의 시점 금액이다.
        request = TermsRequest(
            product_name="옛날든든보험",
            insurer="△△화재",
            contract_date=ApproxDate(2018, 5),
            billable=True,
            price=30000,
            requester_id="fa-1",
        )
        assert request.billable
        assert request.price == 30000

    def test_기본은_무료_요청이다(self):
        assert TermsRequest(product_name="x").billable is False


class TestContextPreserved:
    def test_동의_대기_중에도_상품_컨텍스트가_남는다(self, catalog, legacy_plan):
        assert legacy_plan.context.product_id == "legacy"
        assert isinstance(legacy_plan.context, ConversationContext)
