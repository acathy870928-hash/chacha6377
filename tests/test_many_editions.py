"""판이 수십~수백 개인 상품(실손형)의 되묻기.

판 목록을 칩으로 늘어놓는 방식은 판이 적을 때만 성립한다.
많으면 가입 연·월을 입력으로 받고, 날짜 → 판 변환은 resolve_edition이 처리한다.
"""

from conftest import SILSON

from orca.clarify import EDITION_CHIP_LIMIT, NextAction, plan_turn
from orca.routing import Classification, route
from orca.types import QuestionType


def _plan(catalog, context=None, **kwargs):
    decision = route(Classification(question_type=QuestionType.COVERAGE, **kwargs))
    return plan_turn(decision, catalog, context)


class TestManyEditions:
    def test_판이_40개다(self):
        assert len(SILSON.editions) == 40
        assert len(SILSON.editions) > EDITION_CHIP_LIMIT

    def test_판이_많으면_칩_없이_시점_입력을_받는다(self, catalog):
        plan = _plan(catalog, product_mentioned="실손의료비보장보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert plan.options == ()  # 40개 칩을 늘어놓지 않는다
        assert "가입 시점으로 확인합니다" in plan.prompt
        assert "2005년부터 조회 가능" in plan.prompt

    def test_연월을_말하면_판이_확정된다(self, catalog):
        plan = _plan(
            catalog,
            product_mentioned="실손의료비보장보험",
            period_mentioned="2015년 3월",
        )
        # 2015년 3월 → 2015.01 시행 판.
        assert plan.action is NextAction.SEARCH
        assert plan.edition.label == "2015.01 시행"

    def test_연도만_말하면_그_해의_판_두_개만_칩으로_준다(self, catalog):
        # 연 2회 개정이므로 연도만으로는 두 판에 걸친다.
        # 40개 전체가 아니라 걸친 판만 칩으로 제시한다.
        plan = _plan(
            catalog,
            product_mentioned="실손의료비보장보험",
            period_mentioned="2015년",
        )
        assert plan.action is NextAction.ASK_EXACT_DATE
        assert plan.option_labels == ("2015.01 시행", "2015.07 시행")

    def test_개정월_가입은_일자까지_묻는다(self, catalog):
        # 7월에 개정이 있으므로 「2015년 7월」은 6월 판과 7월 판 경계가 아니라
        # 7/1 시행이면 7월 전체가 새 판이다 → 확정된다.
        plan = _plan(
            catalog,
            product_mentioned="실손의료비보장보험",
            period_mentioned="2015년 7월",
        )
        assert plan.action is NextAction.SEARCH
        assert plan.edition.label == "2015.07 시행"

    def test_판이_적은_상품은_여전히_칩을_준다(self, catalog):
        plan = _plan(catalog, product_mentioned="무배당 운전자보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert len(plan.options) == 3  # 3판 → 칩 유지
