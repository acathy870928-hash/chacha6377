"""약관 등록 비용 산정과 고지.

**과금 단위는 약관 파일 수다.** 상품 단위도, 용량 단위도 아니다.

이 사실이 등록 전략을 정한다. 한 상품이 약관 파일 하나가 아니기 때문이다.

    무배당 변액연금보험 동행(사망보장형-월납)          ← 파일 1
    무배당 변액연금보험 동행(고도재해장해보장형-월납)    ← 파일 2
    무배당 변액연금보험 동행(고도재해장해보장형-일시납)  ← 파일 3
    무배당 변액연금보험 동행 Plus(월납)               ← 파일 4
    ...

여기에 개정 판까지 곱해진다. 실손처럼 판이 150개를 넘는 상품이면 파일 수가 폭발한다.

## 상품 단위로 사는 것과 계약 단위로 사는 것

같은 예산에서 무엇을 덮는지가 크게 달라진다.

- **상품 단위 등록** — 「동행」을 사려면 보장형태 · 납입방법 · 판을 다 사야 한다.
  FA가 실제로 조회하지 않을 조합까지 함께 산다.
- **계약 단위 등록** — 보장분석이 지목한 계약은 보장형태 · 납입방법 · 판이
  이미 하나로 정해져 있다. **정확히 파일 하나**만 사면 된다.

과금이 파일 단위이므로 계약 단위 등록이 압도적으로 유리하다.
(`docs/plan.md`의 「보장분석 먼저」 제안이 여기서 비용으로 뒷받침된다.)

## 요청자 부담 고지

초기 등록분에 없는 약관은 요청한 FA가 비용을 부담한다.
접수 전에 금액을 고지하고 동의를 받아야 하며, 단가가 미확정인 지금은
금액 대신 요청 의사만 받는다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermsPricing:
    """등록 비용 산정 기준.

    **과금 단위는 약관 파일 1건이다.**
    한 상품이 여러 파일로 갈리므로(보장형태 · 납입방법 · 판),
    상품 수가 아니라 파일 수로 예산을 센다.
    """

    price_per_file: int | None = None
    """약관 파일 1건 등록 비용. None이면 미확정 — 화면에 금액을 표시하지 않는다."""

    currency: str = "원"

    def price_for(self, files: int = 1) -> int | None:
        if self.price_per_file is None:
            return None
        return self.price_per_file * max(1, files)

    def format(self, files: int = 1) -> str:
        """FA에게 보여줄 금액 문구."""
        amount = self.price_for(files)
        if amount is None:
            return "등록 비용"
        return f"{amount:,}{self.currency}"


#: 단가가 아직 정해지지 않은 상태. **현재 기본값이다.**
#:
#: 벤더 단가가 확정되지 않았으므로 화면에 금액을 표시하지 않는다.
#: 금액 없이 「비용이 발생합니다, 요청하시겠어요」로 동의를 받으면 백지 동의가 되므로,
#: 이 상태에서는 FA에게 **요청 의사만** 받고 금액은 확인해서 따로 안내한다.
#: 단가가 정해지면 TermsPricing(price_per_file=...)을 주입하면 흐름이 바뀐다.
UNPRICED = TermsPricing()


@dataclass(frozen=True)
class CostEstimate:
    """등록 비용 추정 결과."""

    files: int
    """등록할 약관 파일 수. 이것이 과금 단위다."""

    amount: int | None
    """예상 비용. 단가 미확정이면 None."""

    note: str = ""

    def format(self, pricing: TermsPricing) -> str:
        return f"{self.files:,}건 · {pricing.format(self.files)}"


def estimate_by_product(
    products: int,
    *,
    files_per_product: float,
    pricing: TermsPricing = UNPRICED,
) -> CostEstimate:
    """상품 단위로 살 때의 비용.

    상품 하나에 보장형태 · 납입방법 · 판이 곱해지므로 `files_per_product`가 배수가 된다.
    이 값은 벤더에게 실제 약관 목록을 받아야 확정된다.
    """
    files = max(1, round(products * files_per_product))
    return CostEstimate(
        files=files,
        amount=pricing.price_for(files),
        note=f"상품 {products}개 × 파일 {files_per_product:g}건",
    )


def estimate_by_contract(distinct_terms: int, *, pricing: TermsPricing = UNPRICED) -> CostEstimate:
    """계약 단위로 살 때의 비용.

    보장분석이 지목한 계약은 보장형태 · 납입방법 · 판이 하나로 정해져 있으므로
    **계약 유형 하나당 파일 하나**다. 배수가 붙지 않는다.

    `distinct_terms`는 고유한 (보험사 + 상품 + 판) 수다.
    여러 고객이 같은 계약을 보유하면 파일 하나로 함께 덮이므로 계약 수보다 작다.
    """
    files = max(0, distinct_terms)
    return CostEstimate(
        files=files,
        amount=pricing.price_for(files) if files else None,
        note=f"고유 약관 {distinct_terms}건 (계약이 판까지 지목)",
    )


def products_within_budget(files_budget: int, *, files_per_product: float) -> int:
    """파일 예산을 상품 수로 환산한다."""
    if files_per_product <= 0:
        return 0
    return max(0, int(files_budget / files_per_product))
