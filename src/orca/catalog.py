"""상품 카탈로그 — 되묻기 선택지의 원천.

FA에게 「어느 상품 기준으로 볼까요?」를 물으려면 고를 수 있는 상품 목록이 있어야 한다.
목록의 출처는 보험회사 공시실이 될 수 있으나, **기준은 벤더 인덱스**여야 한다.
공시실에만 있고 벤더 인덱스에 약관이 없는 상품을 선택지로 띄우면
FA가 고른 뒤에 「자료 없음」이 나와 되묻기가 헛수고가 되기 때문이다.
(`Product.indexed` 참고)

iFA는 GA이므로 취급 상품이 여러 보험사에 걸쳐 많다.
따라서 전체 목록을 그대로 칩으로 띄울 수 없고, 입력한 이름으로 좁힌 뒤 제시한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .types import Product

#: 상품명 앞뒤에 붙지만 상품을 구분하지 않는 표기.
#: 「무배당 ○○운전자보험」과 「○○운전자보험」은 같은 상품을 가리키는 경우가 많다.
_NOISE_TOKENS = ("무배당", "유배당", "무)", "유)", "(무)", "(유)")

_NON_NAME_CHARS = re.compile(r"[\s\-_·・,.()\[\]{}「」『』<>《》\"']+")


def normalize_product_name(name: str) -> str:
    """상품명 비교용 정규화.

    공시실 표기 · 벤더 인덱스 표기 · FA가 말하는 이름이 서로 조금씩 다르다.
    배당 표기와 공백 · 구두점을 걷어내 비교 가능한 형태로 만든다.
    상품을 실제로 구분하는 표기(갱신형 / 비갱신형, 세대 표기 등)는 남긴다.
    """
    text = name.strip()
    for token in _NOISE_TOKENS:
        text = text.replace(token, "")
    return _NON_NAME_CHARS.sub("", text)


@dataclass(frozen=True)
class CatalogEntry:
    product: Product
    aliases: tuple[str, ...] = ()
    """공시실 표기 등 같은 상품을 가리키는 다른 이름."""

    def names(self) -> tuple[str, ...]:
        return (self.product.name, *self.aliases)


class InMemoryProductCatalog:
    """메모리 기반 카탈로그.

    출처가 벤더 API든 공시실 수집분이든, 적재된 결과를 이 형태로 담아 쓴다.
    """

    def __init__(self, entries: list[CatalogEntry] | list[Product], *, max_options: int = 8):
        self._entries: list[CatalogEntry] = [
            entry if isinstance(entry, CatalogEntry) else CatalogEntry(product=entry)
            for entry in entries
        ]
        self._max_options = max_options

    def search(self, name: str) -> list[Product]:
        """이름으로 상품 후보를 찾는다.

        이름이 정확히 일치해도 후보를 단독으로 확정하지 않는다.
        보험 상품은 「○○보험」과 「○○보험 플러스」처럼 시리즈로 나오고,
        FA는 짧은 쪽 이름으로 말하는 경우가 많다.
        후보가 둘 이상이면 되묻는 편이, 잘못된 상품 약관으로 보상을 답하는 것보다 낫다.
        """
        indexed = [e for e in self._entries if e.product.indexed]
        needle = normalize_product_name(name) if name else ""

        if not needle:
            return [e.product for e in indexed][: self._max_options]

        matched = [
            e
            for e in indexed
            if any(
                needle in normalize_product_name(n) or normalize_product_name(n) in needle
                for n in e.names()
            )
        ]
        return [e.product for e in matched][: self._max_options]

    def search_registry(self, name: str) -> list[Product]:
        """등록 여부와 무관하게 상품 마스터 전체에서 찾는다.

        약관이 아직 등록되지 않은 상품을 식별하기 위한 조회다.
        「우리가 아는 상품인데 약관만 없다」와 「그런 상품 자체를 모른다」는
        FA에게 안내할 내용이 다르다.
        """
        needle = normalize_product_name(name) if name else ""
        if not needle:
            return [e.product for e in self._entries][: self._max_options]

        matched = [
            e
            for e in self._entries
            if any(
                needle in normalize_product_name(n) or normalize_product_name(n) in needle
                for n in e.names()
            )
        ]
        return [e.product for e in matched][: self._max_options]

    def get(self, product_id: str) -> Product | None:
        return next((e.product for e in self._entries if e.product.product_id == product_id), None)

    def __len__(self) -> int:
        return len(self._entries)
