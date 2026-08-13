import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orca.clarify import ProductCatalog  # noqa: E402
from orca.types import PolicyEdition, Product  # noqa: E402


def _edition(product_id: str, edition_id: str, label: str, start: date, end: date | None = None):
    return PolicyEdition(
        product_id=product_id,
        edition_id=edition_id,
        label=label,
        effective_from=start,
        effective_to=end,
    )


#: 개정 이력이 있는 상품. 가입 시점을 물어야 하는 쪽.
DRIVER = Product(
    product_id="driver",
    name="무배당 운전자보험",
    insurer="○○생명",
    editions=(
        _edition("driver", "driver-1", "1판 (2019.01 시행)", date(2019, 1, 1), date(2021, 3, 31)),
        _edition("driver", "driver-2", "2판 (2021.04 시행)", date(2021, 4, 1), date(2023, 4, 14)),
        _edition("driver", "driver-3", "3판 (2023.04 시행)", date(2023, 4, 15)),
    ),
)

#: 판이 하나뿐인 상품. 가입 시점을 묻지 않아야 하는 쪽.
AUTOPILOT = Product(
    product_id="autopilot",
    name="오토파일럿 변액연금",
    insurer="○○생명",
    editions=(_edition("autopilot", "autopilot-1", "1판 (2022.07 시행)", date(2022, 7, 1)),),
)

CANCER_A = Product(
    product_id="cancer-a",
    name="더드림 암보험",
    editions=(_edition("cancer-a", "cancer-a-1", "1판", date(2020, 1, 1)),),
)

CANCER_B = Product(
    product_id="cancer-b",
    name="더드림 암보험 플러스",
    editions=(_edition("cancer-b", "cancer-b-1", "1판", date(2024, 1, 1)),),
)


#: 상품 마스터(공시실)에는 있으나 아직 약관이 등록되지 않은 상품.
LEGACY = Product(
    product_id="legacy",
    name="옛날든든보험",
    insurer="△△화재",
    editions=(
        _edition("legacy", "legacy-1", "1판 (2016.01 시행)", date(2016, 1, 1), date(2019, 12, 31)),
        _edition("legacy", "legacy-2", "2판 (2020.01 시행)", date(2020, 1, 1)),
    ),
    indexed=False,
)


class FakeCatalog(ProductCatalog):
    def __init__(self, products):
        self._products = list(products)

    def search(self, name: str):
        """약관 등록 여부와 무관하게 후보를 주되, 등록된 상품을 앞에 둔다."""
        return sorted(self._match(name), key=lambda p: not p.indexed)

    def search_registry(self, name: str):
        """등록 여부와 무관한 상품 마스터."""
        return self._match(name)

    def get(self, product_id: str):
        return next((p for p in self._products if p.product_id == product_id), None)

    def _match(self, name: str):
        if not name:
            return list(self._products)
        return [p for p in self._products if name in p.name or p.name in name]


@pytest.fixture
def catalog():
    return FakeCatalog([DRIVER, AUTOPILOT, CANCER_A, CANCER_B, LEGACY])
