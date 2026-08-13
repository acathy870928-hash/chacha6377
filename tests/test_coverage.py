"""보장분석이 붙었을 때의 동작.

픽스처는 실제 리포트의 **구조만** 본뜬 가상 데이터다.
개인 계약 정보는 저장소에 넣지 않는다.
"""

from datetime import date

import pytest

from orca.clarify import NextAction, plan_turn
from orca.coverage import (
    CoverageProfile,
    EnrolledBenefit,
    EnrolledContract,
    normalize_benefit_name,
)
from orca.routing import Classification, route
from orca.types import QuestionType
from orca.versioning import ApproxDate

DRIVER_CONTRACT = EnrolledContract(
    insurer="KB손보",
    product_name="KB다이렉트플러스운전자보험(무배당)(24.10)",
    contract_start=ApproxDate(2024, 11),
    maturity=ApproxDate(2044, 11),
    premium=14800,
    benefits=(
        EnrolledBenefit("골절진단비(치아파절포함)(연간1회한)", 10),
        EnrolledBenefit("5대골절진단비", 20),
        EnrolledBenefit("골절수술비", 10),
        EnrolledBenefit("자동차사고부상보장A(1~3급)(운전자)", 300),
    ),
)

LEGACY_CONTRACT = EnrolledContract(
    insurer="DB손보",
    product_name="브라보라이프보험0808",
    contract_start=ApproxDate(2009, 3),
    maturity=ApproxDate(2087, 3),
    premium=84804,
    insured="본인",
    benefits=(
        EnrolledBenefit("골절진단비(치아제외)", 30),
        EnrolledBenefit("뇌졸중진단비", 1000),
        EnrolledBenefit("상해입원일당(1일이상)", 2),
    ),
)

HEALTH_CONTRACT = EnrolledContract(
    insurer="하나손보",
    product_name="무배당더블플러스건강보험(3종)(2001)",
    contract_start=ApproxDate(2020, 1),
    benefits=(
        EnrolledBenefit("뇌혈관질환진단비", 1000),
        EnrolledBenefit("유사암진단비", 1400),
    ),
)


@pytest.fixture
def coverage():
    return CoverageProfile(
        contracts=(DRIVER_CONTRACT, LEGACY_CONTRACT, HEALTH_CONTRACT),
        as_of=date(2026, 5, 21),
    )


def _plan(catalog, coverage=None, question_type=QuestionType.COVERAGE, **kwargs):
    decision = route(Classification(question_type=question_type, **kwargs))
    return plan_turn(decision, catalog, coverage=coverage)


class TestBenefitLookup:
    def test_여러_계약에_걸친_담보를_모두_찾는다(self, coverage):
        # 골절진단비가 두 계약에 있다. 하나만 답하면 FA가 청구를 놓친다.
        matches = coverage.find_benefits("골절진단비")
        assert {m.contract.insurer for m in matches} == {"KB손보", "DB손보"}

    def test_이름을_포함하는_변형_담보도_함께_보여준다(self, coverage):
        # 「골절진단비」로 물어도 「5대골절진단비」가 함께 지급될 수 있다.
        # 넓게 걸어 FA가 판단하게 한다 — 좁히다 놓치는 쪽이 더 나쁘다.
        names = {m.benefit.name for m in coverage.find_benefits("골절진단비")}
        assert names == {
            "골절진단비(치아파절포함)(연간1회한)",
            "5대골절진단비",
            "골절진단비(치아제외)",
        }

    def test_한_계약_안의_여러_담보도_찾는다(self, coverage):
        matches = coverage.find_benefits("골절")
        names = [m.benefit.name for m in matches]
        assert "5대골절진단비" in names
        assert "골절수술비" in names

    def test_괄호_표기가_달라도_찾되_원문은_보존한다(self, coverage):
        # 「치아파절포함」과 「치아제외」는 지급 범위가 다르므로 원문이 남아야 한다.
        matches = coverage.find_benefits("골절진단비")
        originals = {m.benefit.name for m in matches}
        assert "골절진단비(치아파절포함)(연간1회한)" in originals
        assert "골절진단비(치아제외)" in originals

    def test_가입_여부를_판정한다(self, coverage):
        assert coverage.is_enrolled("뇌졸중진단비")
        assert not coverage.is_enrolled("치아보철치료")

    def test_계약_합산_금액을_구한다(self, coverage):
        # 어디에 얼마씩 있는지 보여주기 위한 값이지 지급액이 아니다.
        assert coverage.total_amount("골절진단비") == 60  # 10 + 20 + 30

    def test_상품명으로_계약을_찾는다(self, coverage):
        contract = coverage.find_contract("KB다이렉트플러스운전자보험")
        assert contract.insurer == "KB손보"
        assert contract.contract_start == ApproxDate(2024, 11)


class TestNoClarificationNeeded:
    def test_상품도_시점도_묻지_않는다(self, catalog, coverage):
        # 리포트에 상품명과 계약년월이 있으므로 특정이 이미 끝나 있다.
        plan = _plan(catalog, coverage, benefit_mentioned="골절진단비")
        assert plan.action is NextAction.SEARCH
        assert not plan.needs_user_input

    def test_계약년월이_판_특정_근거가_된다(self, catalog, coverage):
        plan = _plan(catalog, coverage, benefit_mentioned="골절진단비")
        starts = {c.contract_start for c in plan.contracts}
        assert ApproxDate(2024, 11) in starts
        assert ApproxDate(2009, 3) in starts

    def test_보장분석_없이는_되묻는다(self, catalog):
        plan = _plan(catalog, benefit_mentioned="골절진단비")
        assert plan.needs_user_input


class TestMultipleContracts:
    def test_걸린_계약을_모두_답변_대상으로_삼는다(self, catalog, coverage):
        plan = _plan(catalog, coverage, benefit_mentioned="골절진단비")
        assert len(plan.matches) == 3
        assert {c.insurer for c in plan.contracts} == {"KB손보", "DB손보"}

    def test_상품을_지목하면_그_계약만_본다(self, catalog, coverage):
        plan = _plan(
            catalog,
            coverage,
            product_mentioned="브라보라이프보험0808",
            benefit_mentioned="골절진단비",
        )
        assert {c.insurer for c in plan.contracts} == {"DB손보"}

    def test_담보를_지목하지_않으면_전_계약을_본다(self, catalog, coverage):
        # 「사고 났는데 뭐 받을 수 있어요?」
        plan = _plan(catalog, coverage)
        assert plan.action is NextAction.SEARCH
        assert len(plan.contracts) == 3


class TestNotEnrolled:
    def test_가입하지_않은_담보는_바로_답한다(self, catalog, coverage):
        plan = _plan(catalog, coverage, benefit_mentioned="치아보철치료")
        assert plan.action is NextAction.NOT_ENROLLED
        assert not plan.needs_user_input

    def test_단정하지_않고_증권_확인을_안내한다(self, catalog, coverage):
        # 조회 범위 밖 계약(오래된 계약·단독실손)이 있을 수 있다.
        plan = _plan(catalog, coverage, benefit_mentioned="치아보철치료")
        assert "조회되지 않는 계약" in plan.prompt
        assert "증권" in plan.prompt

    def test_보유하지_않은_상품을_물으면_일반_약관_경로로_간다(self, catalog, coverage):
        plan = _plan(
            catalog,
            coverage,
            product_mentioned="무배당 운전자보험",
            benefit_mentioned="골절진단비",
        )
        # 보유 계약이 아니므로 기존 되묻기·검색 흐름을 탄다.
        assert plan.action is not NextAction.NOT_ENROLLED


class TestNormalize:
    def test_괄호와_공백을_지운다(self):
        assert normalize_benefit_name("골절진단비 (치아파절포함)") == normalize_benefit_name(
            "골절진단비(치아파절포함)"
        )

    def test_다른_담보는_구분된다(self):
        assert normalize_benefit_name("골절진단비") != normalize_benefit_name("골절수술비")
