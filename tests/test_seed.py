from orca.catalog import InMemoryProductCatalog
from orca.seed import (
    LIFE_SEED_PATH,
    coverage_curve,
    load_all,
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
        plan = registration_plan(seeds, files_budget=100, files_per_product=2.0)

        contracts = [s.contracts for s in plan.products]
        assert contracts == sorted(contracts, reverse=True)
        assert plan.products[0].product.category == "운전자"

    def test_파일_예산을_상품_수로_환산한다(self):
        seeds = load_seed()
        # 상품 하나가 약관 2건을 차지한다고 보면 100건 예산 = 상품 50개.
        plan = registration_plan(seeds, files_budget=100, files_per_product=2.0)
        assert len(plan.products) == 50
        assert plan.estimated_files == 100

    def test_상품당_파일이_많으면_담을_상품이_줄어든다(self):
        seeds = load_seed()
        few = registration_plan(seeds, files_budget=100, files_per_product=4.0)
        many = registration_plan(seeds, files_budget=100, files_per_product=1.0)
        assert len(few.products) < len(many.products)
        assert few.contract_coverage < many.contract_coverage

    def test_커버리지를_계산한다(self):
        seeds = load_seed()
        plan = registration_plan(seeds, files_budget=100, files_per_product=2.0)
        # 상위 50개면 계약의 8할 이상을 덮는다.
        assert 0.8 < plan.contract_coverage < 1.0


class TestCoverageCurve:
    def test_상위_N개가_덮는_비율(self):
        curve = dict(coverage_curve(load_seed(), points=(10, 30, 91)))
        assert curve[10] > 0.4
        assert curve[30] > 0.7
        assert curve[91] == 1.0


class TestLifeSeed:
    def test_생명보험_목록을_읽는다(self):
        life = load_seed(LIFE_SEED_PATH)
        assert len(life) == 29
        categories = {s.product.category for s in life}
        assert categories == {"연금보험", "종신보험", "단체기업", "암", "질병·치매", "종합", "치아"}

    def test_실적이_없으면_목록_지정으로_본다(self):
        # 생명보험 목록은 건수 없이 종별로 선정돼 전달됐다.
        life = load_seed(LIFE_SEED_PATH)
        assert all(s.preselected for s in life)
        assert all(s.contracts is None for s in life)

    def test_쉼표가_든_상품명도_읽는다(self):
        names = {s.product.name for s in load_seed(LIFE_SEED_PATH)}
        assert "삼성생명 치아보험(갱신형,무배당) 빠짐없이 튼튼하게" in names

    def test_손보와_생보를_함께_읽는다(self):
        allp = load_all()
        assert len(allp) == 120
        assert len([s for s in allp if s.preselected]) == 29


class TestMixedPlan:
    def test_목록_지정_상품이_먼저_들어간다(self):
        plan = registration_plan(load_all(), files_budget=100, files_per_product=2.0)
        life_count = len([s for s in plan.products if s.preselected])
        assert life_count == 29
        # 나머지 예산은 실적순으로 손해보험이 채운다.
        assert len(plan.products) == 50

    def test_배수가_크면_실적_상품이_밀려난다(self):
        # 생명보험이 예산을 먼저 쓰므로, 배수가 커질수록 손해보험 커버리지가 무너진다.
        loose = registration_plan(load_all(), files_budget=100, files_per_product=2.0)
        tight = registration_plan(load_all(), files_budget=100, files_per_product=3.0)
        assert tight.contract_coverage < loose.contract_coverage * 0.6

    def test_목록을_나눠_예산을_따로_잡을_수_있다(self):
        # 한 예산에 섞지 않고 업권별로 따로 계획하면 이 문제를 피할 수 있다.
        nonlife = registration_plan(load_seed(), files_budget=60, files_per_product=2.0)
        assert len(nonlife.products) == 30
        assert nonlife.contract_coverage > 0.7


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
