from orca.clarify import ConversationContext, NextAction, plan_turn
from orca.routing import Classification, route
from orca.types import QuestionType, Source
from orca.versioning import ApproxDate


def _plan(catalog, question_type, context=None, **kwargs):
    decision = route(Classification(question_type=question_type, **kwargs))
    return plan_turn(decision, catalog, context)


class TestNoClarificationNeeded:
    def test_개념_질문은_되묻지_않는다(self, catalog):
        plan = _plan(catalog, QuestionType.CONCEPT)
        assert plan.action is NextAction.SEARCH
        assert plan.sources == (Source.MICKY,)
        assert not plan.needs_user_input

    def test_판이_하나뿐인_상품은_가입_시점을_묻지_않는다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="오토파일럿 변액연금",
        )
        assert plan.action is NextAction.SEARCH
        assert plan.edition.edition_id == "autopilot-1"

    def test_질문에_상품과_시점이_다_있으면_바로_검색한다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="무배당 운전자보험",
            period_mentioned="2021년 6월",
        )
        assert plan.action is NextAction.SEARCH
        assert plan.edition.edition_id == "driver-2"


class TestAsksForProduct:
    def test_상품이_없는_보상_질문은_상품을_되묻는다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE)
        assert plan.action is NextAction.ASK_PRODUCT
        assert plan.needs_user_input
        # 자유 입력 대신 인덱스에 있는 상품을 선택지로 준다.
        assert "무배당 운전자보험" in plan.option_labels

    def test_상품명이_모호하면_후보를_제시한다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE, product_mentioned="더드림 암보험")
        assert plan.action is NextAction.ASK_PRODUCT
        assert set(plan.option_labels) == {"더드림 암보험", "더드림 암보험 플러스"}

    def test_상품_설명_질문은_상품이_없어도_일반론으로_답한다(self, catalog):
        # 시점 민감도가 REQUIRED가 아니면 되묻지 않고 진행한다.
        plan = _plan(catalog, QuestionType.PRODUCT_INFO)
        assert plan.action is NextAction.ANSWER_GENERAL
        assert not plan.needs_user_input


class TestAsksForContractDate:
    def test_개정_이력이_있으면_가입_시점을_묻는다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE, product_mentioned="무배당 운전자보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert plan.product.product_id == "driver"
        assert len(plan.options) == 3

    def test_개정이_걸친_달이면_일자까지_묻는다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="무배당 운전자보험",
            period_mentioned="2023년 4월",
        )
        assert plan.action is NextAction.ASK_EXACT_DATE
        assert len(plan.options) == 2

    def test_색인_범위보다_이른_가입은_없다고_답한다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="무배당 운전자보험",
            period_mentioned="2015년 3월",
        )
        assert plan.action is NextAction.NO_TERMS_AVAILABLE
        assert "확인되지 않은 내용으로 답하지 않겠습니다" in plan.prompt


class TestSessionContext:
    def test_직전에_특정한_상품을_이어서_쓴다(self, catalog):
        first = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="무배당 운전자보험",
            period_mentioned="2021년 6월",
        )
        assert first.action is NextAction.SEARCH

        # 「그럼 무면허는요?」 — 상품을 다시 말하지 않는다.
        second = _plan(catalog, QuestionType.COVERAGE, context=first.context)
        assert second.action is NextAction.SEARCH
        assert second.product.product_id == "driver"
        assert second.edition.edition_id == "driver-2"

    def test_상품이_바뀌면_이전_판_정보를_버린다(self, catalog):
        context = ConversationContext(
            product_id="driver",
            contract_date=ApproxDate(2021, 6),
            edition_id="driver-2",
        )
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            context=context,
            product_mentioned="오토파일럿 변액연금",
        )
        assert plan.product.product_id == "autopilot"
        assert plan.edition.edition_id == "autopilot-1"
        assert plan.context.contract_date is None

    def test_되묻는_중에도_상품_컨텍스트는_남는다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE, product_mentioned="무배당 운전자보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        # 다음 턴에서 시점만 받으면 되도록 상품을 들고 간다.
        assert plan.context.product_id == "driver"


class TestUnregisteredTerms:
    """약관은 우선 일부만 등록한다. 없는 약관은 역질문으로 확정해 등록 요청으로 남긴다."""

    def test_미등록_상품도_선택지에_보이되_준비중으로_표시된다(self, catalog):
        # 상품명 자체는 보여야 FA가 자료에 있는 상품인지 알 수 있다.
        plan = _plan(catalog, QuestionType.COVERAGE)
        assert plan.action is NextAction.ASK_PRODUCT
        assert "옛날든든보험" in plan.option_labels

        legacy = next(o for o in plan.options if o.label == "옛날든든보험")
        assert legacy.available is False

    def test_등록된_약관이_선택지_앞에_온다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE)
        available = [o.available for o in plan.options]
        assert available == sorted(available, reverse=True)

    def test_미등록_상품도_가입_시점을_먼저_묻는다(self, catalog):
        # 상품명만으로는 어느 판을 등록해야 할지 정해지지 않는다.
        plan = _plan(catalog, QuestionType.COVERAGE, product_mentioned="옛날든든보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert "아직 약관이 등록되어 있지 않습니다" in plan.prompt

    def test_시점까지_받으면_비용_동의를_먼저_받는다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
            question="음주운전 사고인데 보험금 나오나요?",
        )
        # 초기 등록분에 없는 약관이므로 요청자 부담이다. 동의 없이 접수하지 않는다.
        assert plan.action is NextAction.CONFIRM_PAID_REQUEST
        assert plan.terms_request is not None
        assert plan.terms_request.billable is True
        assert plan.terms_request.product_id == "legacy"
        assert plan.terms_request.edition_label == "1판 (2016.01 시행)"
        assert plan.terms_request.contract_date.year == 2018
        assert plan.terms_request.question == "음주운전 사고인데 보험금 나오나요?"

    def test_미등록_상품은_추측해서_답하지_않는다(self, catalog):
        plan = _plan(
            catalog,
            QuestionType.COVERAGE,
            product_mentioned="옛날든든보험",
            period_mentioned="2018년 5월",
        )
        assert plan.sources == ()
        assert "확인할 수 없습니다" in plan.prompt

    def test_마스터에도_없는_상품도_요청으로_남긴다(self, catalog):
        # 「모른다」로 끝내면 등록 요청이 쌓이지 않는다.
        first = _plan(catalog, QuestionType.COVERAGE, product_mentioned="처음보는보험")
        assert first.action is NextAction.ASK_CONTRACT_DATE

        second = _plan(
            catalog,
            QuestionType.COVERAGE,
            context=first.context,
            period_mentioned="2022년 3월",
        )
        assert second.action is NextAction.CONFIRM_PAID_REQUEST
        assert second.terms_request.product_name == "처음보는보험"
        # 마스터에 없으므로 상품 ID는 남기지 않는다.
        assert second.terms_request.product_id is None

    def test_되묻는_중에_미등록_상품_컨텍스트가_유지된다(self, catalog):
        plan = _plan(catalog, QuestionType.COVERAGE, product_mentioned="처음보는보험")
        assert plan.context.product_name == "처음보는보험"


class TestOutOfScope:
    def test_금액_질문은_범위_밖임을_안내한다(self, catalog):
        plan = _plan(catalog, QuestionType.CONTRACT_VALUE)
        assert plan.action is NextAction.OUT_OF_SCOPE
        assert plan.sources == ()
        assert "개별 계약" in plan.prompt
