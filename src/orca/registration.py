"""약관 등록 경로 — 쉬운 길을 먼저 보여준다.

보험사 → 상품 검색 → 등록은 한 건에 세 단계다.
고객 한 명이 계약을 대여섯 건 가지고 있으므로 **그대로 두면 열다섯 단계**가 되고,
FA는 한 번 해보고 다시 하지 않는다.

그래서 등록 경로를 넷으로 늘리고, **빠른 것부터 보여준다.**

    1. 보장분석 리포트 올리기   계약 전부가 한 번에    ← FA가 이미 가지고 있다
    2. 최근 등록한 상품에서     탭 한 번               ← 인기 상품은 고객마다 겹친다
    3. 대화 중 바로 등록        말한 김에              ← 이미 상품을 말했다
    4. 보험사 → 상품 검색       확실하지만 느리다      ← 마지막 수단

1번이 결정적이다. 보장분석 리포트는 **FA가 이미 발행받아 가지고 있는 문서**이고,
거기에 계약별 보험사 · 상품명 · 계약년월이 전부 들어 있다.
그 파일 하나로 보장맵의 뼈대가 채워진다.

주의: 리포트로 채워도 **약관이 등록된 것은 아니다.** 계약을 알게 됐을 뿐이며,
약관 등록 여부는 별개로 확인해 미등록 건은 확보 요청으로 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegistrationMethod(Enum):
    """약관(계약)을 보장맵에 넣는 방법."""

    REPORT_UPLOAD = "report_upload"
    """보장분석 리포트 파일을 올린다. 계약 전부가 한 번에 들어온다."""

    RECENT_REUSE = "recent_reuse"
    """최근 등록한 상품에서 고른다. 인기 상품은 고객마다 겹친다."""

    FROM_CHAT = "from_chat"
    """대화에서 이미 말한 상품을 그대로 등록한다."""

    SEARCH = "search"
    """보험사 → 상품 검색. 확실하지만 느리다."""


#: 방법별 예상 소요. 화면에서 「빠른 순」으로 정렬하는 근거다.
_SPEED_RANK = {
    RegistrationMethod.REPORT_UPLOAD: 0,
    RegistrationMethod.FROM_CHAT: 1,
    RegistrationMethod.RECENT_REUSE: 2,
    RegistrationMethod.SEARCH: 3,
}


@dataclass(frozen=True)
class RegistrationOption:
    """등록 방법 하나. 화면의 버튼 한 개에 대응한다."""

    method: RegistrationMethod
    label: str
    hint: str = ""
    expected_entries: int | None = None
    """이 방법으로 한 번에 들어올 계약 수. 모르면 None."""

    @property
    def is_bulk(self) -> bool:
        return (self.expected_entries or 0) > 1


def suggest_methods(
    *,
    has_report: bool = False,
    recent_count: int = 0,
    mentioned_product: str | None = None,
) -> list[RegistrationOption]:
    """지금 상황에서 쓸 수 있는 등록 방법을 빠른 순으로.

    쓸 수 없는 방법은 아예 빼서 화면을 단순하게 유지한다.
    (최근 등록 이력이 없는 첫 FA에게 「최근 등록한 상품」을 보여줄 이유가 없다)
    """
    options: list[RegistrationOption] = [
        RegistrationOption(
            method=RegistrationMethod.REPORT_UPLOAD,
            label="보장분석 리포트 올리기",
            hint="계약이 한 번에 등록됩니다",
        )
    ]

    if mentioned_product:
        options.append(
            RegistrationOption(
                method=RegistrationMethod.FROM_CHAT,
                label=f"「{mentioned_product}」 등록",
                hint="대화에서 말한 상품",
                expected_entries=1,
            )
        )

    if recent_count:
        options.append(
            RegistrationOption(
                method=RegistrationMethod.RECENT_REUSE,
                label="최근 등록한 상품에서 고르기",
                hint=f"{recent_count}개",
            )
        )

    options.append(
        RegistrationOption(
            method=RegistrationMethod.SEARCH,
            label="보험사 · 상품명으로 찾기",
            hint="직접 검색",
            expected_entries=1,
        )
    )

    options.sort(key=lambda o: _SPEED_RANK[o.method])
    return options


@dataclass(frozen=True)
class ParsedContract:
    """리포트에서 읽어낸 계약 한 건. 보장맵에 넣기 전 확인 단계에서 쓴다."""

    insurer: str
    product_name: str
    contract_year: int | None = None
    contract_month: int | None = None
    selected: bool = True
    """FA가 체크를 풀면 등록하지 않는다. **자동으로 다 넣지 않는다.**"""

    terms_registered: bool = False
    """약관이 벤더에 등록돼 있는지. False면 확보 요청 대상이다."""

    @property
    def period_label(self) -> str:
        if self.contract_year and self.contract_month:
            return f"{self.contract_year}.{self.contract_month:02d} 가입"
        if self.contract_year:
            return f"{self.contract_year} 가입"
        return "가입 시점 미상"


@dataclass(frozen=True)
class ImportPreview:
    """리포트를 읽은 결과. **바로 저장하지 않고 먼저 보여준다.**

    파일에서 읽은 것을 확인 없이 넣으면 잘못 읽힌 계약이 그대로 보장맵에 남는다.
    FA가 훑어보고 체크를 조정한 뒤 저장한다.
    """

    contracts: tuple[ParsedContract, ...] = ()
    source_label: str = ""

    @property
    def selected(self) -> tuple[ParsedContract, ...]:
        return tuple(c for c in self.contracts if c.selected)

    @property
    def ready(self) -> tuple[ParsedContract, ...]:
        """약관까지 등록돼 있어 바로 쓸 수 있는 계약."""
        return tuple(c for c in self.selected if c.terms_registered)

    @property
    def needs_terms(self) -> tuple[ParsedContract, ...]:
        """계약은 확인됐지만 약관이 없는 것. 확보 요청으로 이어진다.

        **여기를 숨기면 보장맵이 채워진 것처럼 보이는데 답은 못 한다.**
        """
        return tuple(c for c in self.selected if not c.terms_registered)

    def summary(self) -> str:
        total = len(self.selected)
        if not total:
            return "등록할 계약을 선택해 주세요."
        parts = [f"계약 {total}건"]
        if self.needs_terms:
            parts.append(f"약관 확보 필요 {len(self.needs_terms)}건")
        return " · ".join(parts)
