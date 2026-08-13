"""등록 비용 산정 — 과금 단위는 약관 파일 수."""

from orca.pricing import (
    UNPRICED,
    TermsPricing,
    estimate_by_contract,
    estimate_by_product,
    products_within_budget,
)

PRICING = TermsPricing(price_per_file=30000)


class TestPricePerFile:
    def test_파일_수만큼_곱한다(self):
        assert PRICING.price_for(4) == 120000
        assert PRICING.format(4) == "120,000원"

    def test_단가_미확정이면_금액이_없다(self):
        assert UNPRICED.price_for(4) is None
        assert UNPRICED.format(4) == "등록 비용"


class TestProductBased:
    def test_상품_수에_배수가_곱해진다(self):
        # 상품 하나가 보장형태·납입방법·판으로 갈린다.
        estimate = estimate_by_product(50, files_per_product=4, pricing=PRICING)
        assert estimate.files == 200
        assert estimate.amount == 6_000_000

    def test_배수가_크면_같은_예산에_적게_담긴다(self):
        assert products_within_budget(200, files_per_product=2) == 100
        assert products_within_budget(200, files_per_product=6) == 33

    def test_배수가_1이면_상품_수가_곧_파일_수다(self):
        assert products_within_budget(200, files_per_product=1) == 200


class TestContractBased:
    def test_계약은_배수가_붙지_않는다(self):
        # 보장분석이 지목한 계약은 보장형태·납입방법·판이 이미 하나다.
        estimate = estimate_by_contract(200, pricing=PRICING)
        assert estimate.files == 200
        assert estimate.amount == 6_000_000

    def test_같은_예산에서_상품_단위보다_많이_덮는다(self):
        by_product = estimate_by_product(200, files_per_product=4)
        by_contract = estimate_by_contract(200)
        # 상품 200개를 사면 800파일이 들지만, 계약 200건은 200파일이다.
        assert by_product.files == 800
        assert by_contract.files == 200

    def test_단가_미확정이면_금액을_내지_않는다(self):
        assert estimate_by_contract(200).amount is None


class TestFormat:
    def test_건수와_금액을_함께_보여준다(self):
        estimate = estimate_by_contract(200)
        assert estimate.format(PRICING) == "200건 · 6,000,000원"

    def test_미확정이면_금액_자리를_비운다(self):
        assert estimate_by_contract(200).format(UNPRICED) == "200건 · 등록 비용"
