"""가입 시점 → 적용 약관 판 특정.

보상 질문의 정확도는 '어느 판을 봤는가'에서 갈린다.
계약 정보(Cloud DATA)가 이번 범위 밖이므로 가입 시점은 FA에게서 받는다.
여기서는 받은 시점을 판으로 옮기는 규칙만 다룬다. 순수 로직이라 단독으로 검증 가능하다.

적용 규칙: 계약일이 속하는 판 = 시행일이 계약일 이하인 판 중 시행일이 가장 늦은 판.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .types import PolicyEdition, Product


@dataclass(frozen=True)
class ApproxDate:
    """FA가 기억하는 수준의 가입 시점.

    정확한 일자까지 기억하지 못하는 경우가 흔하므로 연 · 월까지만 받을 수 있게 한다.
    다만 그 달 안에서 판이 바뀌면 월 단위로는 판을 확정할 수 없다(→ NEEDS_EXACT_DATE).
    """

    year: int
    month: int | None = None
    day: int | None = None

    @property
    def is_exact(self) -> bool:
        return self.month is not None and self.day is not None

    def range(self) -> tuple[date, date]:
        """이 입력이 가리킬 수 있는 날짜 구간 (양끝 포함)."""
        if self.month is None:
            return date(self.year, 1, 1), date(self.year, 12, 31)
        if self.day is None:
            last = calendar.monthrange(self.year, self.month)[1]
            return date(self.year, self.month, 1), date(self.year, self.month, last)
        exact = date(self.year, self.month, self.day)
        return exact, exact


class EditionStatus(Enum):
    RESOLVED = "resolved"
    """판이 하나로 확정됐다. 그대로 검색 필터에 넘긴다."""

    SINGLE_EDITION = "single_edition"
    """상품에 판이 하나뿐이다. 가입 시점을 묻지 않고 진행한다."""

    NEEDS_CONTRACT_DATE = "needs_contract_date"
    """판이 여럿인데 가입 시점이 없다. FA에게 물어야 한다."""

    NEEDS_EXACT_DATE = "needs_exact_date"
    """받은 시점이 판 경계에 걸쳐 있다. 일자까지 물어야 확정된다."""

    BEFORE_COVERAGE = "before_coverage"
    """가입 시점이 색인된 가장 이른 판보다 앞선다. 약관 자체가 없다."""

    NO_EDITIONS = "no_editions"
    """해당 상품의 판 정보가 없다. 벤더 인덱스 확인이 필요하다."""


@dataclass(frozen=True)
class EditionResolution:
    status: EditionStatus
    edition: PolicyEdition | None = None
    candidates: tuple[PolicyEdition, ...] = field(default_factory=tuple)
    """되묻기 선택지로 그대로 쓸 수 있는 후보 목록."""

    @property
    def is_settled(self) -> bool:
        """더 묻지 않고 검색으로 넘어가도 되는 상태인지."""
        return self.status in (EditionStatus.RESOLVED, EditionStatus.SINGLE_EDITION)


def sorted_editions(product: Product) -> tuple[PolicyEdition, ...]:
    return tuple(sorted(product.editions, key=lambda e: e.effective_from))


def resolve_edition(
    product: Product,
    contract_date: ApproxDate | None = None,
) -> EditionResolution:
    """상품과 가입 시점으로 적용 약관 판을 특정한다.

    확정되지 않으면 임의로 최신 판을 고르지 않는다. 무엇을 더 물어야 하는지를 돌려준다.
    """
    editions = sorted_editions(product)

    if not editions:
        return EditionResolution(status=EditionStatus.NO_EDITIONS)

    # 판이 하나뿐이면 시점을 물을 이유가 없다. 되묻기를 줄이는 지점.
    if len(editions) == 1:
        return EditionResolution(
            status=EditionStatus.SINGLE_EDITION,
            edition=editions[0],
            candidates=editions,
        )

    if contract_date is None:
        return EditionResolution(
            status=EditionStatus.NEEDS_CONTRACT_DATE,
            candidates=editions,
        )

    start, end = contract_date.range()

    if end < editions[0].effective_from:
        # 입력 구간 전체가 색인 범위보다 앞선다.
        return EditionResolution(
            status=EditionStatus.BEFORE_COVERAGE,
            candidates=editions,
        )

    matched_start = _edition_at(editions, start)
    matched_end = _edition_at(editions, end)

    if matched_start is not None and matched_start == matched_end:
        return EditionResolution(
            status=EditionStatus.RESOLVED,
            edition=matched_start,
            candidates=editions,
        )

    # 입력 구간 안에서 판이 바뀐다. 일자까지 받아야 확정된다.
    overlapping = tuple(e for e in editions if _overlaps(e, start, end))
    return EditionResolution(
        status=EditionStatus.NEEDS_EXACT_DATE,
        candidates=overlapping or editions,
    )


_DATE_PATTERNS = (
    # 2023-04-15 / 2023.4.15 / 2023/04/15 / 2023년 4월 15일
    re.compile(r"(?P<y>\d{4})\s*[-./년]\s*(?P<m>\d{1,2})\s*[-./월]\s*(?P<d>\d{1,2})\s*일?"),
    # 2023-04 / 2023.4 / 2023년 4월
    re.compile(r"(?P<y>\d{4})\s*[-./년]\s*(?P<m>\d{1,2})\s*월?(?!\s*\d)"),
    # 23년 4월 15일
    re.compile(r"(?P<y>\d{2})\s*년\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일"),
    # 23년 4월
    re.compile(r"(?P<y>\d{2})\s*년\s*(?P<m>\d{1,2})\s*월"),
    # 2023년
    re.compile(r"(?P<y>\d{4})\s*년"),
)


def parse_approx_date(text: str, *, today: date | None = None) -> ApproxDate | None:
    """FA가 말한 가입 시점 표현을 ApproxDate로.

    「2023년 4월」처럼 월까지만 말하는 경우가 흔하므로 부분 입력을 그대로 보존한다.
    확정할 수 없는 부분을 임의로 채우지 않는 것이 이 함수의 요점이다.
    """
    if not text:
        return None

    current_year = (today or date.today()).year

    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        groups = match.groupdict()
        year = int(groups["y"])
        if len(groups["y"]) == 2:
            # 두 자리 연도: 미래가 되면 1900년대로 본다. (예: 95년 가입)
            year = 2000 + year if 2000 + year <= current_year else 1900 + year

        month = int(groups["m"]) if groups.get("m") else None
        if month is not None and not 1 <= month <= 12:
            continue

        day = int(groups["d"]) if groups.get("d") else None
        if month is not None and day is not None:
            last = calendar.monthrange(year, month)[1]
            if not 1 <= day <= last:
                continue

        return ApproxDate(year=year, month=month, day=day)

    return None


def _edition_at(editions: tuple[PolicyEdition, ...], when: date) -> PolicyEdition | None:
    """해당 일자에 적용되던 판. 시행일이 when 이하인 판 중 가장 늦은 것."""
    found: PolicyEdition | None = None
    for edition in editions:
        if edition.effective_from <= when:
            found = edition
        else:
            break
    if found is not None and not found.covers(when):
        return None
    return found


def _overlaps(edition: PolicyEdition, start: date, end: date) -> bool:
    if edition.effective_to is not None and edition.effective_to < start:
        return False
    return edition.effective_from <= end
