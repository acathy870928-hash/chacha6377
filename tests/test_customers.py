"""FA별 담당 고객 목록과 분류.

접근 통제가 화면 단계에서 걸리는지, 분류가 상담 시작 통로로 쓸 만한지 검증한다.
"""

from datetime import date

import pytest

from orca.customers import (
    CustomerCategory,
    CustomerDirectory,
    CustomerSummary,
)
from orca.versioning import ApproxDate

TODAY = date(2026, 8, 13)


def _customer(cid, name, advisor="fa-1", **kwargs):
    return CustomerSummary(customer_id=cid, name=name, advisor_id=advisor, **kwargs)


ANALYZED = _customer(
    "c1",
    "김보장",
    contract_count=6,
    monthly_premium=225074,
    benefit_total=41,
    benefit_shortfall=29,
    analyzed_on=date(2026, 5, 21),
    last_consulted_on=date(2026, 8, 10),
)

ADEQUATE = _customer(
    "c2",
    "이적정",
    contract_count=4,
    benefit_total=41,
    benefit_shortfall=5,
    analyzed_on=date(2026, 6, 1),
)

STALE = _customer(
    "c3",
    "박오래",
    contract_count=3,
    benefit_total=41,
    benefit_shortfall=20,
    analyzed_on=date(2024, 1, 10),
)

NEVER = _customer("c4", "최미분석", contract_count=2)

MATURING = _customer(
    "c5",
    "정만기",
    contract_count=5,
    benefit_total=41,
    benefit_shortfall=10,
    analyzed_on=date(2026, 7, 1),
    next_maturity=ApproxDate(2026, 10),
)

OTHER_ADVISOR = _customer("c9", "남담당", advisor="fa-2", analyzed_on=date(2026, 6, 1))


@pytest.fixture
def directory():
    return CustomerDirectory(
        customers=[ANALYZED, ADEQUATE, STALE, NEVER, MATURING, OTHER_ADVISOR]
    )


class TestAccessControl:
    def test_담당_고객만_보인다(self, directory):
        names = {c.name for c in directory.for_advisor("fa-1")}
        assert "남담당" not in names
        assert len(names) == 5

    def test_담당_밖은_검색되지_않는다(self, directory):
        assert directory.search("fa-1", "남담당") == []

    def test_담당_밖은_ID로도_열리지_않는다(self, directory):
        # 화면에서 걸렀더라도 여기서 한 번 더 막는다.
        assert directory.get("fa-1", "c9") is None
        assert directory.get("fa-2", "c9").name == "남담당"

    def test_담당_고객은_열린다(self, directory):
        assert directory.get("fa-1", "c1").name == "김보장"


class TestCategories:
    def test_보장_부족이_절반_넘으면_갭으로_분류된다(self):
        # 41개 중 29개 부족 → 제안 기회
        assert CustomerCategory.COVERAGE_GAP in ANALYZED.categories(TODAY)

    def test_보장이_적정하면_갭에_들지_않는다(self):
        assert CustomerCategory.COVERAGE_GAP not in ADEQUATE.categories(TODAY)

    def test_분석이_없으면_재분석_대상이다(self):
        assert CustomerCategory.NEEDS_ANALYSIS in NEVER.categories(TODAY)
        assert not NEVER.has_analysis

    def test_분석이_오래돼도_재분석_대상이다(self):
        assert CustomerCategory.NEEDS_ANALYSIS in STALE.categories(TODAY)

    def test_분석이_없으면_부족_여부를_판단하지_않는다(self):
        # 근거가 없는데 갭으로 분류하면 잘못된 제안이 나간다.
        assert CustomerCategory.COVERAGE_GAP not in NEVER.categories(TODAY)

    def test_만기가_다가오면_분류된다(self):
        assert CustomerCategory.MATURITY_SOON in MATURING.categories(TODAY)

    def test_만기가_멀면_분류되지_않는다(self):
        far = _customer("c6", "먼만기", next_maturity=ApproxDate(2030, 1))
        assert CustomerCategory.MATURITY_SOON not in far.categories(TODAY)

    def test_한_고객이_여러_분류에_들_수_있다(self):
        assert len(ANALYZED.categories(TODAY)) >= 2


class TestListing:
    def test_최근_상담_순으로_준다(self, directory):
        recent = directory.by_category("fa-1", CustomerCategory.RECENT, today=TODAY)
        assert [c.name for c in recent] == ["김보장"]

    def test_보장_갭은_부족_비율이_높은_순(self, directory):
        gaps = directory.by_category("fa-1", CustomerCategory.COVERAGE_GAP, today=TODAY)
        ratios = [c.shortfall_ratio for c in gaps]
        assert ratios == sorted(ratios, reverse=True)

    def test_만기는_임박한_순(self, directory):
        soon = directory.by_category("fa-1", CustomerCategory.MATURITY_SOON, today=TODAY)
        assert [c.name for c in soon] == ["정만기"]

    def test_분류별_인원을_센다(self, directory):
        counts = directory.counts("fa-1", today=TODAY)
        assert counts[CustomerCategory.NEEDS_ANALYSIS] == 2  # 박오래, 최미분석
        assert counts[CustomerCategory.RECENT] == 1

    def test_다른_FA의_인원은_섞이지_않는다(self, directory):
        counts = directory.counts("fa-2", today=TODAY)
        assert sum(counts.values()) <= 1


class TestSearch:
    def test_이름으로_찾는다(self, directory):
        assert [c.name for c in directory.search("fa-1", "김보장")] == ["김보장"]

    def test_빈_검색어는_전체_담당_고객(self, directory):
        assert len(directory.search("fa-1", "")) == 5

    def test_부분_일치도_찾는다(self, directory):
        assert [c.name for c in directory.search("fa-1", "보장")] == ["김보장"]
