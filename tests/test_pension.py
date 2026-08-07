import pytest

from app.pension import (
    MIN_PAYMENT_YEARS,
    TAX_CREDIT_LIMIT_MANWON,
    check_suitability,
    simulate_pension,
    start_application,
)
from app.tools import calculate_premium, run_tool


class TestSimulatePension:
    def test_basic_projection(self):
        result = simulate_pension("pension-001", 30, current_age=38, start_age=65)
        assert result["payment_years"] == 27
        assert result["total_principal_krw"] == 30 * 10_000 * 27 * 12
        # 이자가 붙으므로 적립금은 원금보다 커야 한다.
        assert result["estimated_accumulated_krw"] > result["total_principal_krw"]
        assert result["estimated_monthly_pension_krw"] > 0

    def test_longer_payment_yields_more(self):
        early = simulate_pension("pension-001", 30, current_age=30)
        late = simulate_pension("pension-001", 30, current_age=50)
        assert (
            early["estimated_monthly_pension_krw"] > late["estimated_monthly_pension_krw"]
        )

    def test_tax_credit_shows_both_brackets_when_income_unknown(self):
        credit = simulate_pension("pension-001", 30, current_age=38)["tax_credit"]
        assert len(credit["estimate_by_income"]) == 2
        assert "applied_rate" not in credit

    def test_tax_credit_uses_low_rate_above_threshold(self):
        low = simulate_pension("pension-001", 50, 38, annual_income_manwon=5000)
        high = simulate_pension("pension-001", 50, 38, annual_income_manwon=8000)
        assert low["tax_credit"]["applied_rate"] == 0.165
        assert high["tax_credit"]["applied_rate"] == 0.132
        assert (
            low["tax_credit"]["annual_refund_krw"]
            > high["tax_credit"]["annual_refund_krw"]
        )

    def test_tax_credit_caps_at_limit(self):
        # 월 100만원 = 연 1,200만원 이지만 공제는 한도까지만
        credit = simulate_pension("pension-001", 100, 38, annual_income_manwon=5000)[
            "tax_credit"
        ]
        assert credit["deductible_manwon"] == TAX_CREDIT_LIMIT_MANWON
        assert credit["over_limit"] is True

    def test_non_taxable_product_has_no_tax_credit(self):
        assert "tax_credit" not in simulate_pension("pension-002", 30, current_age=38)

    def test_rejects_non_pension_product(self):
        assert simulate_pension("cancer-001", 30, 38)["error"] == "not_a_pension_product"

    def test_rejects_short_payment_period(self):
        result = simulate_pension("pension-001", 30, current_age=62, start_age=65)
        assert result["error"] == "payment_period_too_short"
        assert str(MIN_PAYMENT_YEARS) in result["message"]

    def test_rejects_early_start_age_for_tax_qualified(self):
        result = simulate_pension("pension-001", 30, current_age=40, start_age=50)
        assert result["error"] == "start_age_too_early"

    def test_rejects_invalid_payment(self):
        assert simulate_pension("pension-001", 0, 38)["error"] == "invalid_payment"


class TestCheckSuitability:
    def test_reasonable_case_is_suitable(self):
        result = check_suitability(38, 6000, 30, "노후자금")
        assert result["result"] == "적합"
        assert result["suitability_id"].startswith("S-")

    def test_overcommitment_is_blocked(self):
        # 연소득 3,000만원 (월 250만원) 에 월 150만원 납입 = 60%
        result = check_suitability(38, 3000, 150, "노후자금")
        assert result["result"] == "부적합"
        assert result["blockers"]

    def test_short_horizon_is_blocked(self):
        result = check_suitability(63, 6000, 30, "노후자금", start_age=65)
        assert result["result"] == "부적합"

    def test_short_term_purpose_warns(self):
        result = check_suitability(38, 6000, 30, "목돈마련")
        assert result["result"] == "주의"
        assert any("장기" in w for w in result["warnings"])

    def test_invalid_purpose_rejected(self):
        assert check_suitability(38, 6000, 30, "코인투자")["error"] == "invalid_purpose"


class TestStartApplication:
    def test_requires_suitability(self):
        result = start_application("pension-001", 30, "홍길동", "S-nonexistent")
        assert result["error"] == "suitability_required"

    def test_blocked_when_unsuitable(self):
        sid = check_suitability(38, 3000, 150, "노후자금")["suitability_id"]
        result = start_application("pension-001", 150, "홍길동", sid)
        assert result["error"] == "suitability_failed"

    def test_payment_must_match_diagnosis(self):
        sid = check_suitability(38, 6000, 30, "노후자금")["suitability_id"]
        result = start_application("pension-001", 80, "홍길동", sid)
        assert result["error"] == "payment_mismatch"

    def test_succeeds_after_suitability(self):
        sid = check_suitability(38, 6000, 30, "노후자금")["suitability_id"]
        result = start_application("pension-001", 30, "홍길동", sid)
        assert result["application_no"].startswith("A-")
        assert result["status"] == "접수완료"
        assert "청약철회" in result["cooling_off"]
        assert len(result["next_steps"]) >= 3

    def test_warning_result_still_allows_application(self):
        sid = check_suitability(38, 6000, 30, "목돈마련")["suitability_id"]
        assert start_application("pension-001", 30, "홍길동", sid)["application_no"]


class TestPensionRoutedAwayFromPremiumTool:
    def test_calculate_premium_redirects_pension(self):
        result = calculate_premium("pension-001", 38, "male", 3000)
        assert result["error"] == "use_simulate_pension"
        assert "simulate_pension" in result["message"]

    def test_dispatch_through_run_tool(self):
        content, is_error = run_tool(
            "simulate_pension",
            {"product_id": "pension-001", "monthly_payment_manwon": 30, "current_age": 38},
        )
        assert not is_error
        assert "estimated_monthly_pension_krw" in content
