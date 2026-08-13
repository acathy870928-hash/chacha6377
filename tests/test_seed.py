from orca.catalog import InMemoryProductCatalog
from orca.seed import (
    coverage_curve,
    load_seed,
    make_product_id,
    registration_plan,
    to_entries,
)


class TestLoadSeed:
    def test_실적_상품_목록을_읽는다(self):
        seeds = load_seed()
        assert len(seeds) == 91
        assert sum(s.contracts for s in seeds) == 61297

    def test_기본값은_모두_미등록이다(self):
        # 아직 약관을 하나도 넣지 않은 상태. 그래도 상품명은 목록에 나온다.
        seeds = load_seed()
        assert all(not s.product.indexed for s in seeds)

    def test_등록된_상품만_indexed가_된다(self):
        seeds = load_seed()
        target = seeds[0].product.product_id
        registered = load_seed(registered={target})

        indexed = [s.product for s in registered if s.product.indexed]
        assert [p.product_id for p in indexed] == [target]

    def test_종별이_실린다(self):
        seeds = load_seed()
        categories = {s.product.category for s in seeds}
        assert "운전자" in categories
        assert "실손의료" in categories


class TestProductId:
    def test_표기가_달라도_같은_ID가_나온다(self):
        assert make_product_id("삼성화재", "(무)삼성화재 운전자보험") == make_product_id(
            "삼성화재", "무배당 삼성화재운전자보험"
        )

    def test_회사가_다르면_다른_ID다(self):
        assert make_product_id("삼성화재", "운전자보험") != make_product_id("DB손보", "운전자보험")


class TestRegistrationPlan:
    def test_건수가_많은_상품부터_담는다(self):
        seeds = load_seed()
        plan = registration_plan(seeds, terms_budget=100, terms_per_product=2.0)

        contracts = [s.contracts for s in plan.products]
        assert contracts == sorted(contracts, reverse=True)
        assert plan.products[0].product.category == "운전자"

    def test_약관_예산을_상품_수로_환산한다(self):
        seeds = load_seed()
        # 상품 하나가 약관 2건을 차지한다고 보면 100건 예산 = 상품 50개.
        plan = registration_plan(seeds, terms_budget=100, terms_per_product=2.0)
        assert len(plan.products) == 50
        assert plan.estimated_terms == 100

    def test_상품당_약관이_많으면_담을_상품이_줄어든다(self):
        seeds = load_seed()
        few = registration_plan(seeds, terms_budget=100, terms_per_product=4.0)
        many = registration_plan(seeds, terms_budget=100, terms_per_product=1.0)
        assert len(few.products) < len(many.products)
        assert few.contract_coverage < many.contract_coverage

    def test_커버리지를_계산한다(self):
        seeds = load_seed()
        plan = registration_plan(seeds, terms_budget=100, terms_per_product=2.0)
        # 상위 50개면 계약의 8할 이상을 덮는다.
        assert 0.8 < plan.contract_coverage < 1.0


class TestCoverageCurve:
    def test_상위_N개가_덮는_비율(self):
        curve = dict(coverage_curve(load_seed(), points=(10, 30, 91)))
        assert curve[10] > 0.4
        assert curve[30] > 0.7
        assert curve[91] == 1.0


class TestCatalogFromSeed:
    def test_시드로_카탈로그를_만들_수_있다(self):
        seeds = load_seed()
        catalog = InMemoryProductCatalog(to_entries(seeds))
        found = catalog.search("참좋은운전자상해보험")
        assert [p.insurer for p in found] == ["DB손보"]

    def test_미등록_상품도_검색된다(self):
        catalog = InMemoryProductCatalog(to_entries(load_seed()))
        found = catalog.search("실손의료비")
        assert found
        assert all(not p.indexed for p in found)
