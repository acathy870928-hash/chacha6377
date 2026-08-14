"""FA별 담당 고객 목록.

보장분석을 쓰려면 **먼저 「누구 기준인가」가 정해져야 한다.**
그 선택을 대화 중에 암묵적으로 하지 않고 화면에서 명시적으로 하게 만든다.

이유가 두 가지다.

**1. 안전.** FA가 담당하지 않는 고객의 보장분석을 열 수 없어야 한다.
목록 자체를 담당 고객으로 한정하면(`advisor_id`) 접근 통제가 화면 단계에서 걸린다.
대화 중에 이름으로 고객을 특정하는 방식은 오조회를 만들기 쉽다.

**2. 정확도.** 고객이 정해지면 계약 · 담보 · 약관 판이 전부 따라오므로
되묻기가 사라진다. 반대로 고객이 안 정해진 채로 보상 질문이 들어오면
일반 약관 경로(되묻기)로 빠진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .versioning import ApproxDate


class CustomerCategory(Enum):
    """고객 목록을 나누는 기준. FA가 상담을 시작하는 통로다."""

    RECENT = "recent"
    """최근 상담한 고객. 상담이 이어지는 경우가 많아 첫 번째 통로가 된다."""

    COVERAGE_GAP = "coverage_gap"
    """보장 부족 항목이 많은 고객. 제안 기회."""

    MATURITY_SOON = "maturity_soon"
    """만기 · 갱신이 다가오는 계약이 있는 고객. 시기를 놓치면 안 된다."""

    NEEDS_ANALYSIS = "needs_analysis"
    """보장분석이 없거나 오래된 고객. 이 상태면 되묻기 경로로 빠진다."""


#: 보장분석을 다시 받아야 한다고 보는 기준(일).
STALE_ANALYSIS_DAYS = 365

#: 만기 임박으로 보는 기준(개월).
MATURITY_SOON_MONTHS = 6


@dataclass(frozen=True)
class CustomerSummary:
    """고객 목록 한 줄. 보장분석 리포트 요약에서 만든다."""

    customer_id: str
    name: str
    advisor_id: str
    """담당 FA. **목록은 이 값으로만 조회된다.**"""

    contract_count: int = 0
    monthly_premium: int | None = None

    benefit_total: int = 0
    """보장분석이 평가한 전체 보장 항목 수(리포트의 41개 등)."""

    benefit_shortfall: int = 0
    """그중 부족 판정 항목 수."""

    note: str = ""
    """동명이인을 가르기 위한 최소 메모. 생년이나 관계 등 FA가 알아볼 수 있는 짧은 표기.

    **주민번호 · 연락처 같은 식별정보를 여기 담지 않는다.**
    이 서비스에 필요한 것은 「누구의 계약인지 FA가 구분할 수 있는가」까지다.
    """

    analyzed_on: date | None = None
    """보장분석 조회일. 없으면 분석 이력이 없다는 뜻이다."""

    last_consulted_on: date | None = None
    next_maturity: ApproxDate | None = None

    @property
    def has_analysis(self) -> bool:
        return self.analyzed_on is not None

    @property
    def shortfall_ratio(self) -> float:
        if not self.benefit_total:
            return 0.0
        return self.benefit_shortfall / self.benefit_total

    def is_stale(self, today: date) -> bool:
        """분석이 오래되어 다시 받아야 하는지."""
        if self.analyzed_on is None:
            return True
        return (today - self.analyzed_on).days > STALE_ANALYSIS_DAYS

    def categories(self, today: date) -> set[CustomerCategory]:
        """이 고객이 속하는 분류. 한 고객이 여러 곳에 들어갈 수 있다."""
        found: set[CustomerCategory] = set()

        if self.is_stale(today):
            found.add(CustomerCategory.NEEDS_ANALYSIS)

        # 분석이 없으면 부족 여부를 판단할 근거가 없다.
        if self.has_analysis and self.shortfall_ratio >= 0.5:
            found.add(CustomerCategory.COVERAGE_GAP)

        if self.last_consulted_on is not None:
            found.add(CustomerCategory.RECENT)

        if self._maturity_within(today, MATURITY_SOON_MONTHS):
            found.add(CustomerCategory.MATURITY_SOON)

        return found

    def _maturity_within(self, today: date, months: int) -> bool:
        if self.next_maturity is None:
            return False
        due = self.next_maturity
        elapsed = (due.year - today.year) * 12 + ((due.month or 1) - today.month)
        return 0 <= elapsed <= months


@dataclass
class CustomerDirectory:
    """담당 고객 명부.

    조회는 **언제나 FA 단위로 한정된다.** 담당이 아닌 고객은 검색으로도 나오지 않는다.
    """

    customers: list[CustomerSummary] = field(default_factory=list)

    def for_advisor(self, advisor_id: str) -> list[CustomerSummary]:
        return [c for c in self.customers if c.advisor_id == advisor_id]

    def search(self, advisor_id: str, name: str) -> list[CustomerSummary]:
        """이름으로 담당 고객을 찾는다. 담당 밖은 검색되지 않는다."""
        needle = name.strip()
        pool = self.for_advisor(advisor_id)
        if not needle:
            return pool
        return [c for c in pool if needle in c.name]

    def by_category(
        self,
        advisor_id: str,
        category: CustomerCategory,
        *,
        today: date,
    ) -> list[CustomerSummary]:
        """분류별 목록. 각 분류에 맞는 순서로 정렬해 돌려준다."""
        matched = [c for c in self.for_advisor(advisor_id) if category in c.categories(today)]
        return sorted(matched, key=_sort_key(category, today))

    def get(self, advisor_id: str, customer_id: str) -> CustomerSummary | None:
        """고객 하나를 가져온다.

        **담당이 아니면 None이다.** 화면에서 걸렀더라도 여기서 한 번 더 막는다.
        """
        return next(
            (
                c
                for c in self.customers
                if c.customer_id == customer_id and c.advisor_id == advisor_id
            ),
            None,
        )

    def duplicates(self, advisor_id: str, name: str) -> list[CustomerSummary]:
        """같은 이름의 담당 고객. **등록 전에 보여줘 중복 생성을 막는다.**

        FA는 고객이 수십~수백 명이라 이미 만든 고객을 다시 만들기 쉽다.
        중복이 생기면 약관북과 보장맵이 둘로 쪼개져 답변이 반쪽이 된다.
        """
        needle = name.strip()
        if not needle:
            return []
        return [c for c in self.for_advisor(advisor_id) if c.name == needle]

    def add(
        self,
        advisor_id: str,
        name: str,
        *,
        note: str = "",
        customer_id: str | None = None,
    ) -> CustomerSummary:
        """고객을 만든다. **이름 하나면 충분하다.**

        상담을 시작하려면 「누구 기준인가」만 정해지면 되므로 필수값은 이름뿐이다.
        생년 · 연락처 같은 정보는 요구하지 않는다 — 없어도 기능이 돌고,
        받으면 보관 · 파기 책임만 늘어난다(`docs/privacy.md`).

        동명이인은 `note`로 가른다. 중복 여부는 호출 전에 `duplicates()`로 확인한다.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("고객 이름은 비워 둘 수 없습니다.")

        customer = CustomerSummary(
            customer_id=customer_id or _make_customer_id(advisor_id, cleaned, len(self.customers)),
            name=cleaned,
            advisor_id=advisor_id,
            note=note.strip(),
        )
        self.customers.append(customer)
        return customer

    def counts(self, advisor_id: str, *, today: date) -> dict[CustomerCategory, int]:
        """분류별 인원. 화면의 칩에 붙일 숫자다."""
        result = {category: 0 for category in CustomerCategory}
        for customer in self.for_advisor(advisor_id):
            for category in customer.categories(today):
                result[category] += 1
        return result


def _make_customer_id(advisor_id: str, name: str, seq: int) -> str:
    """고객 식별자. 이름을 그대로 키로 쓰지 않는다(동명이인 · 개명)."""
    return f"{advisor_id}-{seq + 1:04d}"


def _sort_key(category: CustomerCategory, today: date):
    if category is CustomerCategory.RECENT:
        # 최근 상담일이 늦은 순 → 날짜를 음수 정렬할 수 없으므로 역순 키를 만든다.
        return lambda c: (-(c.last_consulted_on or date.min).toordinal(), c.name)
    if category is CustomerCategory.COVERAGE_GAP:
        return lambda c: (-c.shortfall_ratio, c.name)
    if category is CustomerCategory.MATURITY_SOON:
        return lambda c: (
            (c.next_maturity.year, c.next_maturity.month or 1) if c.next_maturity else (9999, 12),
            c.name,
        )
    # NEEDS_ANALYSIS — 오래된 순, 이력 없는 고객이 먼저.
    return lambda c: (c.analyzed_on or date.min, c.name)
