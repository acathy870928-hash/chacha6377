"""고객 ↔ 약관 연결 장부.

보상 질문에 답하고 나면 그 약관이 **어느 고객의 계약이었는지**를 함께 남긴다.
이것이 쌓이면 고객별 약관 목록이 만들어진다.

## 왜 필요한가

**1. FA가 쓸 이유가 생긴다.**
한 번 확인한 약관이 그 고객에 묶여 남으므로, 다음 상담에서 다시 찾을 필요가 없다.
쓸수록 자기 고객 자료가 쌓이는 구조여야 FA가 도구를 계속 쓴다.
답변하고 끝나면 매번 처음부터 다시 특정해야 한다.

**2. 되묻기가 점점 줄어든다.**
보장분석이 없는 고객이라도, 상담하면서 하나씩 연결되면
그 고객의 약관이 다음번엔 바로 후보로 뜬다.
보장분석이 위에서 한 번에 채우는 방식이라면, 이 장부는 **아래에서 하나씩 쌓는 방식**이다.
둘 다 같은 결과(고객 → 계약 → 약관 판)에 도달한다.

**3. 유료로 확보한 약관이 자산으로 남는다.**
비용을 들여 등록한 약관이 누구의 계약 때문이었는지 남으므로,
그 고객 상담에서 반복해서 쓰인다. 비용이 한 번 쓰고 사라지지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class LinkSource(Enum):
    """이 연결이 어떻게 만들어졌는지."""

    ASKED = "asked"
    """FA가 상담 중 답변을 받고 「이 고객 건」으로 지정했다."""

    COVERAGE = "coverage"
    """보장분석 리포트에서 자동으로 확인됐다."""

    PURCHASED = "purchased"
    """미등록 약관을 확보 요청해 등록됐다. 비용이 들어간 건이다."""


@dataclass(frozen=True)
class CustomerTermsLink:
    """고객 한 명과 약관 하나의 연결."""

    customer_id: str
    customer_name: str
    advisor_id: str

    insurer: str
    product_name: str
    edition_label: str | None = None
    contract_year: int | None = None

    source: LinkSource = LinkSource.ASKED
    linked_on: date | None = None

    @property
    def terms_key(self) -> tuple[str, str, int | None]:
        """약관 식별 키. 같은 약관이면 고객이 달라도 같은 값이다."""
        return (self.insurer, self.product_name, self.contract_year)

    @property
    def label(self) -> str:
        if self.edition_label:
            return f"{self.product_name} · {self.edition_label}"
        return self.product_name


@dataclass(frozen=True)
class TermsFolder:
    """약관북의 고객 폴더 하나.

    첫 화면은 질문창이고, 약관북은 **별도 메뉴**다.
    상담 중 쌓인 약관이 고객별 폴더로 정리돼 여기서 다시 열린다.
    """

    customer_id: str
    customer_name: str
    terms: tuple[CustomerTermsLink, ...] = ()

    @property
    def count(self) -> int:
        return len(self.terms)

    @property
    def updated_on(self) -> date | None:
        """가장 최근에 약관이 추가된 날. 폴더 정렬 기준."""
        dates = [t.linked_on for t in self.terms if t.linked_on]
        return max(dates) if dates else None

    @property
    def insurers(self) -> tuple[str, ...]:
        """폴더에 든 보험사들. 폴더 요약에 쓴다."""
        seen: list[str] = []
        for term in self.terms:
            if term.insurer and term.insurer not in seen:
                seen.append(term.insurer)
        return tuple(seen)


@dataclass
class TermsLedger:
    """연결 장부. 고객별 · 약관별 양방향으로 조회한다.

    화면에서는 **약관북**으로 보인다. 고객 = 폴더, 연결된 약관 = 폴더 안의 항목.
    """

    links: list[CustomerTermsLink] = field(default_factory=list)

    def link(self, link: CustomerTermsLink) -> bool:
        """연결을 추가한다. 이미 있으면 추가하지 않고 False를 돌려준다."""
        for existing in self.links:
            if (
                existing.customer_id == link.customer_id
                and existing.terms_key == link.terms_key
            ):
                return False
        self.links.append(link)
        return True

    def terms_for(self, customer_id: str) -> list[CustomerTermsLink]:
        """이 고객에 연결된 약관들. **다음 상담에서 바로 후보로 띄운다.**"""
        return [ln for ln in self.links if ln.customer_id == customer_id]

    def customers_for(self, terms_key: tuple[str, str, int | None]) -> list[CustomerTermsLink]:
        """이 약관을 쓰는 고객들.

        확보 비용을 들인 약관이 몇 명에게 쓰이는지 보여준다.
        여러 고객에 걸릴수록 그 등록은 잘 산 것이다.
        """
        return [ln for ln in self.links if ln.terms_key == terms_key]

    def customer_count(self, terms_key: tuple[str, str, int | None]) -> int:
        return len({ln.customer_id for ln in self.customers_for(terms_key)})

    def for_advisor(self, advisor_id: str) -> list[CustomerTermsLink]:
        return [ln for ln in self.links if ln.advisor_id == advisor_id]

    def customers_with_terms(self, advisor_id: str) -> dict[str, int]:
        """FA의 고객별 연결 약관 수. 고객 목록에 배지로 붙인다."""
        counts: dict[str, int] = {}
        for link in self.for_advisor(advisor_id):
            counts[link.customer_id] = counts.get(link.customer_id, 0) + 1
        return counts

    def is_linked(self, customer_id: str, terms_key: tuple[str, str, int | None]) -> bool:
        return any(
            ln.customer_id == customer_id and ln.terms_key == terms_key for ln in self.links
        )

    def recent_products(self, advisor_id: str, limit: int = 8) -> list[CustomerTermsLink]:
        """이 FA가 최근 등록한 상품. **운영 지표용이며 등록 화면에 내놓지 않는다.**

        이 목록은 결국 다른 고객에게 등록했던 상품이라, 지금 상담 중인 고객과
        무관한 계약을 화면에 끌어오게 된다. 그래서 등록 경로로는 쓰지 않고,
        어떤 상품이 자주 등록되는지(= 초기 등록 목록 산정 근거)를 보는 데만 쓴다.
        같은 상품은 한 번만 내보낸다.
        """
        seen: set[tuple[str, str, int | None]] = set()
        picked: list[CustomerTermsLink] = []
        for link in sorted(
            self.for_advisor(advisor_id),
            key=lambda ln: ln.linked_on or date.min,
            reverse=True,
        ):
            if link.terms_key in seen:
                continue
            seen.add(link.terms_key)
            picked.append(link)
            if len(picked) >= limit:
                break
        return picked

    def folders(self, advisor_id: str) -> list[TermsFolder]:
        """약관북 폴더 목록. **최근에 약관이 추가된 고객이 위로 온다.**

        상담이 이어지는 고객이 위에 있어야 다시 여는 동작이 빨라진다.
        """
        grouped: dict[str, list[CustomerTermsLink]] = {}
        names: dict[str, str] = {}
        for link in self.for_advisor(advisor_id):
            grouped.setdefault(link.customer_id, []).append(link)
            names[link.customer_id] = link.customer_name

        folders = [
            TermsFolder(
                customer_id=customer_id,
                customer_name=names[customer_id],
                terms=tuple(sorted(items, key=lambda t: t.linked_on or date.min, reverse=True)),
            )
            for customer_id, items in grouped.items()
        ]
        folders.sort(
            key=lambda f: (-(f.updated_on or date.min).toordinal(), f.customer_name)
        )
        return folders

    def folder(self, advisor_id: str, customer_id: str) -> TermsFolder | None:
        """폴더 하나를 연다. 담당이 아니면 None이다."""
        return next(
            (f for f in self.folders(advisor_id) if f.customer_id == customer_id),
            None,
        )

    def search_folders(self, advisor_id: str, keyword: str) -> list[TermsFolder]:
        """고객명 또는 상품명으로 폴더를 찾는다.

        FA는 「누구 폴더」로도 찾지만 「그 어린이보험 어디 있더라」로도 찾는다.
        """
        needle = keyword.strip()
        if not needle:
            return self.folders(advisor_id)
        return [
            folder
            for folder in self.folders(advisor_id)
            if needle in folder.customer_name
            or any(needle in term.product_name for term in folder.terms)
        ]
