"""연금 상품 관련 로직: 수령액 시뮬레이션, 적합성 진단, 청약 접수.

세법·세율 상수는 매년 바뀐다. 하드코딩된 값을 그대로 운영에 쓰지 말고
설정/DB 로 빼고 연 1회 이상 검증하라 (docs/crawl-targets.md 참고).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .knowledge import get_product

# --- 세법 상수 (2025년 기준 예시. 반드시 최신 세법으로 재확인할 것) ------------
TAX_CREDIT_LIMIT_MANWON = 600  # 연금저축 단독 세액공제 한도
TAX_CREDIT_LIMIT_WITH_IRP_MANWON = 900  # IRP 합산 한도
INCOME_THRESHOLD_MANWON = 5500  # 총급여 기준선
TAX_CREDIT_RATE_LOW_INCOME = 0.165  # 기준선 이하
TAX_CREDIT_RATE_HIGH_INCOME = 0.132  # 기준선 초과
EARLY_TERMINATION_TAX_RATE = 0.165  # 중도해지 시 기타소득세

# --- 시뮬레이션 가정 ---------------------------------------------------------
ASSUMED_CREDIT_RATE = 0.035  # 공시이율 가정 (확정 수익률 아님)
DEFAULT_START_AGE = 65  # 연금 개시 연령
DEFAULT_PAYOUT_YEARS = 20  # 확정 수령 기간
MIN_PAYMENT_YEARS = 5  # 최소 납입 기간
MIN_START_AGE = 55  # 연금저축 최소 수령 개시 연령

# --- 적합성 진단 기준 --------------------------------------------------------
MAX_PAYMENT_TO_INCOME_RATIO = 0.30  # 월소득 대비 납입액 상한
SUITABILITY_TTL_MINUTES = 30

_PENSION_CATEGORY = "연금"


def _is_pension(product: dict[str, Any]) -> bool:
    return product.get("premium_basis") == "payment"


def tax_credit_rate(annual_income_manwon: int) -> float:
    return (
        TAX_CREDIT_RATE_LOW_INCOME
        if annual_income_manwon <= INCOME_THRESHOLD_MANWON
        else TAX_CREDIT_RATE_HIGH_INCOME
    )


# ---------------------------------------------------------------------------
# 1. 연금 수령액 시뮬레이션
# ---------------------------------------------------------------------------


def simulate_pension(
    product_id: str,
    monthly_payment_manwon: int,
    current_age: int,
    start_age: int = DEFAULT_START_AGE,
    annual_income_manwon: int | None = None,
    payout_years: int = DEFAULT_PAYOUT_YEARS,
) -> dict[str, Any]:
    """납입 조건에 따른 예상 적립금·연금월액·세액공제액을 계산한다."""
    product = get_product(product_id)
    if product is None or not _is_pension(product):
        return {
            "error": "not_a_pension_product",
            "message": "연금 상품이 아닙니다. pension-001(연금저축보험) 또는 pension-002(일반연금보험)를 지정하세요.",
        }

    if monthly_payment_manwon <= 0:
        return {"error": "invalid_payment", "message": "월 납입액은 1만원 이상이어야 합니다."}

    payment_years = start_age - current_age
    if payment_years < MIN_PAYMENT_YEARS:
        return {
            "error": "payment_period_too_short",
            "message": (
                f"납입 기간이 {payment_years}년으로 최소 {MIN_PAYMENT_YEARS}년에 미달합니다. "
                f"연금 개시 연령을 만 {current_age + MIN_PAYMENT_YEARS}세 이후로 조정해 주세요."
            ),
        }

    if product_id == "pension-001" and start_age < MIN_START_AGE:
        return {
            "error": "start_age_too_early",
            "message": f"연금저축은 만 {MIN_START_AGE}세 이후부터 수령할 수 있습니다.",
        }

    monthly = monthly_payment_manwon * 10_000
    rate = ASSUMED_CREDIT_RATE / 12
    months = payment_years * 12

    principal = monthly * months
    accumulated = monthly * (((1 + rate) ** months - 1) / rate)

    payout_months = payout_years * 12
    monthly_pension = accumulated * rate / (1 - (1 + rate) ** -payout_months)

    result: dict[str, Any] = {
        "product_id": product_id,
        "product_name": product["name"],
        "current_age": current_age,
        "start_age": start_age,
        "payment_years": payment_years,
        "payout_years": payout_years,
        "monthly_payment_krw": monthly,
        "total_principal_krw": int(principal),
        "estimated_accumulated_krw": int(accumulated),
        "estimated_monthly_pension_krw": int(round(monthly_pension / 10) * 10),
        "assumed_annual_rate": ASSUMED_CREDIT_RATE,
        "disclaimer": (
            f"공시이율 연 {ASSUMED_CREDIT_RATE * 100:.1f}% 가정에 따른 추정치이며 확정 수익률이 아닙니다. "
            "실제 수령액은 공시이율 변동과 사업비 차감에 따라 달라집니다."
        ),
    }

    if product_id == "pension-001":
        annual_payment_manwon = monthly_payment_manwon * 12
        deductible = min(annual_payment_manwon, TAX_CREDIT_LIMIT_MANWON)
        result["tax_credit"] = {
            "annual_payment_manwon": annual_payment_manwon,
            "deductible_manwon": deductible,
            "limit_manwon": TAX_CREDIT_LIMIT_MANWON,
            "over_limit": annual_payment_manwon > TAX_CREDIT_LIMIT_MANWON,
        }
        if annual_income_manwon is None:
            # 소득을 모르면 양쪽 구간을 모두 제시해 임의 가정을 막는다.
            result["tax_credit"]["estimate_by_income"] = {
                f"총급여 {INCOME_THRESHOLD_MANWON}만원 이하": int(
                    deductible * 10_000 * TAX_CREDIT_RATE_LOW_INCOME
                ),
                f"총급여 {INCOME_THRESHOLD_MANWON}만원 초과": int(
                    deductible * 10_000 * TAX_CREDIT_RATE_HIGH_INCOME
                ),
            }
        else:
            applied = tax_credit_rate(annual_income_manwon)
            result["tax_credit"]["annual_income_manwon"] = annual_income_manwon
            result["tax_credit"]["applied_rate"] = applied
            result["tax_credit"]["annual_refund_krw"] = int(deductible * 10_000 * applied)

    return result


# ---------------------------------------------------------------------------
# 2. 적합성 진단 (금융소비자보호법상 적합성 원칙)
# ---------------------------------------------------------------------------

# 진단 결과를 서버가 보관한다. 모델이 "적합 판정을 받았다"고 주장해도
# 여기에 기록이 없으면 청약이 진행되지 않는다 (프롬프트가 아닌 코드로 강제).
_SUITABILITY: dict[str, dict[str, Any]] = {}

_VALID_PURPOSES = ("노후자금", "세액공제", "목돈마련", "상속증여", "기타")


def check_suitability(
    age: int,
    annual_income_manwon: int,
    monthly_payment_manwon: int,
    purpose: str,
    start_age: int = DEFAULT_START_AGE,
) -> dict[str, Any]:
    """가입 권유 전 적합성을 진단한다. 청약의 선행 조건이다."""
    if purpose not in _VALID_PURPOSES:
        return {
            "error": "invalid_purpose",
            "message": f"purpose 는 다음 중 하나여야 합니다: {', '.join(_VALID_PURPOSES)}",
        }
    if annual_income_manwon < 0 or monthly_payment_manwon <= 0:
        return {"error": "invalid_input", "message": "소득과 납입액은 0보다 커야 합니다."}

    warnings: list[str] = []
    blockers: list[str] = []

    monthly_income = annual_income_manwon * 10_000 / 12
    ratio = (monthly_payment_manwon * 10_000 / monthly_income) if monthly_income else 1.0
    if ratio > MAX_PAYMENT_TO_INCOME_RATIO:
        blockers.append(
            f"월 납입액이 월소득의 {ratio * 100:.0f}% 로 권장 한도"
            f"({MAX_PAYMENT_TO_INCOME_RATIO * 100:.0f}%)를 초과합니다. 납입 부담으로 중도해지 위험이 큽니다."
        )
    elif ratio > MAX_PAYMENT_TO_INCOME_RATIO * 0.7:
        warnings.append("월 납입액이 소득 대비 다소 높습니다. 납입 지속 가능성을 검토하세요.")

    payment_years = start_age - age
    if payment_years < MIN_PAYMENT_YEARS:
        blockers.append(
            f"연금 개시까지 {payment_years}년으로 최소 납입 기간({MIN_PAYMENT_YEARS}년)에 미달합니다."
        )

    if purpose == "목돈마련":
        warnings.append(
            "연금상품은 장기 노후자금 목적입니다. 단기 목돈 마련이 목적이라면 "
            "중도해지 시 원금 손실과 세금 추징이 발생할 수 있어 적합하지 않습니다."
        )

    if age >= MIN_START_AGE:
        warnings.append("만 55세 이상이므로 납입 기간이 짧아 세액공제 효과가 제한적일 수 있습니다.")

    result = "부적합" if blockers else ("주의" if warnings else "적합")
    suitability_id = f"S-{uuid.uuid4().hex[:10]}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=SUITABILITY_TTL_MINUTES)

    _SUITABILITY[suitability_id] = {
        "result": result,
        "expires_at": expires_at,
        "monthly_payment_manwon": monthly_payment_manwon,
    }

    return {
        "suitability_id": suitability_id,
        "result": result,
        "blockers": blockers,
        "warnings": warnings,
        "payment_to_income_ratio": round(ratio, 3),
        "expires_in_minutes": SUITABILITY_TTL_MINUTES,
        "message": {
            "적합": "적합 판정입니다. 청약을 진행할 수 있습니다.",
            "주의": "가입은 가능하나 아래 유의사항을 고객에게 반드시 설명한 뒤 진행하세요.",
            "부적합": "부적합 판정입니다. 이 조건으로는 청약을 권유할 수 없습니다. 납입액이나 개시 연령을 조정해 다시 진단하세요.",
        }[result],
    }


# ---------------------------------------------------------------------------
# 3. 청약 접수
# ---------------------------------------------------------------------------


def start_application(
    product_id: str,
    monthly_payment_manwon: int,
    applicant_name: str,
    suitability_id: str,
) -> dict[str, Any]:
    """청약을 접수하고 다음 절차를 안내한다.

    실제 계약 체결이 아니라 '청약 접수' 단계까지만 처리한다.
    본인인증·전자서명·초회보험료 납입은 별도 인증 채널에서 이루어져야 한다.
    """
    product = get_product(product_id)
    if product is None or not _is_pension(product):
        return {
            "error": "not_a_pension_product",
            "message": "연금 상품이 아닙니다.",
        }

    record = _SUITABILITY.get(suitability_id)
    if record is None:
        return {
            "error": "suitability_required",
            "message": "적합성 진단이 필요합니다. check_suitability 를 먼저 수행하세요.",
        }
    if record["expires_at"] < datetime.now(timezone.utc):
        return {
            "error": "suitability_expired",
            "message": "적합성 진단이 만료되었습니다. 다시 진단해 주세요.",
        }
    if record["result"] == "부적합":
        return {
            "error": "suitability_failed",
            "message": "적합성 진단 결과가 부적합이므로 청약을 진행할 수 없습니다.",
        }
    if record["monthly_payment_manwon"] != monthly_payment_manwon:
        return {
            "error": "payment_mismatch",
            "message": (
                f"진단 시 납입액({record['monthly_payment_manwon']}만원)과 청약 납입액"
                f"({monthly_payment_manwon}만원)이 다릅니다. 변경된 금액으로 다시 진단해 주세요."
            ),
        }

    now = datetime.now(timezone.utc)
    application_no = f"A-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    return {
        "application_no": application_no,
        "product_id": product_id,
        "product_name": product["name"],
        "applicant_name": applicant_name,
        "monthly_payment_krw": monthly_payment_manwon * 10_000,
        "status": "접수완료",
        "next_steps": [
            "본인인증 (휴대폰 또는 공동인증서)",
            "상품설명서·약관 확인 및 전자서명",
            "초회 보험료 납입 계좌 등록",
            "청약 심사 후 증권 발급 (영업일 기준 2~3일)",
        ],
        "cooling_off": "보험증권을 받은 날부터 15일 이내(청약일로부터 30일 이내) 청약철회가 가능하며 납입 보험료 전액을 돌려받습니다.",
        "message": "청약이 접수되었습니다. 등록된 휴대폰으로 전자서명 링크를 발송했습니다.",
    }
