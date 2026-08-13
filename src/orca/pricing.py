"""약관 등록 비용 고지.

초기 등록분(회사 부담)에 없는 약관은 **요청한 FA가 비용을 부담한다.**
따라서 요청을 접수하기 전에 금액을 고지하고 동의를 받아야 한다.

금액을 모른 채 「요청하기」를 누르게 두면 안 된다.
동의 없이 비용이 발생하는 흐름은 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermsPricing:
    """등록 비용 산정 기준.

    비용 단위는 **판(edition)**이다. 같은 상품이라도 판마다 따로 등록해야 한다.
    실제 단가 체계(판당 정액 / 용량 기준 / 구간 정액)는 벤더 계약에 따르며,
    여기서는 판당 정액을 가정한다. 다른 체계면 `price_for`만 바꾸면 된다.
    """

    price_per_edition: int | None = None
    """판 1건 등록 비용. None이면 금액 미확정 — 화면에 금액을 표시하지 않는다."""

    currency: str = "원"

    def price_for(self, editions: int = 1) -> int | None:
        if self.price_per_edition is None:
            return None
        return self.price_per_edition * max(1, editions)

    def format(self, editions: int = 1) -> str:
        """FA에게 보여줄 금액 문구."""
        amount = self.price_for(editions)
        if amount is None:
            return "등록 비용"
        return f"{amount:,}{self.currency}"


#: 금액이 아직 정해지지 않은 상태의 기본값.
#: 벤더 단가가 확정되면 설정에서 주입한다.
UNPRICED = TermsPricing()
