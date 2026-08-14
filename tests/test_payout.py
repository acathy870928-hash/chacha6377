"""지급 판정 — 면책이 먼저다.

조항만 보면 보상 가능해 보여도 면책에 걸리면 지급되지 않는다.
판정 순서가 뒤집히면 FA가 「나온다」고 읽고 멈춘다.
"""

from orca.coverage import BenefitMatch, EnrolledBenefit, EnrolledContract
from orca.payout import (
    ClaimVerdict,
    ClauseFinding,
    ClauseKind,
    PayoutEstimate,
    estimate_from_matches,
    judge,
    summarize,
)
from orca.versioning import ApproxDate

REASON = ClauseFinding(
    kind=ClauseKind.PAYOUT_REASON,
    text="피보험자가 보험기간 중 상해의 직접결과로써 골절로 진단확정된 경우",
    location="제3조 1항",
)
EXCLUSION = ClauseFinding(
    kind=ClauseKind.EXCLUSION,
    text="피보험자가 음주운전을 하는 동안 발생한 손해",
    location="제5조 1항 6호",
)
REDUCTION = ClauseFinding(
    kind=ClauseKind.REDUCTION,
    text="보장개시일부터 1년 이내 발생 시 50% 감액",
    location="제4조 2항",
)
LIMIT = ClauseFinding(kind=ClauseKind.LIMIT, text="연간 1회한", location="제6조")


class TestExclusionFirst:
    def test_면책이_있으면_지급사유가_있어도_면책이다(self):
        # 이 규칙이 뒤집히면 미지급 건을 「나온다」고 답하게 된다.
        estimate = judge(
            benefit_name="골절진단비", findings=(REASON, EXCLUSION), enrolled_amount=30
        )
        assert estimate.verdict is ClaimVerdict.EXCLUDED

    def test_면책이면_금액을_말하지_않는다(self):
        estimate = judge(
            benefit_name="골절진단비", findings=(REASON, EXCLUSION), enrolled_amount=30
        )
        # 「0원」은 계산 결과처럼 보인다. 지급 자체가 성립하지 않으므로 숫자를 두지 않는다.
        assert estimate.payable_amount is None
        assert not estimate.has_amount

    def test_면책이면_첫_문장이_면책이다(self):
        estimate = judge(benefit_name="골절진단비", findings=(REASON, EXCLUSION))
        assert "지급되지 않습니다" in estimate.headline

    def test_사실관계에_달리면_단정하지_않는다(self):
        # 음주 여부·고의 여부처럼 확인이 필요한 경우.
        estimate = judge(
            benefit_name="골절진단비",
            findings=(REASON, EXCLUSION),
            fact_dependent=True,
        )
        assert estimate.verdict is ClaimVerdict.NEEDS_REVIEW
        assert estimate.payable_amount is None


class TestPayable:
    def test_면책이_없고_지급사유가_있으면_지급이다(self):
        estimate = judge(benefit_name="골절진단비", findings=(REASON,), enrolled_amount=30)
        assert estimate.verdict is ClaimVerdict.PAYABLE
        assert estimate.payable_amount == 30

    def test_가입금액이_없으면_금액을_말하지_않는다(self):
        # 보장분석이 없는 상태. 약관만으로는 금액을 알 수 없다.
        estimate = judge(benefit_name="골절진단비", findings=(REASON,))
        assert estimate.verdict is ClaimVerdict.PAYABLE
        assert estimate.payable_amount is None

    def test_근거가_없으면_모른다고_한다(self):
        estimate = judge(benefit_name="골절진단비", findings=(), enrolled_amount=30)
        assert estimate.verdict is ClaimVerdict.UNKNOWN
        assert estimate.payable_amount is None


class TestConditions:
    def test_감액_조건이_있으면_확정_금액을_말하지_않는다(self):
        estimate = judge(
            benefit_name="골절진단비", findings=(REASON, REDUCTION), enrolled_amount=30
        )
        assert estimate.verdict is ClaimVerdict.REDUCED
        assert estimate.payable_amount is None

    def test_한도_조건도_같이_잡는다(self):
        estimate = judge(benefit_name="골절진단비", findings=(REASON, LIMIT), enrolled_amount=30)
        assert estimate.verdict is ClaimVerdict.REDUCED
        assert estimate.conditions == (LIMIT,)


class TestNotEnrolled:
    def test_미가입이면_약관을_보지_않는다(self):
        estimate = judge(benefit_name="치아보철치료", findings=(REASON,), is_enrolled=False)
        assert estimate.verdict is ClaimVerdict.NOT_ENROLLED
        assert estimate.payable_amount is None


class TestSummary:
    def _e(self, name, verdict, amount=None):
        return PayoutEstimate(benefit_name=name, verdict=verdict, enrolled_amount=amount)

    def test_확정_건만_합산한다(self):
        summary = summarize(
            (
                self._e("골절진단비", ClaimVerdict.PAYABLE, 30),
                self._e("5대골절진단비", ClaimVerdict.PAYABLE, 20),
                self._e("골절수술비", ClaimVerdict.REDUCED, 10),
            )
        )
        assert summary.total == 50
        assert summary.has_pending

    def test_막힌_건도_함께_보여준다(self):
        # 숨기면 FA는 전부 확인된 줄 안다.
        summary = summarize(
            (
                self._e("골절진단비", ClaimVerdict.PAYABLE, 30),
                self._e("교통상해입원일당", ClaimVerdict.EXCLUDED),
                self._e("치아보철치료", ClaimVerdict.NOT_ENROLLED),
            )
        )
        assert len(summary.blocked) == 2

    def test_확정_건이_없으면_합계가_없다(self):
        summary = summarize((self._e("골절진단비", ClaimVerdict.EXCLUDED),))
        assert summary.total is None

    def test_여러_건이면_중복지급_제한을_경고한다(self):
        summary = summarize(
            (
                self._e("골절진단비", ClaimVerdict.PAYABLE, 30),
                self._e("골절진단비", ClaimVerdict.PAYABLE, 10),
            )
        )
        assert "중복지급 제한" in summary.note()

    def test_보류_건이_있으면_합계가_최종이_아님을_밝힌다(self):
        summary = summarize(
            (
                self._e("골절진단비", ClaimVerdict.PAYABLE, 30),
                self._e("골절수술비", ClaimVerdict.REDUCED, 10),
            )
        )
        assert "합계에 넣지 않았습니다" in summary.note()

    def test_심사_확정_문구는_항상_붙는다(self):
        assert "보상 심사" in summarize(()).note()


class TestFromMatches:
    def test_보장분석_매칭에서_판정한다(self):
        contract = EnrolledContract(
            insurer="KB손보",
            product_name="KB다이렉트플러스운전자보험",
            contract_start=ApproxDate(2024, 11),
            benefits=(EnrolledBenefit("골절진단비(치아파절포함)(연간1회한)", 10),),
        )
        matches = (BenefitMatch(contract=contract, benefit=contract.benefits[0]),)

        summary = estimate_from_matches(
            matches, {"골절진단비(치아파절포함)(연간1회한)": (REASON,)}
        )
        assert summary.total == 10
        assert summary.estimates[0].insurer == "KB손보"

    def test_면책이_섞이면_그_건만_빠진다(self):
        contract = EnrolledContract(
            insurer="DB손보",
            product_name="브라보라이프보험0808",
            benefits=(
                EnrolledBenefit("골절진단비(치아제외)", 30),
                EnrolledBenefit("상해입원일당(1일이상)", 2),
            ),
        )
        matches = tuple(BenefitMatch(contract=contract, benefit=b) for b in contract.benefits)

        summary = estimate_from_matches(
            matches,
            {
                "골절진단비(치아제외)": (REASON,),
                "상해입원일당(1일이상)": (REASON, EXCLUSION),
            },
        )
        assert summary.total == 30
        assert len(summary.blocked) == 1
