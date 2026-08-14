"""보장분석 — 고객이 실제로 가입한 계약과 담보.

마이데이터(한국신용정보원)로 조회한 보장분석 리포트가 시스템에 붙으면,
그동안 되묻거나 조건부로만 답하던 것들이 확정된다.

## 무엇이 풀리는가

**1. 되묻기가 대부분 사라진다.**
리포트에 계약별 **정확한 상품명**과 **계약년월**이 들어 있다.
상품을 물을 필요도, 가입 시점을 물을 필요도 없다. 약관 판이 바로 정해진다.
상품명 끝의 판 표기(「…운전자보험(무배당)**(24.10)**」)까지 실려 오는 경우도 있다.

**2. 「가입한 담보에 한함」 조건부가 사실 확인으로 바뀐다.**
약관에는 가입 가능한 담보가 전부 들어 있어 그것만으로는 지급 여부를 말할 수 없었다.
리포트에는 **이 계약이 실제 가입한 담보와 금액**이 있으므로,
「골절진단비 가입되어 있습니다 — KB운전자보험 10만원, 브라보라이프 30만원」처럼
확정해서 답할 수 있다.

**3. 계약 간 중복 청구를 잡아낼 수 있다.**
같은 사고에 여러 계약이 걸린다. 담보가 여러 계약에 흩어져 있으면
FA가 한 건만 청구하고 나머지를 놓치기 쉽다. 이걸 한눈에 보여주는 것이
FA에게 실제로 가장 쓸모 있는 기능이다.

## 한계 — 그대로 확정 근거는 아니다

리포트 자체가 명시한다.

  - 조회 범위가 제한된다. 손해보험은 2002년 12월, 생명보험은 2000년 4월 이후
    계약만 조회되며, **단독실손은 상세 정보가 제공되지 않는다.**
  - 「보험금 지급 근거 자료가 될 수 없으며 정확한 내용은 약관 및 보험증권을 확인」해야 한다.
  - 가입 1년 이내 감액 지급, 동일 사고 중복지급 제한 등은 약관을 봐야 한다.

따라서 보장분석은 **가입 담보의 강한 근거**이되 최종 확인은 증권·약관이다.
답변에서 「조회 기준일」과 이 한계를 함께 밝힌다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .versioning import ApproxDate

#: 리포트가 조회할 수 있는 최초 계약 시점. 이보다 이전 계약은 리포트에 없다.
COVERAGE_LOOKUP_START = {
    "손해보험": date(2002, 12, 1),
    "생명보험": date(2000, 4, 1),
    "공제": date(2009, 10, 1),
}

#: 담보명 비교 시 지워도 되는 부가 표기.
#: 「골절진단비(치아파절포함)(연간1회한)」과 「골절진단비」를 같은 담보로 보기 위한 것이지만,
#: 괄호 안 내용이 지급 조건을 가르는 경우가 있으므로(치아파절 포함/제외) 원문은 반드시 보존한다.
_BENEFIT_NOISE = re.compile(r"[\s()\[\]·・,]+")


def normalize_benefit_name(name: str) -> str:
    """담보명 비교용 정규화. 표시는 언제나 원문으로 한다."""
    return _BENEFIT_NOISE.sub("", name.strip())


@dataclass(frozen=True)
class EnrolledBenefit:
    """계약이 실제 가입한 담보 하나."""

    name: str
    """리포트에 실린 담보명 원문. 예) 「골절진단비(치아파절포함)(연간1회한)」

    괄호 안 표기가 지급 범위를 가르므로(치아파절 포함/제외) 절대 잘라 쓰지 않는다.
    """

    amount: int | None = None
    """가입금액(만원). 리포트가 금액을 주지 않는 담보도 있다."""

    def matches(self, keyword: str) -> bool:
        needle = normalize_benefit_name(keyword)
        return bool(needle) and needle in normalize_benefit_name(self.name)


@dataclass(frozen=True)
class EnrolledContract:
    """보유 계약 하나."""

    insurer: str
    product_name: str
    benefits: tuple[EnrolledBenefit, ...] = field(default_factory=tuple)

    contract_start: ApproxDate | None = None
    """계약년월. **약관 판을 특정하는 근거**이므로 되묻기를 대체한다."""

    maturity: ApproxDate | None = None
    premium: int | None = None
    contract_id: str = ""
    insured: str = ""
    """피보험자. 계약자와 다를 수 있다(부모가 계약자인 경우 등)."""

    policyholder: str = ""
    """계약자."""

    terms_url: str = ""
    """이 계약의 약관 링크. **현재 연동 업체는 제공하지 않는다.**

    보장분석 업체는 계약과 담보만 발행하고 약관은 주지 않는다.
    약관은 VELUGA 벤더에 별도로 등록해야 한다.
    다른 경로로 링크를 확보하게 될 경우를 위해 자리만 남겨 둔다.
    """

    @property
    def has_terms_link(self) -> bool:
        return bool(self.terms_url)

    def find(self, keyword: str) -> tuple[EnrolledBenefit, ...]:
        return tuple(b for b in self.benefits if b.matches(keyword))


def terms_key(contract: EnrolledContract) -> str:
    """등록 대상 약관을 식별하는 키.

    같은 상품이라도 계약년월이 다르면 적용 판이 다를 수 있으므로 연도까지 넣는다.
    """
    from .catalog import normalize_product_name

    year = contract.contract_start.year if contract.contract_start else None
    return f"{contract.insurer}:{normalize_product_name(contract.product_name)}:{year}"


@dataclass(frozen=True)
class TermsNeed:
    """보유 계약에서 도출된 약관 등록 수요 한 건."""

    key: str
    insurer: str
    product_name: str
    contract_year: int | None
    contract_count: int
    """이 약관이 필요한 보유 계약 수. 곧 등록 우선순위다."""

    terms_url: str = ""
    """약관 링크. 현재 연동 업체는 주지 않으므로 대개 비어 있다."""


def aggregate_terms_needs(profiles: list[CoverageProfile]) -> list[TermsNeed]:
    """여러 고객의 보장분석에서 **사야 할 약관 목록**을 뽑는다.

    보장분석 업체는 약관을 주지 않으므로 약관은 벤더에서 유료로 등록해야 한다.
    잘못 사면 그대로 손실이므로, 무엇을 살지가 정확해야 한다.

    리포트의 계약 한 줄이 살 약관 하나를 지목한다.
    (보험사 + 상품 + 계약년월 → 적용 판)
    실적 상위 상품을 추정해 사는 것과 달리, 여기 있는 약관은
    보유 계약이 존재하므로 **언젠가 반드시 조회된다.**
    보유 계약 수가 많은 순이 곧 등록 우선순위다.
    """
    grouped: dict[str, list[EnrolledContract]] = {}
    for profile in profiles:
        for contract in profile.contracts:
            grouped.setdefault(terms_key(contract), []).append(contract)

    needs = [
        TermsNeed(
            key=key,
            insurer=contracts[0].insurer,
            product_name=contracts[0].product_name,
            contract_year=(
                contracts[0].contract_start.year if contracts[0].contract_start else None
            ),
            contract_count=len(contracts),
            terms_url=next((c.terms_url for c in contracts if c.terms_url), ""),
        )
        for key, contracts in grouped.items()
    ]
    needs.sort(key=lambda n: (-n.contract_count, n.insurer, n.product_name))
    return needs


@dataclass(frozen=True)
class BenefitMatch:
    """어느 계약의 어느 담보가 걸렸는지."""

    contract: EnrolledContract
    benefit: EnrolledBenefit


@dataclass(frozen=True)
class CoverageProfile:
    """한 고객의 보장분석 결과."""

    contracts: tuple[EnrolledContract, ...] = field(default_factory=tuple)
    as_of: date | None = None
    """조회 기준일. 답변에 함께 밝힌다. 이후 가입·해지분은 반영되지 않는다."""

    customer_id: str = ""
    customer_name: str = ""
    """리포트의 대상 고객. 대화 컨텍스트와 확보 요청이 이 값으로 고객에 귀속된다."""

    def find_benefits(self, keyword: str) -> tuple[BenefitMatch, ...]:
        """담보명으로 가입 내역을 찾는다.

        **여러 계약에 걸쳐 찾는다.** 같은 담보가 여러 계약에 있으면 각각 청구 대상이므로
        하나만 돌려주면 FA가 나머지를 놓친다.
        """
        matches: list[BenefitMatch] = []
        for contract in self.contracts:
            for benefit in contract.find(keyword):
                matches.append(BenefitMatch(contract=contract, benefit=benefit))
        return tuple(matches)

    def is_enrolled(self, keyword: str) -> bool:
        return bool(self.find_benefits(keyword))

    def contracts_with(self, keyword: str) -> tuple[EnrolledContract, ...]:
        """해당 담보를 가입한 계약들. 중복 없이 리포트 순서를 유지한다."""
        seen: list[EnrolledContract] = []
        for match in self.find_benefits(keyword):
            if match.contract not in seen:
                seen.append(match.contract)
        return tuple(seen)

    def find_contract(self, product_name: str) -> EnrolledContract | None:
        """상품명으로 계약을 찾는다. FA가 상품을 지목했을 때 쓴다."""
        from .catalog import normalize_product_name

        needle = normalize_product_name(product_name)
        if not needle:
            return None
        for contract in self.contracts:
            name = normalize_product_name(contract.product_name)
            if needle in name or name in needle:
                return contract
        return None

    def contracts_needing_terms(self, registered: set[str]) -> tuple[EnrolledContract, ...]:
        """보유 계약 중 약관이 아직 등록되지 않은 것.

        `registered`에는 이미 등록된 약관의 키(보험사:상품명)를 넣는다.
        """
        return tuple(c for c in self.contracts if terms_key(c) not in registered)

    def total_amount(self, keyword: str) -> int | None:
        """해당 담보의 계약 합산 가입금액(만원).

        중복지급 제한이 있는 담보도 있으므로 **합계를 지급액으로 단정하지 않는다.**
        어디에 얼마씩 있는지 보여주기 위한 값이다.
        """
        amounts = [m.benefit.amount for m in self.find_benefits(keyword) if m.benefit.amount]
        return sum(amounts) if amounts else None
