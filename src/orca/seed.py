"""초기 상품 목록 적재 및 등록 우선순위 산정.

`data/products_nonlife.csv`는 손해보험 실적 기준 상품 목록이다.
(회사 · 종별 · 상품명 · 건수 · 월납보험료)

약관을 처음부터 전부 등록할 수 없으므로 어디부터 넣을지 정해야 하는데,
그 근거를 추측이 아니라 이 실적 데이터에서 가져온다.
보상 질문은 계약이 있는 곳에서 나오므로, 건수가 많은 상품이 먼저다.

주의: **상품 1건 = 약관 1건이 아니다.**
같은 상품도 보장형태 · 납입방법 · 개정 판에 따라 약관 파일이 갈린다.
따라서 「약관 100건」은 상품 100개가 아니라 그보다 적은 상품 수에 해당한다.
`registration_plan()`이 이 배수를 감안해 상품 수를 잡는다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .catalog import CatalogEntry, normalize_product_name
from .types import Product

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "products_nonlife.csv"


@dataclass(frozen=True)
class SeedProduct:
    """실적 정보가 붙은 상품. 등록 우선순위 산정에만 쓴다."""

    product: Product
    contracts: int
    monthly_premium: int


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
                    contracts=int(row["contracts"]),
                    monthly_premium=int(row["monthly_premium"]),
                )
            )
    return seeds


def to_entries(seeds: list[SeedProduct]) -> list[CatalogEntry]:
    """카탈로그에 넣을 형태로. 표기 흔들림은 여기서 별칭으로 흡수한다."""
    return [CatalogEntry(product=s.product) for s in seeds]


@dataclass(frozen=True)
class RegistrationPlan:
    """초기 등록 계획."""

    products: list[SeedProduct]
    contract_coverage: float
    """이 상품들이 덮는 계약 건수 비율. 보상 질문이 걸릴 확률의 대리 지표."""

    estimated_terms: int
    """예상 약관 파일 수. 상품 수 × 상품당 약관 배수."""


def registration_plan(
    seeds: list[SeedProduct],
    *,
    terms_budget: int = 100,
    terms_per_product: float = 2.0,
) -> RegistrationPlan:
    """약관 등록 예산 안에서 어떤 상품부터 넣을지 정한다.

    건수 순으로 담되, 상품 하나가 약관 여러 건을 차지한다는 점을 반영한다.
    `terms_per_product`는 보장형태 · 납입방법 · 판 수에 따라 달라지므로
    벤더에서 실제 약관 목록을 받으면 그 값으로 바꿔 다시 계산한다.
    """
    ranked = sorted(seeds, key=lambda s: -s.contracts)
    total = sum(s.contracts for s in seeds) or 1

    limit = max(1, int(terms_budget / terms_per_product))
    picked = ranked[:limit]
    covered = sum(s.contracts for s in picked)

    return RegistrationPlan(
        products=picked,
        contract_coverage=covered / total,
        estimated_terms=int(len(picked) * terms_per_product),
    )


def coverage_curve(seeds: list[SeedProduct], points: tuple[int, ...]) -> list[tuple[int, float]]:
    """상위 N개가 덮는 계약 비율. 어디서 예산을 끊을지 판단하는 근거."""
    ranked = sorted(seeds, key=lambda s: -s.contracts)
    total = sum(s.contracts for s in seeds) or 1

    curve: list[tuple[int, float]] = []
    running = 0
    for index, seed in enumerate(ranked, start=1):
        running += seed.contracts
        if index in points:
            curve.append((index, running / total))
    return curve
