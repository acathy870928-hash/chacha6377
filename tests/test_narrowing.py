"""상품이 많을 때 보험사부터 좁히는 흐름.

공시실 상품명을 전량 적재하면 카탈로그가 수천 건이 된다.
그 상태에서 상품 칩만 잘라 보여주면 FA가 찾는 상품이 그 안에 없다.
실제 시드 데이터(손보 91 + 생보 29)로 이 흐름을 검증한다.
"""

from orca.catalog import InMemoryProductCatalog
from orca.clarify import NextAction, plan_turn
from orca.routing import Classification, route
from orca.seed import load_all, to_entries
from orca.types import QuestionType


def _catalog():
    return InMemoryProductCatalog(to_entries(load_all()))


def _plan(catalog, context=None, **kwargs):
    decision = route(Classification(question_type=QuestionType.COVERAGE, **kwargs))
    return plan_turn(decision, catalog, context)


class TestInsurerNarrowing:
    def test_상품이_많으면_보험사부터_묻는다(self):
        plan = _plan(_catalog())
        assert plan.action is NextAction.ASK_INSURER
        assert "삼성화재" in plan.option_labels
        assert plan.needs_user_input

    def test_보험사를_고르면_상품을_묻는다(self):
        catalog = _catalog()
        first = _plan(catalog)
        assert first.action is NextAction.ASK_INSURER

        chosen = first.context.with_insurer("메트라이프")
        second = _plan(catalog, context=chosen)
        assert second.action is NextAction.ASK_PRODUCT
        # 메트라이프 상품만 후보로 나온다.
        assert set(second.option_labels) <= {
            "(무)변액연금보험 동행Plus",
            "(무)변액연금보험 동행",
            "(무)백만인을위한달러종신보험Plus",
            "360암보험",
        }

    def test_흔한_이름은_보험사부터_묻는다(self):
        # 「건강보험」은 회사마다 있어 후보가 쏟아진다.
        plan = _plan(_catalog(), product_mentioned="건강보험")
        assert plan.action is NextAction.ASK_INSURER

    def test_충분히_좁은_이름이면_바로_상품을_묻는다(self):
        # 메트라이프 「동행」 계열은 두 개뿐이므로 보험사를 물을 필요가 없다.
        plan = _plan(_catalog(), product_mentioned="변액연금보험 동행")
        assert plan.action is NextAction.ASK_PRODUCT
        assert set(plan.option_labels) == {
            "(무)변액연금보험 동행Plus",
            "(무)변액연금보험 동행",
        }

    def test_이름이_유일하면_되묻지_않는다(self):
        plan = _plan(_catalog(), product_mentioned="참좋은운전자상해보험")
        # 상품은 특정됐고, 판 정보가 없어 다음 단계로 넘어간다.
        assert plan.action is not NextAction.ASK_PRODUCT
        assert plan.action is not NextAction.ASK_INSURER
        assert plan.product.insurer == "DB손보"

    def test_보험사를_이미_알면_다시_묻지_않는다(self):
        catalog = _catalog()
        context = _plan(catalog).context.with_insurer("삼성화재")
        plan = _plan(catalog, context=context, product_mentioned="건강보험")
        assert plan.action is NextAction.ASK_PRODUCT

    def test_상품을_고르면_보험사가_컨텍스트에_남는다(self):
        plan = _plan(_catalog(), product_mentioned="참좋은운전자상해보험")
        assert plan.context.insurer == "DB손보"
