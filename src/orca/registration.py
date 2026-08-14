"""약관 등록 경로 — 쉬운 길을 먼저 보여준다.

보험사 → 상품 검색 → 등록은 한 건에 세 단계다.
고객 한 명이 계약을 대여섯 건 가지고 있으므로 **그대로 두면 열다섯 단계**가 되고,
FA는 한 번 해보고 다시 하지 않는다.

그래서 등록 경로를 셋으로 두고, **빠른 것부터 보여준다.**

    1. My Data 가져오기      계약 전부가 한 번에    ← 현 시점 미오픈
    2. 대화 중 바로 등록      말한 김에              ← 이미 상품을 말했다
    3. 보험사 → 상품 검색     확실하지만 느리다      ← 기본 경로

「최근 등록한 상품에서 고르기」는 두지 않는다. 그 목록은 결국 **다른 고객에게
등록했던 상품**이라, 지금 이 고객과 무관한 계약을 화면에 끌어오는 셈이 된다.
상품명을 아는 상태라면 검색이 더 빠르고 오해도 없다.

1번이 원래 결정적인 경로다. 마이데이터는 고객이 전송요구권을 행사해 여러 기관의
보험 가입내역을 한 번에 모으는 제도이므로, 계약별 보험사 · 상품명 · 계약년월이
구조화된 형태로 들어온다. 그 한 번으로 보장맵의 뼈대가 채워진다.

**다만 1차 오픈 범위가 아니다.** 개인인증 · 동의 범위 · 사업자 계약이 선행되어야
하므로 화면에는 두되 **「현 시점 오픈하지 않음」으로 표시하고 고를 수 없게** 한다.
숨기지 않는 이유는, 곧 열릴 경로가 있다는 사실 자체가 안내이고
FA가 「왜 하나씩 넣어야 하나」를 납득하는 근거가 되기 때문이다.

그 결과 **1차에는 대량 등록 경로가 없다.** 실질적으로 가장 빠른 길은 2번(대화에서
말한 상품)이며, 보장맵은 상담하면서 하나씩 쌓인다. 이 점을 감안해 등록 한 건의
단계 수를 최대한 줄여야 한다.

주의: 계약을 가져와도 **약관이 등록된 것은 아니다.** 계약을 알게 됐을 뿐이며,
약관 등록 여부는 별개로 확인해 미등록 건은 확보 요청으로 넘긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegistrationMethod(Enum):
    """약관(계약)을 보장맵에 넣는 방법."""

    MYDATA_IMPORT = "mydata_import"
    """My Data로 계약을 가져온다. 전부가 한 번에 들어온다. **1차 오픈 범위 밖.**"""

    FROM_CHAT = "from_chat"
    """대화에서 이미 말한 상품을 그대로 등록한다."""

    SEARCH = "search"
    """보험사 → 상품 검색. 확실하지만 느리다."""


#: 방법별 예상 소요. 화면에서 「빠른 순」으로 정렬하는 근거다.
_SPEED_RANK = {
    RegistrationMethod.MYDATA_IMPORT: 0,
    RegistrationMethod.FROM_CHAT: 1,
    RegistrationMethod.SEARCH: 2,
}


@dataclass(frozen=True)
class RegistrationOption:
    """등록 방법 하나. 화면의 버튼 한 개에 대응한다."""

    method: RegistrationMethod
    label: str
    hint: str = ""
    expected_entries: int | None = None
    """이 방법으로 한 번에 들어올 계약 수. 모르면 None."""

    available: bool = True
    """지금 쓸 수 있는가. False면 화면에 두되 고를 수 없게 한다."""

    note: str = ""
    """쓸 수 없는 이유. 「현 시점 오픈하지 않음」처럼 화면에 그대로 띄운다."""

    @property
    def is_bulk(self) -> bool:
        return (self.expected_entries or 0) > 1


def suggest_methods(
    *,
    mydata_open: bool = False,
    mentioned_product: str | None = None,
) -> list[RegistrationOption]:
    """지금 상황에서 쓸 수 있는 등록 방법을 빠른 순으로.

    **상황에 없는 방법은 빼고, 아직 안 열린 방법은 두되 잠근다.** 둘은 다르다 —
    최근 등록 이력이 없는 첫 FA에게 「최근 등록한 상품」을 보여줄 이유는 없지만,
    My Data는 곧 열릴 경로이므로 보여주는 것 자체가 안내가 된다.
    """
    options: list[RegistrationOption] = [
        RegistrationOption(
            method=RegistrationMethod.MYDATA_IMPORT,
            label="My Data 가져오기",
            hint=(
                "계약이 한 번에 등록됩니다"
                if mydata_open
                else "현 시점 오픈하지 않음"
            ),
            available=mydata_open,
            note="" if mydata_open else "개인인증 · 동의 범위 확인 후 열립니다",
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

    options.append(
        RegistrationOption(
            method=RegistrationMethod.SEARCH,
            label="보험사 · 상품명으로 찾기",
            hint="My Data가 열리기 전까지 기본 경로",
            expected_entries=1,
        )
    )

    options.sort(key=lambda o: _SPEED_RANK[o.method])
    return options


@dataclass(frozen=True)
class ParsedContract:
    """가져온 계약 한 건. 보장맵에 넣기 전 확인 단계에서 쓴다."""

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
    """가져온 계약 목록. **바로 저장하지 않고 먼저 보여준다.**

    확인 없이 넣으면 잘못 읽힌 계약이 그대로 보장맵에 남는다.
    FA가 훑어보고 체크를 조정한 뒤 저장한다.

    My Data가 열리기 전까지는 쓰이지 않지만, 화면과 규칙을 먼저 정해 둔다.
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
