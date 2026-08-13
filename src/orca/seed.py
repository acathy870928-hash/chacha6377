"""초기 상품 목록 적재 및 등록 우선순위 산정.

`data/products_nonlife.csv`는 손해보험 실적 기준 상품 목록이다.
(회사 · 종별 · 상품명 · 건수 · 월납보험료)

약관을 처음부터 전부 등록할 수 없으므로 어디부터 넣을지 정해야 하는데,
그 근거를 추측이 아니라 이 실적 데이터에서 가져온다.
보상 질문은 계약이 있는 곳에서 나오므로, 건수가 많은 상품이 먼저다.

주의: **상품 1건 = 약관 1건이 아니다.**
같은 상품도 보장형태 · 납입방법 · 개정 판에 따라 약관 파일이 갈린다.
**과금 단위는 약관 파일 수**이므로 「약관 200건」은 상품 200개가 아니다.
`registration_plan()`이 이 배수를 감안해 상품 수를 잡는다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .catalog import CatalogEntry, normalize_product_name
from .types import Product

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_SEED_PATH = DATA_DIR / "products_nonlife.csv"
LIFE_SEED_PATH = DATA_DIR / "products_life.csv"


@dataclass(frozen=True)
class SeedProduct:
    """등록 후보 상품. 실적이 있으면 우선순위 산정에 쓴다."""

    product: Product
    contracts: int | None = None
    """계약 건수. 실적 자료가 없는 목록(생명보험)에서는 None이다."""

    monthly_premium: int | None = None

    @property
    def preselected(self) -> bool:
        """실적 없이 목록으로 지정된 상품인지.

        생명보험 목록은 실적 수치 없이 종별로 선정돼 전달됐다.
        목록에 올랐다는 것 자체가 선정 결과이므로 건수로 다시 줄 세우지 않고
        등록 대상에 우선 포함한다.
        """
        return self.contracts is None


def make_product_id(insurer: str, name: str) -> str:
    """회사 + 정규화된 상품명으로 안정적인 식별자를 만든다.

    표기가 흔들려도(배당 표기 · 공백) 같은 상품이면 같은 ID가 나오게 한다.
    """
    return f"{insurer}:{normalize_product_name(name)}"


def load_seed(path: Path | str | None = None, *, registered: set[str] | None = None) -> list[SeedProduct]:
    """상품 목록 CSV를 읽는다.

    `registered`에 든 product_id만 `indexed=True`가 된다.
    아직 아무것도 등록하지 않았다면 전부 False이고, 그래도 상품명은 화면에 나온다.
    """
    path = Path(path) if path else DEFAULT_SEED_PATH
    registered = registered or set()

    seeds: list[SeedProduct] = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            insurer = row["insurer"].strip()
            name = row["name"].strip()
            product_id = make_product_id(insurer, name)
            seeds.append(
                SeedProduct(
                    product=Product(
                        product_id=product_id,
                        name=name,
                        insurer=insurer,
                        category=row["category"].strip(),
                        indexed=product_id in registered,
                    ),
                    contracts=_optional_int(row.get("contracts")),
                    monthly_premium=_optional_int(row.get("monthly_premium")),
                )
            )
    return seeds


def load_all(*, registered: set[str] | None = None) -> list[SeedProduct]:
    """손해보험 · 생명보험 목록을 함께 읽는다."""
    return load_seed(DEFAULT_SEED_PATH, registered=registered) + load_seed(
        LIFE_SEED_PATH, registered=registered
    )


def _optional_int(value: str | None) -> int | None:
    text = (value or "").strip()
    return int(text) if text else None


def to_entries(seeds: list[SeedProduct]) -> list[CatalogEntry]:
    """카탈로그에 넣을 형태로. 표기 흔들림은 여기서 별칭으로 흡수한다."""
    return [CatalogEntry(product=s.product) for s in seeds]


@dataclass(frozen=True)
class RegistrationPlan:
    """초기 등록 계획."""

    products: list[SeedProduct]
    contract_coverage: float
    """이 상품들이 덮는 계약 건수 비율. 보상 질문이 걸릴 확률의 대리 지표."""

    estimated_files: int
    """예상 약관 파일 수. 이것이 과금 단위다 (상품 수 × 상품당 파일 수)."""


def registration_plan(
    seeds: list[SeedProduct],
    *,
    files_budget: int = 200,
    files_per_product: float = 2.0,
) -> RegistrationPlan:
    """약관 파일 예산 안에서 어떤 상품부터 넣을지 정한다.

    담는 순서는 두 단계다.
      1. 목록으로 지정된 상품(생명보험) — 실적 수치가 없고, 선정 자체가 이미 끝났다.
      2. 실적이 있는 상품(손해보험) — 계약 건수가 많은 순.

    상품 하나가 약관 여러 건을 차지한다는 점을 반영한다.
    **과금 단위는 약관 파일 수다.** `files_per_product`(상품당 파일 수)는
    보장형태 · 납입방법 · 판 수에 따라 달라지므로
    벤더에서 실제 약관 목록을 받으면 그 값으로 바꿔 다시 계산한다.
    """
    preselected = [s for s in seeds if s.preselected]
    measured = sorted((s for s in seeds if not s.preselected), key=lambda s: -(s.contracts or 0))

    limit = max(1, int(files_budget / files_per_product))
    picked = (preselected + measured)[:limit]

    total = sum(s.contracts or 0 for s in seeds) or 1
    covered = sum(s.contracts or 0 for s in picked)

    return RegistrationPlan(
        products=picked,
        contract_coverage=covered / total,
        estimated_files=int(len(picked) * files_per_product),
    )


def coverage_curve(seeds: list[SeedProduct], points: tuple[int, ...]) -> list[tuple[int, float]]:
    """상위 N개가 덮는 계약 비율. 어디서 예산을 끊을지 판단하는 근거.

    실적이 있는 상품만 대상으로 한다.
    """
    measured = [s for s in seeds if not s.preselected]
    ranked = sorted(measured, key=lambda s: -(s.contracts or 0))
    total = sum(s.contracts or 0 for s in measured) or 1

    curve: list[tuple[int, float]] = []
    running = 0
    for index, seed in enumerate(ranked, start=1):
        running += seed.contracts or 0
        if index in points:
            curve.append((index, running / total))
    return curve
