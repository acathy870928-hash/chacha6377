"""담보 용어 질문 — 약관으로 답하되 상품 · 판을 특정하지 않는다.

「골절진단비가 뭔가요?」의 정의는 약관 공통이다.
되묻기 없이 전체 약관에서 일반 설명으로 답하고,
금액 · 지급 조건은 상품마다 다름을 답변에서 밝힌다.
"""

from orca.clarify import NextAction, plan_turn
from orca.routing import Classification, route
from orca.types import QuestionType, Source, VersionSensitivity


def _plan(catalog, context=None, **kwargs):
    decision = route(Classification(question_type=QuestionType.BENEFIT_TERM, **kwargs))
    return plan_turn(decision, catalog, context)


class TestRouting:
    def test_약관을_쓰지만_판_특정은_불필요하다(self):
        decision = route(Classification(question_type=QuestionType.BENEFIT_TERM))
        assert decision.sources == (Source.VELUGA,)
        assert decision.version_sensitivity is VersionSensitivity.NONE
        assert decision.in_scope


class TestNoClarification:
    def test_상품이_없어도_되묻지_않고_바로_답한다(self, catalog):
        plan = _plan(catalog)
        assert plan.action is NextAction.SEARCH
        assert plan.sources == (Source.VELUGA,)
        assert not plan.needs_user_input
        assert plan.product is None  # 전체 약관에서 일반 설명

    def test_상품이_하나로_떨어지면_검색_범위만_좁힌다(self, catalog):
        plan = _plan(catalog, product_mentioned="무배당 운전자보험")
        assert plan.action is NextAction.SEARCH
        assert plan.product.product_id == "driver"
        # 판은 묻지도 정하지도 않는다.
        assert plan.edition is None

    def test_상품이_모호해도_묻지_않는다(self, catalog):
        # 「더드림 암보험」은 두 상품에 걸리지만, 용어 설명에는 특정이 필요 없다.
        plan = _plan(catalog, product_mentioned="더드림 암보험")
        assert plan.action is NextAction.SEARCH
        assert plan.product is None

    def test_판이_150개인_상품이_언급돼도_시점을_묻지_않는다(self, catalog):
        plan = _plan(catalog, product_mentioned="실손의료비보장보험")
        assert plan.action is NextAction.SEARCH
        assert plan.product.product_id == "silson"
        assert plan.edition is None

    def test_세션에_남은_상품과_무관하게_동작한다(self, catalog):
        # 직전 보상 질문에서 상품을 특정한 상태에서 용어 질문이 와도 그대로 답한다.
        from orca.clarify import ConversationContext

        context = ConversationContext(product_id="driver", product_name="무배당 운전자보험")
        plan = _plan(catalog, context=context)
        assert plan.action is NextAction.SEARCH
        # 컨텍스트는 버리지 않고 유지한다. 다음 보상 질문이 이어받는다.
        assert plan.context.product_id == "driver"
