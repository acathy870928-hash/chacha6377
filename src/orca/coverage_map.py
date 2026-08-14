"""보장맵 — 고객이 가진 담보를 계약별로 펼쳐 놓은 것.

## 이름을 「보장맵」으로 정한 이유

담기는 구조는 **고객 → 계약(약관) → 담보**의 3층이다. 개발 관점에서는 트리지만
FA 화면에 「트리」를 쓰면 무슨 말인지 전달되지 않는다.

| 후보 | 문제 |
| --- | --- |
| 보장트리 | 개발 용어. FA가 쓰는 말이 아니다 |
| 보장분석 | **보장분석 업체 서비스명과 겹친다.** 출처가 다른 것을 같은 이름으로 부르면 안 된다 |
| 보장표 · 보장목록 | 평면적이다. 계약별로 나뉜다는 점이 안 드러난다 |
| **보장맵** | 「어디에 무엇이 있는지 펼쳐 본다」가 그대로 전달된다. 계층도 담긴다 |

「보장맵을 채운다 / 비어 있다」처럼 **미완성 상태를 말하기 좋다는 점**도 중요하다.
약관을 하나씩 등록하며 완성해 가는 것이 이 기능의 핵심이기 때문이다.

## 무엇으로 채워지는가

시작 범위에서는 **약관**이 출처다. 약관에는 그 상품에서 가입할 수 있는 담보가
전부 들어 있으므로, 약관을 등록하면 「이 상품에 어떤 담보가 있는지」가 채워진다.
다만 **실제 가입 여부와 가입금액은 약관이 모른다.**

    약관 등록      → 담보 이름이 채워진다 (가입 여부는 미확인)
    FA가 증권 확인 → 가입 여부 · 금액을 채운다
    보장분석 연동  → 위 단계가 자동으로 채워진다 (초개인화)

그래서 보장맵은 처음에 **미확인 상태로 시작해 점점 확정된다.**
확정되지 않은 담보를 확정된 것처럼 보이면 안 되므로 상태를 명시적으로 들고 간다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .coverage import normalize_benefit_name


class BenefitStatus(Enum):
    """담보 하나의 확인 상태."""

    ENROLLED = "enrolled"
    """가입이 확인됐다. 금액이 있으면 금액도 확정이다."""

    NOT_ENROLLED = "not_enrolled"
    """가입하지 않은 것으로 확인됐다."""

    UNKNOWN = "unknown"
    """약관에는 있으나 가입 여부를 모른다. **기본값이다.**

    약관만 등록한 상태에서는 전부 이 상태다.
    이걸 가입으로 취급하면 미가입 담보를 「나온다」고 답하게 된다.
    """


class BenefitSource(Enum):
    """이 담보 정보가 어디서 왔는지."""

    TERMS = "terms"
    """약관에서. 담보 이름만 알 수 있고 가입 여부는 모른다."""

    COVERAGE_REPORT = "coverage_report"
    """보장분석 리포트에서. 가입 여부와 금액이 함께 온다."""

    MANUAL = "manual"
    """FA가 증권을 보고 직접 입력했다."""


@dataclass(frozen=True)
class MappedBenefit:
    """보장맵의 담보 한 줄."""

    name: str
    status: BenefitStatus = BenefitStatus.UNKNOWN
    amount: int | None = None
    """가입금액(만원). 상태가 ENROLLED일 때만 의미가 있다."""

    source: BenefitSource = BenefitSource.TERMS

    def matches(self, keyword: str) -> bool:
        needle = normalize_benefit_name(keyword)
        return bool(needle) and needle in normalize_benefit_name(self.name)

    @property
    def is_confirmed(self) -> bool:
        return self.status is not BenefitStatus.UNKNOWN


@dataclass(frozen=True)
class MapEntry:
    """계약(= 등록된 약관) 하나와 그 담보들."""

    insurer: str
    product_name: str
    edition_label: str | None = None
    contract_year: int | None = None
    benefits: tuple[MappedBenefit, ...] = field(default_factory=tuple)

    @property
    def label(self) -> str:
        return f"{self.product_name} · {self.edition_label}" if self.edition_label else self.product_name

    @property
    def confirmed_count(self) -> int:
        return sum(1 for b in self.benefits if b.is_confirmed)

    def find(self, keyword: str) -> tuple[MappedBenefit, ...]:
        return tuple(b for b in self.benefits if b.matches(keyword))


@dataclass(frozen=True)
class CoverageMap:
    """한 고객의 보장맵.

    고객별로 여러 상품에 가입하므로 계약이 여러 개다.
    같은 담보가 여러 계약에 흩어져 있는 것이 정상이며, 그것을 보여주는 것이 목적이다.
    """

    customer_id: str = ""
    customer_name: str = ""
    entries: tuple[MapEntry, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not self.entries

    @property
    def contract_count(self) -> int:
        return len(self.entries)

    @property
    def benefit_count(self) -> int:
        return sum(len(e.benefits) for e in self.entries)

    @property
    def confirmed_ratio(self) -> float:
        """가입 여부가 확인된 담보 비율. 보장맵 완성도다.

        약관만 등록한 직후에는 0이고, 증권 확인이나 보장분석 연동으로 올라간다.
        """
        total = self.benefit_count
        if not total:
            return 0.0
        return sum(e.confirmed_count for e in self.entries) / total

    def find(self, keyword: str) -> tuple[tuple[MapEntry, MappedBenefit], ...]:
        """담보명으로 전 계약을 훑는다. 계약과 담보를 짝으로 돌려준다."""
        found: list[tuple[MapEntry, MappedBenefit]] = []
        for entry in self.entries:
            for benefit in entry.find(keyword):
                found.append((entry, benefit))
        return tuple(found)

    def enrolled(self, keyword: str) -> tuple[tuple[MapEntry, MappedBenefit], ...]:
        """그중 가입이 확인된 것만."""
        return tuple(
            (entry, benefit)
            for entry, benefit in self.find(keyword)
            if benefit.status is BenefitStatus.ENROLLED
        )

    def unconfirmed(self, keyword: str) -> tuple[tuple[MapEntry, MappedBenefit], ...]:
        """약관에는 있으나 가입 여부를 모르는 것.

        **답변에서 이걸 빠뜨리면 안 된다.** 「없다」가 아니라 「확인이 안 됐다」이므로
        FA가 증권으로 확인할 대상이 된다.
        """
        return tuple(
            (entry, benefit)
            for entry, benefit in self.find(keyword)
            if benefit.status is BenefitStatus.UNKNOWN
        )

    def with_entry(self, entry: MapEntry) -> CoverageMap:
        """약관을 하나 더 등록한 결과. 같은 계약이면 교체한다."""
        key = (entry.insurer, entry.product_name, entry.contract_year)
        kept = tuple(
            e for e in self.entries if (e.insurer, e.product_name, e.contract_year) != key
        )
        return CoverageMap(
            customer_id=self.customer_id,
            customer_name=self.customer_name,
            entries=kept + (entry,),
        )


def summarize_gap(coverage_map: CoverageMap, keyword: str) -> str:
    """이 담보에 대해 보장맵이 무엇을 말할 수 있는지 한 줄로.

    확정 · 미확인 · 없음을 구분해 말한다. 셋을 섞으면 답이 틀린다.
    """
    if coverage_map.is_empty:
        return "등록된 약관이 없어 이 고객 기준으로는 확인할 수 없습니다."

    enrolled = coverage_map.enrolled(keyword)
    unknown = coverage_map.unconfirmed(keyword)

    if enrolled:
        parts = [f"가입 확인 {len(enrolled)}건"]
        if unknown:
            parts.append(f"확인 필요 {len(unknown)}건")
        return " · ".join(parts)
    if unknown:
        return f"약관에는 있으나 가입 여부 미확인 {len(unknown)}건 — 증권 확인이 필요합니다."
    return "등록된 약관에서 해당 담보를 찾지 못했습니다."
