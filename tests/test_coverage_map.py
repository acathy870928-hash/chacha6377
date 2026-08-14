"""보장맵 — 고객이 가진 담보를 계약별로 펼친 것.

약관을 등록하면 담보 이름이 채워지지만 가입 여부는 모른다.
그 구분이 무너지면 미가입 담보를 「나온다」고 답하게 된다.
"""

import pytest

from orca.clarify import NextAction, plan_turn
from orca.coverage_map import (
    BenefitSource,
    BenefitStatus,
    CoverageMap,
    MapEntry,
    MappedBenefit,
    summarize_gap,
)
from orca.routing import Classification, route
from orca.types import QuestionType

KB = MapEntry(
    insurer="KB손보",
    product_name="KB다이렉트플러스운전자보험",
    edition_label="2024.10 시행",
    contract_year=2024,
    benefits=(
        MappedBenefit("골절진단비(치아파절포함)(연간1회한)", BenefitStatus.ENROLLED, 10,
                      BenefitSource.COVERAGE_REPORT),
        MappedBenefit("5대골절진단비"),
        MappedBenefit("교통상해입원일당", BenefitStatus.NOT_ENROLLED),
    ),
)

DB = MapEntry(
    insurer="DB손보",
    product_name="브라보라이프보험0808",
    contract_year=2009,
    benefits=(
        MappedBenefit("골절진단비(치아제외)"),
        MappedBenefit("뇌졸중진단비", BenefitStatus.ENROLLED, 1000, BenefitSource.MANUAL),
    ),
)


@pytest.fixture
def cmap():
    return CoverageMap(customer_id="c1", customer_name="차○희", entries=(KB, DB))


class TestDefaultStatus:
    def test_약관만_등록하면_가입_여부는_모른다(self):
        # 이게 기본값이어야 미가입을 「나온다」고 답하지 않는다.
        benefit = MappedBenefit("골절진단비")
        assert benefit.status is BenefitStatus.UNKNOWN
        assert not benefit.is_confirmed
        assert benefit.source is BenefitSource.TERMS

    def test_보장분석에서_오면_확정이다(self):
        benefit = MappedBenefit("골절진단비", BenefitStatus.ENROLLED, 10,
                                BenefitSource.COVERAGE_REPORT)
        assert benefit.is_confirmed
        assert benefit.amount == 10


class TestLookup:
    def test_전_계약을_훑는다(self, cmap):
        found = cmap.find("골절진단비")
        assert {entry.insurer for entry, _ in found} == {"KB손보", "DB손보"}

    def test_가입_확인된_것만_따로_본다(self, cmap):
        enrolled = cmap.enrolled("골절진단비")
        assert len(enrolled) == 1
        assert enrolled[0][1].amount == 10

    def test_미확인_담보를_빠뜨리지_않는다(self, cmap):
        # 「없다」가 아니라 「확인이 안 됐다」이므로 증권 확인 대상이 된다.
        unknown = cmap.unconfirmed("골절진단비")
        assert {b.name for _, b in unknown} == {"5대골절진단비", "골절진단비(치아제외)"}

    def test_미가입_확인된_것은_미확인이_아니다(self, cmap):
        assert cmap.unconfirmed("교통상해입원일당") == ()
        assert cmap.enrolled("교통상해입원일당") == ()


class TestCompleteness:
    def test_빈_보장맵(self):
        empty = CoverageMap(customer_id="c1")
        assert empty.is_empty
        assert empty.confirmed_ratio == 0.0

    def test_확정_비율을_센다(self, cmap):
        # 5개 담보 중 3개 확정(가입 2 + 미가입 1)
        assert cmap.benefit_count == 5
        assert cmap.confirmed_ratio == pytest.approx(0.6)

    def test_계약_수를_센다(self, cmap):
        assert cmap.contract_count == 2


class TestAddEntry:
    def test_약관을_등록하면_계약이_늘어난다(self, cmap):
        added = cmap.with_entry(
            MapEntry(insurer="하나손보", product_name="무배당더블플러스건강보험")
        )
        assert added.contract_count == 3

    def test_같은_계약을_다시_등록하면_교체된다(self, cmap):
        updated = cmap.with_entry(
            MapEntry(
                insurer="DB손보",
                product_name="브라보라이프보험0808",
                contract_year=2009,
                benefits=(MappedBenefit("골절진단비(치아제외)", BenefitStatus.ENROLLED, 30),),
            )
        )
        assert updated.contract_count == 2
        assert updated.enrolled("골절진단비(치아제외)")

    def test_원본은_바뀌지_않는다(self, cmap):
        cmap.with_entry(MapEntry(insurer="하나손보", product_name="새상품"))
        assert cmap.contract_count == 2


class TestSummaryLine:
    def test_등록된_약관이_없으면_그렇게_말한다(self):
        assert "등록된 약관이 없어" in summarize_gap(CoverageMap(), "골절진단비")

    def test_확정과_미확인을_함께_말한다(self, cmap):
        line = summarize_gap(cmap, "골절진단비")
        assert "가입 확인 1건" in line
        assert "확인 필요 2건" in line

    def test_미확인만_있으면_증권_확인을_안내한다(self):
        only_unknown = CoverageMap(entries=(MapEntry(
            insurer="DB손보", product_name="브라보라이프보험0808",
            benefits=(MappedBenefit("골절진단비(치아제외)"),),
        ),))
        assert "증권 확인이 필요" in summarize_gap(only_unknown, "골절진단비")

    def test_해당_담보가_없으면_찾지_못했다고_한다(self, cmap):
        assert "찾지 못했습니다" in summarize_gap(cmap, "치아보철치료")


class TestOfferPersonalize:
    """일반 답변 뒤에 개인화 경로를 제안한다."""

    def test_일반_담보_설명에는_제안한다(self, catalog):
        decision = route(Classification(question_type=QuestionType.BENEFIT_TERM))
        plan = plan_turn(decision, catalog)
        assert plan.action is NextAction.SEARCH
        assert plan.offer_personalize

    def test_되묻는_중에는_제안하지_않는다(self, catalog):
        decision = route(
            Classification(question_type=QuestionType.COVERAGE, product_mentioned="무배당 운전자보험")
        )
        plan = plan_turn(decision, catalog)
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert not plan.offer_personalize

    def test_개념_질문에는_제안하지_않는다(self, catalog):
        # 계약과 무관한 이론 질문이므로 개인화할 것이 없다.
        decision = route(Classification(question_type=QuestionType.CONCEPT))
        plan = plan_turn(decision, catalog)
        assert not plan.offer_personalize

    def test_이미_계약으로_답했으면_제안하지_않는다(self, catalog):
        from datetime import date

        from orca.coverage import CoverageProfile, EnrolledBenefit, EnrolledContract
        from orca.versioning import ApproxDate

        profile = CoverageProfile(
            contracts=(
                EnrolledContract(
                    insurer="KB손보",
                    product_name="KB다이렉트플러스운전자보험(무배당)(24.10)",
                    contract_start=ApproxDate(2024, 11),
                    benefits=(EnrolledBenefit("골절진단비(치아파절포함)(연간1회한)", 10),),
                ),
            ),
            as_of=date(2026, 5, 21),
        )
        decision = route(
            Classification(question_type=QuestionType.COVERAGE, benefit_mentioned="골절진단비")
        )
        plan = plan_turn(decision, catalog, coverage=profile)
        assert plan.action is NextAction.SEARCH
        assert not plan.offer_personalize
