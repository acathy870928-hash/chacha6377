"""벤더에 보낼 검색 질의 — 개인정보를 여기서 끊는다.

보장분석 데이터는 고객 본인인증(마이데이터 전송요구권)으로 조회한 **개인정보**다.
그런데 약관 검색은 외부 벤더 API에서 이뤄진다.
개인정보를 그대로 벤더에 보내면 제3자 제공 · 처리위탁 문제가 된다.

## 해결 — 보내는 것을 자른다

벤더가 약관을 찾는 데 필요한 것은 **누구의 계약인지가 아니라 어느 약관인지**다.

    필요한 것        상품명 · 약관 판 · 담보명 · 상황 설명
    필요 없는 것     이름 · 생년월일 · 계약번호 · 가입금액 · 보험료 · 계약자 · 피보험자

가입금액도 보낼 필요가 없다. 약관은 「지급사유에 해당하는가」만 답하고,
금액은 우리 쪽에서 답변을 조립할 때 붙이면 된다.

```
보장분석(개인정보)  ──  우리 서버에만 머문다
        │
        │  상품 · 판 · 담보명만 추출
        ▼
   TermsQuery  ──────  벤더 API (누구 것인지 모른다)
        │
        │  조항 원문 반환
        ▼
   답변 조립     ──────  우리 서버에서 가입금액 · 계약과 결합
```

이렇게 하면 벤더에 나가는 값은 **약관을 특정하는 정보뿐**이고,
그 자체로는 특정 개인을 알아볼 수 없다.

주의: 질문 원문을 그대로 벤더에 보내면 이 분리가 깨진다.
FA가 「김○○ 고객이…」처럼 입력할 수 있기 때문이다. `TermsQuery.situation`은
분류기가 정리한 상황 서술만 담고, 원문을 그대로 싣지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .coverage import BenefitMatch

#: 상황 서술에서 걸러낼 개인 식별 표현.
#: 완전한 비식별화 수단이 아니라, 실수로 섞여 들어가는 것을 막는 마지막 방어선이다.
_PII_PATTERNS = (
    re.compile(r"\d{6}\s*-\s*\d[\d*•\-_]{0,6}"),  # 주민등록번호(마스킹 형태 포함)
    re.compile(r"01[016789]-?\d{3,4}-?\d{4}"),  # 휴대전화
    re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일생"),  # 생년월일
    re.compile(r"[가-힣]{2,4}\s*(고객님|님|씨)"),  # 실명 호칭
)


def strip_pii(text: str) -> str:
    """상황 서술에서 개인 식별 표현을 지운다."""
    cleaned = text
    for pattern in _PII_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


@dataclass(frozen=True)
class TermsQuery:
    """벤더 약관 API에 보내는 질의.

    **개인 식별정보를 담지 않는다.** 필드를 추가할 때 이 원칙을 먼저 확인한다.
    """

    insurer: str
    product_name: str
    edition_label: str | None = None
    """약관 판. 계약년월에서 우리 쪽이 이미 계산해 넘긴다."""

    benefit_name: str | None = None
    """담보명. 보장분석에서 가져오되 계약 식별정보는 붙이지 않는다."""

    situation: str = ""
    """사고 · 상황 서술. 분류기가 정리한 문장만 싣는다(원문 그대로 보내지 않는다)."""

    def as_payload(self) -> dict[str, str]:
        payload = {
            "insurer": self.insurer,
            "product": self.product_name,
        }
        if self.edition_label:
            payload["edition"] = self.edition_label
        if self.benefit_name:
            payload["benefit"] = self.benefit_name
        if self.situation:
            payload["situation"] = strip_pii(self.situation)
        return payload


def build_queries(
    matches: tuple[BenefitMatch, ...],
    *,
    situation: str = "",
) -> tuple[TermsQuery, ...]:
    """보장분석 결과를 벤더 질의로 바꾼다.

    계약별로 적용 판이 다르므로 질의도 계약 수만큼 나간다.
    가입금액 · 계약자 · 피보험자 · 보험료는 **의도적으로 제외한다.**
    """
    seen: set[tuple[str, str, str | None, str | None]] = set()
    queries: list[TermsQuery] = []

    for match in matches:
        contract = match.contract
        edition = _edition_hint(contract)
        key = (contract.insurer, contract.product_name, edition, match.benefit.name)
        if key in seen:
            continue
        seen.add(key)
        queries.append(
            TermsQuery(
                insurer=contract.insurer,
                product_name=contract.product_name,
                edition_label=edition,
                benefit_name=match.benefit.name,
                situation=strip_pii(situation),
            )
        )
    return tuple(queries)


def _edition_hint(contract) -> str | None:
    """계약년월을 판 힌트로 바꾼다. 날짜 자체는 개인정보로 보지 않지만,
    벤더에는 판 식별에 필요한 최소 형태(연-월)로만 넘긴다."""
    start = contract.contract_start
    if start is None:
        return None
    if start.month:
        return f"{start.year}.{start.month:02d}"
    return str(start.year)
