"""지급 판정 — 면책이 먼저다.

약관에서 지급사유 조항만 보면 「보상된다」로 읽힌다. 그런데 면책 조항에 걸리면
지급되지 않는다. **따라서 판정 순서는 면책 → 지급사유이지 그 반대가 아니다.**

    잘못된 순서: 지급사유 확인 → 「지급 대상입니다」 → (면책은 참고로 덧붙임)
    올바른 순서: 면책 확인 → 걸리면 거기서 끝 → 안 걸릴 때만 지급사유를 본다

지급사유를 먼저 보여주면 FA가 그 줄에서 읽기를 멈춘다. 면책은 아래에 있어도 안 읽힌다.
그래서 답변 구성에서도 판정 결과가 맨 앞에 온다.

## 얼마 받는지 답하려면

「어디가 다쳤는데 얼마 받을 수 있어요」에 답하려면 네 가지가 모두 있어야 한다.

    1. 가입 담보와 가입금액   ← 보장분석 (초개인화 단계)
    2. 지급사유 해당 여부      ← 약관
    3. 면책 해당 여부          ← 약관 (가장 먼저 본다)
    4. 감액 · 한도 · 중복 제한  ← 약관

하나라도 없으면 금액을 말하지 않는다. 특히 1이 없으면 약관만으로는
「가입했다면 얼마」조차 말할 수 없다. 약관은 가입 가능한 담보의 목록일 뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .coverage import BenefitMatch


class ClauseKind(Enum):
    """조항 유형. 벤더 검색 결과를 이 유형으로 분류해 받는다."""

    EXCLUSION = "exclusion"
    """보험금을 지급하지 않는 사유. **가장 먼저 확인한다.**"""

    PAYOUT_REASON = "payout_reason"
    """보험금을 지급하는 사유."""

    REDUCTION = "reduction"
    """감액 지급. 가입 1년 이내 50% 감액 등."""

    WAITING = "waiting"
    """면책기간 · 대기기간."""

    LIMIT = "limit"
    """지급 한도 · 횟수 제한 · 중복지급 제한."""


@dataclass(frozen=True)
class ClauseFinding:
    """약관에서 찾은 조항 하나."""

    kind: ClauseKind
    text: str
    location: str = ""
    """조 · 항 · 호. 예) 「2판 제5조 1항 6호」"""

    edition_label: str = ""


class ClaimVerdict(Enum):
    """지급 판정. 우선순위가 곧 순서다."""

    EXCLUDED = "excluded"
    """면책에 해당한다. 지급사유가 있어도 지급되지 않는다."""

    NOT_ENROLLED = "not_enrolled"
    """담보에 가입하지 않았다. 약관 판정 이전 문제다."""

    REDUCED = "reduced"
    """지급되지만 감액 · 대기기간 등 조건이 붙는다."""

    PAYABLE = "payable"
    """지급사유에 해당하고 면책에 걸리지 않는다."""

    NEEDS_REVIEW = "needs_review"
    """면책 여부가 사실관계에 달려 있다. 단정할 수 없다."""

    UNKNOWN = "unknown"
    """약관 근거를 찾지 못했다. 추측하지 않는다."""


#: 판정별 답변 첫 문장. 결과를 맨 앞에 둔다.
VERDICT_HEADLINE = {
    ClaimVerdict.EXCLUDED: "면책 사유에 해당해 지급되지 않습니다.",
    ClaimVerdict.NOT_ENROLLED: "이 담보에 가입되어 있지 않습니다.",
    ClaimVerdict.REDUCED: "지급 대상이지만 감액 · 조건이 붙습니다.",
    ClaimVerdict.PAYABLE: "지급 대상입니다.",
    ClaimVerdict.NEEDS_REVIEW: "면책 여부가 사실관계에 따라 갈립니다. 확인이 필요합니다.",
    ClaimVerdict.UNKNOWN: "약관에서 근거를 찾지 못했습니다. 확인되지 않은 내용으로 답하지 않습니다.",
}


@dataclass(frozen=True)
class PayoutEstimate:
    """담보 하나에 대한 지급 판정과 예상 금액."""

    benefit_name: str
    insurer: str = ""
    product_name: str = ""
    edition_label: str = ""

    enrolled_amount: int | None = None
    """가입금액(만원). 보장분석이 없으면 None이고, 그러면 금액을 말하지 않는다."""

    verdict: ClaimVerdict = ClaimVerdict.UNKNOWN
    exclusions: tuple[ClauseFinding, ...] = field(default_factory=tuple)
    reasons: tuple[ClauseFinding, ...] = field(default_factory=tuple)
    conditions: tuple[ClauseFinding, ...] = field(default_factory=tuple)
    """감액 · 대기기간 · 한도. 지급되더라도 금액을 깎는 것들."""

    @property
    def headline(self) -> str:
        return VERDICT_HEADLINE[self.verdict]

    @property
    def payable_amount(self) -> int | None:
        """말해도 되는 금액(만원).

        면책 · 미가입이면 0이 아니라 **None**이다. 「0원」은 계산 결과처럼 보이지만
        실제로는 지급 자체가 성립하지 않는 것이므로 금액 자리에 숫자를 두지 않는다.
        감액 조건이 붙어 있으면 확정 금액을 말할 수 없으므로 역시 None이다.
        """
        if self.verdict is not ClaimVerdict.PAYABLE:
            return None
        return self.enrolled_amount

    @property
    def has_amount(self) -> bool:
        return self.payable_amount is not None


def judge(
    *,
    benefit_name: str,
    findings: tuple[ClauseFinding, ...],
    enrolled_amount: int | None = None,
    is_enrolled: bool = True,
    insurer: str = "",
    product_name: str = "",
    edition_label: str = "",
    fact_dependent: bool = False,
) -> PayoutEstimate:
    """조항들을 받아 지급 여부를 판정한다.

    **순서가 규칙이다.**
      1. 가입하지 않았으면 약관을 볼 필요가 없다.
      2. 면책이 있으면 거기서 끝난다. 지급사유가 있어도 뒤집지 못한다.
      3. 지급사유가 없으면 모른다고 한다. 없는 근거를 만들지 않는다.
      4. 감액 · 대기기간 · 한도가 있으면 확정 금액을 말하지 않는다.

    `fact_dependent`는 면책 해당 여부가 사실관계에 달린 경우다.
    (음주 여부, 고의 여부 등) 이때는 단정하지 않는다.
    """
    exclusions = tuple(f for f in findings if f.kind is ClauseKind.EXCLUSION)
    reasons = tuple(f for f in findings if f.kind is ClauseKind.PAYOUT_REASON)
    conditions = tuple(
        f for f in findings if f.kind in (ClauseKind.REDUCTION, ClauseKind.WAITING, ClauseKind.LIMIT)
    )

    common = {
        "benefit_name": benefit_name,
        "insurer": insurer,
        "product_name": product_name,
        "edition_label": edition_label,
        "enrolled_amount": enrolled_amount,
        "exclusions": exclusions,
        "reasons": reasons,
        "conditions": conditions,
    }

    if not is_enrolled:
        return PayoutEstimate(verdict=ClaimVerdict.NOT_ENROLLED, **common)

    if exclusions:
        # 면책이 먼저다. 지급사유가 함께 나왔더라도 뒤집지 못한다.
        verdict = ClaimVerdict.NEEDS_REVIEW if fact_dependent else ClaimVerdict.EXCLUDED
        return PayoutEstimate(verdict=verdict, **common)

    if not reasons:
        return PayoutEstimate(verdict=ClaimVerdict.UNKNOWN, **common)

    if conditions:
        return PayoutEstimate(verdict=ClaimVerdict.REDUCED, **common)

    return PayoutEstimate(verdict=ClaimVerdict.PAYABLE, **common)


@dataclass(frozen=True)
class PayoutSummary:
    """여러 계약을 합친 결과. 「얼마 받을 수 있어요」의 답이 되는 단위."""

    estimates: tuple[PayoutEstimate, ...] = field(default_factory=tuple)

    @property
    def payable(self) -> tuple[PayoutEstimate, ...]:
        return tuple(e for e in self.estimates if e.verdict is ClaimVerdict.PAYABLE)

    @property
    def blocked(self) -> tuple[PayoutEstimate, ...]:
        """면책 · 미가입으로 막힌 건. **숨기지 않고 함께 보여준다.**"""
        return tuple(
            e
            for e in self.estimates
            if e.verdict in (ClaimVerdict.EXCLUDED, ClaimVerdict.NOT_ENROLLED)
        )

    @property
    def needs_review(self) -> tuple[PayoutEstimate, ...]:
        return tuple(
            e
            for e in self.estimates
            if e.verdict in (ClaimVerdict.NEEDS_REVIEW, ClaimVerdict.REDUCED, ClaimVerdict.UNKNOWN)
        )

    @property
    def total(self) -> int | None:
        """확정 지급 건의 합계(만원).

        확정 건이 없으면 None이다. 감액 · 확인 필요 건은 합계에 넣지 않는다.
        """
        amounts = [e.payable_amount for e in self.payable if e.payable_amount is not None]
        return sum(amounts) if amounts else None

    @property
    def has_pending(self) -> bool:
        """합계 밖에 남은 건이 있는지. 있으면 합계를 최종 금액으로 말하면 안 된다."""
        return bool(self.needs_review)

    def note(self) -> str:
        """금액과 함께 반드시 붙는 문구."""
        parts = ["약관상 담보 기준이며 실제 지급은 보상 심사로 확정됩니다."]
        if len(self.payable) > 1:
            parts.append("동일 사고에 중복지급 제한이 적용될 수 있습니다.")
        if self.has_pending:
            parts.append("감액 · 확인이 필요한 건은 합계에 넣지 않았습니다.")
        return " ".join(parts)


def summarize(estimates: tuple[PayoutEstimate, ...]) -> PayoutSummary:
    return PayoutSummary(estimates=estimates)


def estimate_from_matches(
    matches: tuple[BenefitMatch, ...],
    findings_by_benefit: dict[str, tuple[ClauseFinding, ...]],
    *,
    fact_dependent: bool = False,
) -> PayoutSummary:
    """보장분석 매칭 결과와 약관 조항을 합쳐 판정한다.

    보장분석이 없으면 이 함수를 쓸 수 없다 — 그때는 금액 없이 약관 판정만 한다.
    """
    estimates = tuple(
        judge(
            benefit_name=match.benefit.name,
            findings=findings_by_benefit.get(match.benefit.name, ()),
            enrolled_amount=match.benefit.amount,
            insurer=match.contract.insurer,
            product_name=match.contract.product_name,
            fact_dependent=fact_dependent,
        )
        for match in matches
    )
    return PayoutSummary(estimates=estimates)
