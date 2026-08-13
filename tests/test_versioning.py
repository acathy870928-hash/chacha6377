from datetime import date

from conftest import AUTOPILOT, DRIVER

from orca.types import Product
from orca.versioning import (
    ApproxDate,
    EditionStatus,
    parse_approx_date,
    resolve_edition,
)


class TestResolveEdition:
    def test_판이_하나면_시점을_묻지_않는다(self):
        result = resolve_edition(AUTOPILOT)
        assert result.status is EditionStatus.SINGLE_EDITION
        assert result.is_settled
        assert result.edition.edition_id == "autopilot-1"

    def test_판이_여럿인데_시점이_없으면_되묻는다(self):
        result = resolve_edition(DRIVER)
        assert result.status is EditionStatus.NEEDS_CONTRACT_DATE
        assert not result.is_settled
        # 되묻기 선택지로 판 목록을 그대로 쓴다.
        assert [e.edition_id for e in result.candidates] == ["driver-1", "driver-2", "driver-3"]

    def test_정확한_일자면_해당_판으로_확정된다(self):
        result = resolve_edition(DRIVER, ApproxDate(2021, 6, 10))
        assert result.status is EditionStatus.RESOLVED
        assert result.edition.edition_id == "driver-2"

    def test_시행일_당일은_새_판이_적용된다(self):
        result = resolve_edition(DRIVER, ApproxDate(2023, 4, 15))
        assert result.edition.edition_id == "driver-3"

    def test_시행일_전날은_이전_판이_적용된다(self):
        result = resolve_edition(DRIVER, ApproxDate(2023, 4, 14))
        assert result.edition.edition_id == "driver-2"

    def test_월까지만_말해도_판이_안_바뀌면_확정된다(self):
        result = resolve_edition(DRIVER, ApproxDate(2021, 6))
        assert result.status is EditionStatus.RESOLVED
        assert result.edition.edition_id == "driver-2"

    def test_그_달에_개정이_있으면_일자까지_묻는다(self):
        # 2023년 4월은 2판과 3판이 걸쳐 있다. 최신 판으로 임의 확정하지 않는다.
        result = resolve_edition(DRIVER, ApproxDate(2023, 4))
        assert result.status is EditionStatus.NEEDS_EXACT_DATE
        assert [e.edition_id for e in result.candidates] == ["driver-2", "driver-3"]

    def test_연도만_말하면_그_해에_개정이_있을_때_되묻는다(self):
        result = resolve_edition(DRIVER, ApproxDate(2021))
        assert result.status is EditionStatus.NEEDS_EXACT_DATE

    def test_연도만_말해도_개정이_없으면_확정된다(self):
        result = resolve_edition(DRIVER, ApproxDate(2020))
        assert result.status is EditionStatus.RESOLVED
        assert result.edition.edition_id == "driver-1"

    def test_색인_범위보다_이른_가입은_없다고_답한다(self):
        result = resolve_edition(DRIVER, ApproxDate(2015, 3, 2))
        assert result.status is EditionStatus.BEFORE_COVERAGE
        assert result.edition is None

    def test_판_정보가_없으면_확정하지_않는다(self):
        result = resolve_edition(Product(product_id="x", name="약관 없음"))
        assert result.status is EditionStatus.NO_EDITIONS

    def test_판_순서가_뒤섞여_있어도_동작한다(self):
        shuffled = Product(
            product_id=DRIVER.product_id,
            name=DRIVER.name,
            editions=tuple(reversed(DRIVER.editions)),
        )
        result = resolve_edition(shuffled, ApproxDate(2019, 5, 1))
        assert result.edition.edition_id == "driver-1"


class TestParseApproxDate:
    def test_전체_일자(self):
        assert parse_approx_date("2023-04-15") == ApproxDate(2023, 4, 15)
        assert parse_approx_date("2023.4.15") == ApproxDate(2023, 4, 15)
        assert parse_approx_date("2023년 4월 15일") == ApproxDate(2023, 4, 15)

    def test_연월까지만(self):
        assert parse_approx_date("2023년 4월") == ApproxDate(2023, 4)
        assert parse_approx_date("2023.04") == ApproxDate(2023, 4)

    def test_연도만(self):
        assert parse_approx_date("2019년에 가입했어요") == ApproxDate(2019)

    def test_두_자리_연도는_미래가_되지_않게_해석한다(self):
        today = date(2026, 8, 13)
        assert parse_approx_date("23년 4월", today=today) == ApproxDate(2023, 4)
        assert parse_approx_date("95년 7월", today=today) == ApproxDate(1995, 7)

    def test_문장_안에서도_찾는다(self):
        assert parse_approx_date("아마 2021년 6월쯤 가입한 계약입니다") == ApproxDate(2021, 6)

    def test_잘못된_월은_버리고_연도만_남긴다(self):
        # 확정할 수 없는 부분을 임의로 채우지 않는다. 이후 단계에서 다시 묻게 된다.
        assert parse_approx_date("2023년 13월") == ApproxDate(2023)

    def test_시점_표현이_없으면_None(self):
        assert parse_approx_date("가입 시점 기억 안 나요") is None
        assert parse_approx_date("") is None
