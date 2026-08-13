"""담보 범위 — 약관에 있는 담보와 계약이 가입한 담보는 다르다.

약관에는 그 상품에서 가입할 수 있는 담보가 전부 들어 있고,
실제 계약은 그중 일부만 가입한다. 계약별 가입 담보는 이번 범위 밖이므로
지급 여부를 다루는 답변은 언제나 조건부여야 한다.
"""

from orca.benefits import ENROLLMENT_CAVEAT, BenefitScope, scope_for
from orca.clarify import NextAction, plan_turn
from orca.routing import Classification, parse_classification, route
from orca.types import QuestionType


def _plan(catalog, question_type=QuestionType.COVERAGE, **kwargs):
    decision = route(Classification(question_type=question_type, **kwargs))
    return plan_turn(decision, catalog)


class TestScope:
    def test_담보를_지목하면_그것만_본다(self):
        assert scope_for("골절진단비") is BenefitScope.SPECIFIC

    def test_지목하지_않으면_걸리는_담보를_모두_본다(self):
        assert scope_for(None) is BenefitScope.ENUMERATE


class TestPlanScope:
    def test_골절진단비를_물으면_SPECIFIC(self, catalog):
        plan = _plan(
            catalog,
            product_mentioned="오토파일럿 변액연금",
            benefit_mentioned="골절진단비",
        )
        assert plan.action is NextAction.SEARCH
        assert plan.benefit_scope is BenefitScope.SPECIFIC

    def test_상황만_말하면_ENUMERATE(self, catalog):
        # 「골절됐는데 뭐 받을 수 있어요?」 — 담보를 지목하지 않았다.
        # 골절진단비뿐 아니라 입원일당·수술비·후유장해가 함께 걸릴 수 있다.
        plan = _plan(catalog, product_mentioned="오토파일럿 변액연금")
        assert plan.benefit_scope is BenefitScope.ENUMERATE


class TestEnrollmentCaveat:
    def test_지급_질문_답변에는_가입_전제를_붙인다(self, catalog):
        plan = _plan(catalog, product_mentioned="오토파일럿 변액연금")
        assert plan.action is NextAction.SEARCH
        assert plan.needs_enrollment_caveat

    def test_담보_용어_설명에도_붙인다(self, catalog):
        # 「골절진단비가 뭔가요」에도 가입 여부는 별개임을 밝혀야 한다.
        plan = _plan(catalog, QuestionType.BENEFIT_TERM)
        assert plan.action is NextAction.SEARCH
        assert plan.needs_enrollment_caveat

    def test_개념_질문에는_붙이지_않는다(self, catalog):
        plan = _plan(catalog, QuestionType.CONCEPT)
        assert not plan.needs_enrollment_caveat

    def test_되묻는_중에는_붙이지_않는다(self, catalog):
        plan = _plan(catalog, product_mentioned="무배당 운전자보험")
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert not plan.needs_enrollment_caveat

    def test_전제_문구가_확인_요청을_담는다(self):
        # 우리가 확인할 수 없는 정보이므로 FA에게 확인을 넘긴다.
        assert "가입한 계약에 한하" in ENROLLMENT_CAVEAT
        assert "확인" in ENROLLMENT_CAVEAT


class TestClassificationParsing:
    def test_담보명을_읽는다(self):
        raw = '{"question_type": "coverage", "benefit_mentioned": "골절진단비"}'
        assert parse_classification(raw).benefit_mentioned == "골절진단비"

    def test_담보가_없으면_None(self):
        raw = '{"question_type": "coverage", "benefit_mentioned": null}'
        assert parse_classification(raw).benefit_mentioned is None
