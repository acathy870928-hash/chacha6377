"""연금 챗봇 계산 엔진.

챗봇이 도구(tool)로 호출하는 계산 함수 모음.
모든 함수는 계산값과 함께 `assumptions`(가정 조건)와 `disclosure`(필수 고지)를
반환한다. 챗봇은 이 필드를 반드시 답변에 포함해야 한다.

⚠️ 이 모듈은 어떤 값도 "보장"하지 않는다. 모든 결과는 가정 기반 추정치다.

실행:
    python3 pension_calc.py          # 데모 출력
    python3 test_pension_calc.py     # 테스트
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal
import math

# ============================================================
# 상수 — statistics.yaml / tax-rules.yaml 과 동기화할 것
# ============================================================

# 노후 생활비 (국민연금연구원 국민노후보장패널조사, 2024년 기준)
LIVING_COST = {
    "single_minimum": 1_392_000,
    "single_adequate": 1_976_000,
    "couple_minimum": 2_166_000,
    "couple_adequate": 2_981_000,
}
LIVING_COST_CITATION = "(국민연금연구원 국민노후보장패널조사, 2024년 기준)"

# 국민연금 노령연금 월평균 수령액 (국민연금공단 공표통계)
NPS_AVG_BY_YEARS = {
    "under_10": 0,            # 10년 미만은 반환일시금 대상
    "10_to_19": 442_177,
    "20_or_more": 1_120_539,
}
NPS_CITATION = "(국민연금공단 공표통계)"

# 국민연금 명목소득대체율 (2026년 개혁 반영, 40년 가입 기준)
NPS_REPLACEMENT_RATE = 0.43
NPS_FULL_CONTRIBUTION_YEARS = 40

# 수급 개시 연령 (출생연도 → 연령)
def nps_start_age(birth_year: int) -> int:
    """국민연금 수급 개시 연령을 출생연도로 판정한다."""
    if birth_year <= 1956:
        return 61
    if birth_year <= 1960:
        return 62
    if birth_year <= 1964:
        return 63
    if birth_year <= 1968:
        return 64
    return 65


# 주된 일자리 퇴직 평균 연령 (통계청 경제활동인구조사 고령층 부가조사)
RETIREMENT_AGE_TYPICAL = 49.4      # 55~64세 기준, 2024년
RETIREMENT_AGE_CONSERVATIVE = 53.0  # 고령층 전체 기준, 2026년 5월
RETIREMENT_AGE_CITATION = "(통계청 「경제활동인구조사 고령층 부가조사」)"

# 세액공제 (2026년 과세연도)
TAX_CREDIT_LIMIT_PENSION_SAVING = 6_000_000   # 연금저축 단독
TAX_CREDIT_LIMIT_COMBINED = 9_000_000         # 연금저축 + IRP 합산
TAX_CREDIT_RATE_LOW_INCOME = 0.165            # 총급여 5,500만 원 이하
TAX_CREDIT_RATE_HIGH_INCOME = 0.132           # 총급여 5,500만 원 초과
TAX_CREDIT_INCOME_THRESHOLD = 55_000_000

# 연금소득세율 (연령별)
PENSION_INCOME_TAX_RATES = [
    (55, 69, 0.055),
    (70, 79, 0.044),
    (80, 999, 0.033),
]

# 중도 해지 시 기타소득세
EARLY_WITHDRAWAL_TAX_RATE = 0.165

# 시뮬레이션 가정 이율 — 상한 4% (forbidden-expressions.json FB-014)
DEFAULT_RATE = 0.03
MAX_ALLOWED_RATE = 0.04

# 퇴직급여 연금화 기본 분할 기간
DEFAULT_ANNUITIZATION_YEARS = 20


class SimulationRateError(ValueError):
    """가정 이율이 허용 상한을 초과했을 때 발생."""


# ============================================================
# 결과 컨테이너
# ============================================================

@dataclass
class CalcResult:
    """모든 계산 함수의 공통 반환 타입.

    Attributes:
        value: 계산 결과 (dict)
        assumptions: 사용한 가정 조건. 답변에 반드시 노출한다.
        disclosures: 필수 고지 문구 ID 목록.
        citations: 인용한 통계의 출처 문구.
    """

    value: dict
    assumptions: list[str] = field(default_factory=list)
    disclosures: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# 1. 국민연금 예상 수령액 추정
# ============================================================

def estimate_national_pension(
    age: int,
    monthly_income: int,
    contribution_years: int | None = None,
    birth_year: int | None = None,
) -> CalcResult:
    """국민연금 예상 월 수령액을 추정한다.

    두 가지 방식을 모두 계산해 보수적인 쪽(낮은 값)을 대표값으로 제시한다.
      - 소득대체율 방식: 소득 × 43% × (가입기간 / 40년)
      - 통계 평균 방식: 가입기간 구간별 실제 평균 수령액

    Args:
        age: 현재 만 나이.
        monthly_income: 월 소득 (원).
        contribution_years: 예상 총 가입기간(년). None이면 60세까지 계속
            납부한다고 가정하고, 만 27세부터 가입한 것으로 본다.
        birth_year: 출생연도. None이면 age로 역산한다.

    Returns:
        CalcResult — 예상 월 수령액, 수급 개시 연령, 두 방식의 계산값.

    Raises:
        ValueError: 나이 또는 소득이 유효 범위를 벗어난 경우.
    """
    if not 18 <= age <= 100:
        raise ValueError(f"age must be 18~100, got {age}")
    if monthly_income < 0:
        raise ValueError(f"monthly_income must be >= 0, got {monthly_income}")

    if birth_year is None:
        birth_year = 2026 - age
    start_age = nps_start_age(birth_year)

    if contribution_years is None:
        # 만 27세 가입 → 60세 납부 종료 가정
        assumed_start = 27
        contribution_years = max(0, min(60, max(age, 60)) - assumed_start)

    # 방식 1 — 소득대체율
    rate_based = (
        monthly_income
        * NPS_REPLACEMENT_RATE
        * min(contribution_years / NPS_FULL_CONTRIBUTION_YEARS, 1.0)
    )

    # 방식 2 — 통계 평균
    if contribution_years >= 20:
        stat_based = NPS_AVG_BY_YEARS["20_or_more"]
    elif contribution_years >= 10:
        stat_based = NPS_AVG_BY_YEARS["10_to_19"]
    else:
        stat_based = NPS_AVG_BY_YEARS["under_10"]

    estimated = min(rate_based, stat_based) if stat_based else rate_based

    return CalcResult(
        value={
            "estimated_monthly": round(estimated, -3),
            "start_age": start_age,
            "contribution_years": contribution_years,
            "method_rate_based": round(rate_based, -3),
            "method_statistic_based": stat_based,
            "years_until_start": max(0, start_age - age),
        },
        assumptions=[
            f"가입기간 {contribution_years}년 가정",
            f"명목소득대체율 {NPS_REPLACEMENT_RATE:.0%} 적용 (40년 가입 기준)",
            "두 방식 중 보수적인 값을 대표값으로 제시",
        ],
        disclosures=["DISC-015"],  # 추정치 고지
        citations=[NPS_CITATION, "(보건복지부, 2025년 연금개혁법 기준)"],
    )


# ============================================================
# 2. 노후 소득 공백 계산
# ============================================================

def calc_income_gap(
    national_pension: int,
    retirement_pension: int = 0,
    private_pension: int = 0,
    household: Literal["single", "couple"] = "couple",
    target_level: Literal["minimum", "adequate"] = "adequate",
    custom_target: int | None = None,
) -> CalcResult:
    """은퇴 후 예상 소득과 목표 생활비의 차액을 계산한다.

    Args:
        national_pension: 예상 국민연금 월 수령액.
        retirement_pension: 예상 퇴직연금 월 수령액.
        private_pension: 예상 개인연금 월 수령액.
        household: "single" 또는 "couple".
        target_level: "minimum"(최소) 또는 "adequate"(적정).
        custom_target: 고객이 직접 지정한 목표 생활비. 있으면 우선 적용.

    Returns:
        CalcResult — 총 예상 소득, 목표 생활비, 월 부족액, 소득 충족률.
    """
    total_income = national_pension + retirement_pension + private_pension

    if custom_target is not None:
        target = custom_target
        target_label = "고객 지정"
    else:
        key = f"{household}_{target_level}"
        target = LIVING_COST[key]
        target_label = f"{'부부' if household == 'couple' else '개인'} {'적정' if target_level == 'adequate' else '최소'}"

    gap = max(0, target - total_income)
    coverage = (total_income / target * 100) if target else 0

    return CalcResult(
        value={
            "total_income": total_income,
            "target_cost": target,
            "target_label": target_label,
            "monthly_gap": gap,
            "coverage_rate": round(coverage, 1),
            "breakdown": {
                "국민연금": national_pension,
                "퇴직연금": retirement_pension,
                "개인연금": private_pension,
            },
        },
        assumptions=[
            f"목표 생활비: {target_label} 기준 월 {target:,}원",
            "물가상승률 미반영 (명목 기준)",
        ],
        disclosures=[],
        citations=[LIVING_COST_CITATION] if custom_target is None else [],
    )


# ============================================================
# 3. 연금 크레바스 (소득 공백기) 계산
# ============================================================

def calc_pension_crevasse(
    current_age: int,
    birth_year: int | None = None,
    retirement_age: float | None = None,
    monthly_need: int | None = None,
    conservative: bool = False,
) -> CalcResult:
    """퇴직 시점과 국민연금 수급 개시 사이의 소득 공백기를 계산한다.

    Args:
        current_age: 현재 만 나이.
        birth_year: 출생연도. None이면 current_age로 역산.
        retirement_age: 예상 퇴직 연령. None이면 통계 평균값 사용.
        monthly_need: 공백기 월 필요 생활비. None이면 부부 최소생활비 사용.
        conservative: True면 보수적(늦은) 퇴직 연령 통계를 사용.

    Returns:
        CalcResult — 공백 기간(년), 총 필요 자금, 퇴직/수급 연령.
    """
    if birth_year is None:
        birth_year = 2026 - current_age
    start_age = nps_start_age(birth_year)

    if retirement_age is None:
        retirement_age = (
            RETIREMENT_AGE_CONSERVATIVE if conservative else RETIREMENT_AGE_TYPICAL
        )
    if monthly_need is None:
        monthly_need = LIVING_COST["couple_minimum"]

    gap_years = max(0.0, start_age - retirement_age)
    total_needed = int(gap_years * 12 * monthly_need)

    return CalcResult(
        value={
            "retirement_age": retirement_age,
            "pension_start_age": start_age,
            "gap_years": round(gap_years, 1),
            "gap_months": round(gap_years * 12),
            "monthly_need": monthly_need,
            "total_needed": total_needed,
            "years_until_retirement": max(0, round(retirement_age - current_age, 1)),
        },
        assumptions=[
            f"퇴직 연령 {retirement_age}세 가정 (통계 평균)",
            f"공백기 생활비 월 {monthly_need:,}원 가정",
            "물가상승률 미반영",
        ],
        disclosures=[],
        citations=[RETIREMENT_AGE_CITATION, LIVING_COST_CITATION],
    )


# ============================================================
# 4. 적립액 시뮬레이션
# ============================================================

def simulate_accumulation(
    monthly_premium: int,
    years: int,
    annual_rate: float = DEFAULT_RATE,
) -> CalcResult:
    """월 납입액을 복리로 적립했을 때의 예상 적립액을 계산한다.

    기말 납입 기준 연금 미래가치 공식을 사용한다:
        FV = P × [((1 + r)^n - 1) / r]
    여기서 r은 월 이율, n은 총 납입 개월 수.

    Args:
        monthly_premium: 월 납입액 (원).
        years: 납입 기간 (년).
        annual_rate: 연 이율. 기본 3%, 상한 4%.

    Returns:
        CalcResult — 총 납입 원금, 예상 적립액, 운용 수익.

    Raises:
        SimulationRateError: annual_rate가 상한을 초과한 경우.
        ValueError: 납입액 또는 기간이 유효하지 않은 경우.
    """
    if annual_rate > MAX_ALLOWED_RATE:
        raise SimulationRateError(
            f"가정 이율 {annual_rate:.1%}는 허용 상한 {MAX_ALLOWED_RATE:.1%}를 초과합니다. "
            "과도한 수익률 가정은 사실상 수익 보장 광고로 읽힙니다 (FB-014)."
        )
    if monthly_premium <= 0:
        raise ValueError(f"monthly_premium must be > 0, got {monthly_premium}")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")

    months = years * 12
    principal = monthly_premium * months

    if annual_rate == 0:
        future_value = principal
    else:
        r = annual_rate / 12
        future_value = monthly_premium * ((1 + r) ** months - 1) / r

    return CalcResult(
        value={
            "monthly_premium": monthly_premium,
            "years": years,
            "annual_rate": annual_rate,
            "principal": principal,
            "future_value": int(round(future_value, -3)),
            "investment_return": int(round(future_value - principal, -3)),
        },
        assumptions=[
            f"연 {annual_rate:.1%} 복리 가정",
            "사업비 차감 미반영 (실제 적립액은 이보다 적음)",
            "세전 기준",
        ],
        disclosures=["DISC-006", "DISC-004"],  # 가정 명시 + 사업비 차감
        citations=[],
    )


def compare_start_timing(
    monthly_premium: int,
    current_age: int,
    target_age: int = 65,
    delay_years: list[int] | None = None,
    annual_rate: float = DEFAULT_RATE,
) -> CalcResult:
    """시작 시점을 늦출 때의 적립액 차이를 비교한다.

    "나중에 할게요" 반론 처리에 사용한다. 같은 금액을 넣어도
    늦게 시작하면 결과가 얼마나 줄어드는지를 보여준다.

    Args:
        monthly_premium: 월 납입액.
        current_age: 현재 나이.
        target_age: 목표 수령 나이.
        delay_years: 비교할 지연 연수 목록. 기본 [0, 5, 10].
        annual_rate: 연 이율.

    Returns:
        CalcResult — 시작 시점별 적립액과, 지연분을 만회하는 데 필요한 납입액.
    """
    if delay_years is None:
        delay_years = [0, 5, 10]

    baseline = None
    rows = []
    for delay in delay_years:
        start = current_age + delay
        years = target_age - start
        if years <= 0:
            continue
        sim = simulate_accumulation(monthly_premium, years, annual_rate)
        fv = sim.value["future_value"]
        if baseline is None:
            baseline = fv

        # 지연분을 만회하려면 월 얼마를 넣어야 하는가
        required = (
            int(round(monthly_premium * baseline / fv, -3)) if fv else None
        )
        rows.append(
            {
                "delay_years": delay,
                "start_age": start,
                "payment_years": years,
                "future_value": fv,
                "loss_vs_now": baseline - fv,
                "required_premium_to_match": required,
            }
        )

    return CalcResult(
        value={"rows": rows, "baseline": baseline},
        assumptions=[
            f"연 {annual_rate:.1%} 복리 가정",
            f"만 {target_age}세 수령 개시 기준",
            "사업비 차감 미반영",
        ],
        disclosures=["DISC-006", "DISC-004"],
        citations=[],
    )


# ============================================================
# 5. 세액공제 계산
# ============================================================

def calc_tax_credit(
    annual_premium: int,
    annual_income: int,
    has_irp: bool = False,
    irp_premium: int = 0,
    income_type: Literal["salary", "comprehensive"] = "salary",
) -> CalcResult:
    """연금저축·IRP 세액공제 환급 예상액을 계산한다.

    Args:
        annual_premium: 연금저축 연간 납입액.
        annual_income: 총급여(근로소득자) 또는 종합소득금액.
        has_irp: IRP 동시 납입 여부.
        irp_premium: IRP 연간 납입액.
        income_type: "salary"(총급여) 또는 "comprehensive"(종합소득금액).

    Returns:
        CalcResult — 공제 대상 금액, 적용 공제율, 예상 환급액, 실질 부담액.
    """
    if annual_premium < 0 or irp_premium < 0:
        raise ValueError("premium must be >= 0")

    threshold = (
        TAX_CREDIT_INCOME_THRESHOLD if income_type == "salary" else 45_000_000
    )
    rate = (
        TAX_CREDIT_RATE_LOW_INCOME
        if annual_income <= threshold
        else TAX_CREDIT_RATE_HIGH_INCOME
    )

    # 연금저축은 600만 원까지, IRP 합산 900만 원까지
    eligible_saving = min(annual_premium, TAX_CREDIT_LIMIT_PENSION_SAVING)
    eligible_irp = 0
    if has_irp:
        room = TAX_CREDIT_LIMIT_COMBINED - eligible_saving
        eligible_irp = min(irp_premium, max(0, room))

    eligible_total = eligible_saving + eligible_irp
    refund = int(round(eligible_total * rate, -1))

    total_paid = annual_premium + (irp_premium if has_irp else 0)
    net_burden = total_paid - refund

    # 한도 초과분 안내
    excess = max(0, total_paid - eligible_total)

    return CalcResult(
        value={
            "annual_premium": annual_premium,
            "irp_premium": irp_premium if has_irp else 0,
            "total_paid": total_paid,
            "eligible_amount": eligible_total,
            "excess_amount": excess,
            "applied_rate": rate,
            "estimated_refund": refund,
            "net_burden_annual": net_burden,
            "net_burden_monthly": int(round(net_burden / 12, -1)),
            "remaining_limit": max(0, TAX_CREDIT_LIMIT_COMBINED - eligible_total),
        },
        assumptions=[
            f"총급여 {annual_income:,}원 기준 공제율 {rate:.1%} 적용",
            "결정세액이 충분하다고 가정",
        ],
        disclosures=["DISC-007", "DISC-008"],  # 중도해지 페널티 + 변동 가능성
        citations=["(2026년 과세연도 기준)"],
    )


# ============================================================
# 6. 연금 수령 시뮬레이션
# ============================================================

def simulate_annuity_payout(
    accumulated: int,
    start_age: int = 65,
    payout_years: int | None = None,
    gender: Literal["male", "female"] | None = None,
) -> CalcResult:
    """적립금을 연금으로 수령할 때의 월 수령액과 세후 금액을 계산한다.

    Args:
        accumulated: 적립금 총액.
        start_age: 수령 개시 연령.
        payout_years: 수령 기간. None이면 성별 기대여명 사용.
        gender: 기대여명 적용용 성별.

    Returns:
        CalcResult — 월 수령액(세전/세후), 적용 연금소득세율.
    """
    if payout_years is None:
        # 65세 기대여명 (통계청 2024년 생명표)
        life_expectancy = {"male": 19.5, "female": 23.7}
        payout_years = int(life_expectancy.get(gender or "female", 21.5))

    months = payout_years * 12
    gross_monthly = int(round(accumulated / months, -3)) if months else 0

    tax_rate = next(
        (r for lo, hi, r in PENSION_INCOME_TAX_RATES if lo <= start_age <= hi),
        0.055,
    )
    net_monthly = int(round(gross_monthly * (1 - tax_rate), -3))

    return CalcResult(
        value={
            "accumulated": accumulated,
            "start_age": start_age,
            "payout_years": payout_years,
            "gross_monthly": gross_monthly,
            "tax_rate": tax_rate,
            "net_monthly": net_monthly,
            "total_tax": int(round(gross_monthly * tax_rate * months, -3)),
        },
        assumptions=[
            f"{payout_years}년 균등 분할 수령 가정",
            "수령 기간 중 추가 운용수익 미반영 (보수적 계산)",
            f"연금소득세 {tax_rate:.1%} 적용",
        ],
        disclosures=["DISC-006"],
        citations=["(통계청 「2024년 생명표」)"],
    )


def calc_early_withdrawal_loss(
    accumulated: int,
    total_credited: int,
) -> CalcResult:
    """세제적격 상품 중도 해지 시의 세금 부담을 계산한다.

    ⭐ '단점 먼저' 원칙(P1) 구현. 세액공제를 안내할 때 함께 제시한다.

    Args:
        accumulated: 현재 적립금.
        total_credited: 세액공제를 받은 누적 납입액.

    Returns:
        CalcResult — 기타소득세 부과액, 실수령 예상액.
    """
    taxable = min(accumulated, total_credited) + max(0, accumulated - total_credited)
    tax = int(round(taxable * EARLY_WITHDRAWAL_TAX_RATE, -1))

    return CalcResult(
        value={
            "accumulated": accumulated,
            "taxable_amount": taxable,
            "tax_rate": EARLY_WITHDRAWAL_TAX_RATE,
            "tax_amount": tax,
            "net_received": accumulated - tax,
        },
        assumptions=[
            "부득이한 사유에 해당하지 않는 일반 중도 해지 가정",
            "세액공제를 받은 납입액과 운용수익 전액이 과세 대상",
        ],
        disclosures=["DISC-005", "DISC-007"],
        citations=["(소득세법 기준)"],
    )


# ============================================================
# 데모
# ============================================================

def _demo() -> None:
    """페르소나 시나리오(38세 직장인)를 그대로 계산해 본다."""
    print("=" * 60)
    print("데모: 38세 / 월 실수령 350만 원 / 국민연금+퇴직연금 보유")
    print("=" * 60)

    np_result = estimate_national_pension(age=38, monthly_income=3_500_000)
    print("\n[1] 국민연금 예상")
    for k, v in np_result.value.items():
        print(f"    {k}: {v:,}" if isinstance(v, (int, float)) else f"    {k}: {v}")
    print(f"    가정: {np_result.assumptions}")

    gap = calc_income_gap(
        national_pension=np_result.value["estimated_monthly"],
        retirement_pension=400_000,
        household="couple",
        target_level="adequate",
    )
    print("\n[2] 소득 공백")
    print(f"    예상 총소득: {gap.value['total_income']:,}원")
    print(f"    목표 생활비: {gap.value['target_cost']:,}원 ({gap.value['target_label']})")
    print(f"    월 부족액:   {gap.value['monthly_gap']:,}원")
    print(f"    충족률:      {gap.value['coverage_rate']}%")

    crev = calc_pension_crevasse(current_age=38)
    print("\n[3] 연금 크레바스")
    print(f"    퇴직 {crev.value['retirement_age']}세 → 수급 {crev.value['pension_start_age']}세")
    print(f"    공백 기간:   {crev.value['gap_years']}년")
    print(f"    필요 자금:   {crev.value['total_needed']:,}원")

    timing = compare_start_timing(monthly_premium=200_000, current_age=38)
    print("\n[4] 시작 시점 비교 (월 20만 원)")
    for row in timing.value["rows"]:
        print(
            f"    {row['start_age']}세 시작 ({row['payment_years']}년 납입): "
            f"{row['future_value']:,}원 "
            f"| 지금 대비 -{row['loss_vs_now']:,}원 "
            f"| 만회하려면 월 {row['required_premium_to_match']:,}원"
        )

    credit = calc_tax_credit(annual_premium=2_400_000, annual_income=48_000_000)
    print("\n[5] 세액공제 (연 240만 원 납입, 총급여 4,800만 원)")
    print(f"    적용 공제율:   {credit.value['applied_rate']:.1%}")
    print(f"    예상 환급액:   {credit.value['estimated_refund']:,}원")
    print(f"    실질 월 부담:  {credit.value['net_burden_monthly']:,}원")
    print(f"    남은 공제한도: {credit.value['remaining_limit']:,}원")

    loss = calc_early_withdrawal_loss(accumulated=10_000_000, total_credited=9_600_000)
    print("\n[6] ⚠️ 중도 해지 시 (적립 1,000만 원 시점)")
    print(f"    기타소득세:   {loss.value['tax_amount']:,}원")
    print(f"    실수령액:     {loss.value['net_received']:,}원")

    print("\n" + "=" * 60)
    print("⚠️ 모든 수치는 가정 기반 추정치이며 실제 수익률을 보장하지 않습니다.")
    print("=" * 60)


if __name__ == "__main__":
    _demo()
