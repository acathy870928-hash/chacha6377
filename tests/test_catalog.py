from datetime import date

from orca.catalog import CatalogEntry, InMemoryProductCatalog, normalize_product_name
from orca.types import PolicyEdition, Product


def _product(product_id: str, name: str, *, indexed: bool = True, insurer: str = "○○생명"):
    return Product(
        product_id=product_id,
        name=name,
        insurer=insurer,
        editions=(
            PolicyEdition(
                product_id=product_id,
                edition_id=f"{product_id}-1",
                label="1판",
                effective_from=date(2020, 1, 1),
            ),
        ),
        indexed=indexed,
    )


class TestNormalize:
    def test_배당_표기는_구분에_쓰지_않는다(self):
        assert normalize_product_name("무배당 든든운전자보험") == normalize_product_name(
            "든든운전자보험"
        )
        assert normalize_product_name("(무)든든운전자보험") == normalize_product_name(
            "든든운전자보험"
        )

    def test_공백과_구두점을_무시한다(self):
        assert normalize_product_name("든든 운전자 보험") == normalize_product_name("든든운전자보험")
        assert normalize_product_name("「든든운전자보험」") == normalize_product_name(
            "든든운전자보험"
        )

    def test_상품을_구분하는_표기는_남긴다(self):
        # 갱신형과 비갱신형은 다른 상품이다.
        assert normalize_product_name("암보험 갱신형") != normalize_product_name("암보험 비갱신형")


class TestSearch:
    def test_표기가_달라도_같은_상품으로_찾는다(self):
        catalog = InMemoryProductCatalog([_product("driver", "무배당 든든운전자보험")])
        found = catalog.search("든든 운전자보험")
        assert [p.product_id for p in found] == ["driver"]

    def test_공시실_표기를_별칭으로_붙일_수_있다(self):
        catalog = InMemoryProductCatalog(
            [
                CatalogEntry(
                    product=_product("driver", "든든운전자보험"),
                    aliases=("무배당 든든운전자보험2404",),
                )
            ]
        )
        assert [p.product_id for p in catalog.search("든든운전자보험2404")] == ["driver"]

    def test_후보가_여럿이면_모두_돌려준다(self):
        catalog = InMemoryProductCatalog(
            [
                _product("a", "더드림암보험"),
                _product("b", "더드림암보험 플러스"),
            ]
        )
        assert len(catalog.search("더드림암보험")) == 2

    def test_인덱스에_없는_상품은_선택지에_넣지_않는다(self):
        # 공시실에는 있으나 벤더 인덱스에 약관이 없는 상품.
        catalog = InMemoryProductCatalog(
            [
                _product("old", "옛날운전자보험", indexed=False),
                _product("new", "든든운전자보험"),
            ]
        )
        assert [p.product_id for p in catalog.search("운전자보험")] == ["new"]
        assert [p.product_id for p in catalog.search("")] == ["new"]

    def test_없는_이름이면_빈_목록(self):
        catalog = InMemoryProductCatalog([_product("driver", "든든운전자보험")])
        assert catalog.search("존재하지않는보험") == []

    def test_대표_목록은_칩_개수만큼만_준다(self):
        catalog = InMemoryProductCatalog(
            [_product(f"p{i}", f"상품{i}") for i in range(20)], max_options=5
        )
        assert len(catalog.search("")) == 5

    def test_id로_조회한다(self):
        catalog = InMemoryProductCatalog([_product("driver", "든든운전자보험")])
        assert catalog.get("driver").name == "든든운전자보험"
        assert catalog.get("없음") is None
