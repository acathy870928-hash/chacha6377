"""pension_calc 테스트.

실행: python3 test_pension_calc.py
표준 라이브러리 unittest만 사용한다 (외부 의존성 없음).
"""

import unittest

from pension_calc import (
    LIVING_COST,
    MAX_ALLOWED_RATE,
    SimulationRateError,
    TAX_CREDIT_LIMIT_COMBINED,
    calc_early_withdrawal_loss,
    calc_income_gap,
    calc_pension_crevasse,
    calc_tax_credit,
    compare_start_timing,
    estimate_national_pension,
    nps_start_age,
    simulate_accumulation,
    simulate_annuity_payout,
)


class TestNpsStartAge(unittest.TestCase):
    def test_birth_year_boundaries(self):
        self.assertEqual(nps_start_age(1950), 61)
        self.assertEqual(nps_start_age(1956), 61)
        self.assertEqual(nps_start_age(1957), 62)
        self.assertEqual(nps_start_age(1960), 62)
        self.assertEqual(nps_start_age(1961), 63)
        self.assertEqual(nps_start_age(1964), 63)
        self.assertEqual(nps_start_age(1965), 64)
        self.assertEqual(nps_start_age(1968), 64)
        self.assertEqual(nps_start_age(1969), 65)
        self.assertEqual(nps_start_age(1990), 65)


class TestEstimateNationalPension(unittest.TestCase):
    def test_returns_conservative_value(self):
        """두 방식 중 낮은 쪽이 대표값이어야 한다."""
        r = estimate_national_pension(age=38, monthly_income=3_500_000)
        v = r.value
        self.assertLessEqual(
            v["estimated_monthly"],
            max(v["method_rate_based"], v["method_statistic_based"]),
        )

    def test_higher_income_gives_higher_estimate_or_capped(self):
        low = estimate_national_pension(age=40, monthly_income=2_000_000)
        high = estimate_national_pension(age=40, monthly_income=6_000_000)
        self.assertGreaterEqual(
            high.value["estimated_monthly"], low.value["estimated_monthly"]
        )

    def test_short_contribution_yields_zero_statistic(self):
        r = estimate_national_pension(
            age=30, monthly_income=3_000_000, contribution_years=5
        )
        self.assertEqual(r.value["method_statistic_based"], 0)

    def test_start_age_included(self):
        r = estimate_national_pension(age=38, monthly_income=3_000_000)
        self.assertEqual(r.value["start_age"], 65)

    def test_disclosure_attached(self):
        """국민연금 추정치에는 반드시 DISC-015가 붙어야 한다."""
        r = estimate_national_pension(age=38, monthly_income=3_000_000)
        self.assertIn("DISC-015", r.disclosures)

    def test_invalid_age_raises(self):
        with self.assertRaises(ValueError):
            estimate_national_pension(age=5, monthly_income=3_000_000)
        with self.assertRaises(ValueError):
            estimate_national_pension(age=150, monthly_income=3_000_000)

    def test_negative_income_raises(self):
        with self.assertRaises(ValueError):
            estimate_national_pension(age=38, monthly_income=-1)


class TestIncomeGap(unittest.TestCase):
    def test_gap_computation(self):
        r = calc_income_gap(
            national_pension=950_000,
            retirement_pension=400_000,
            household="couple",
            target_level="adequate",
        )
        self.assertEqual(r.value["total_income"], 1_350_000)
        self.assertEqual(r.value["target_cost"], LIVING_COST["couple_adequate"])
        self.assertEqual(
            r.value["monthly_gap"], LIVING_COST["couple_adequate"] - 1_350_000
        )

    def test_no_negative_gap(self):
        """소득이 목표를 넘어도 부족액은 음수가 되지 않는다."""
        r = calc_income_gap(national_pension=5_000_000, household="single")
        self.assertEqual(r.value["monthly_gap"], 0)

    def test_custom_target_overrides(self):
        r = calc_income_gap(national_pension=1_000_000, custom_target=2_000_000)
        self.assertEqual(r.value["target_cost"], 2_000_000)
        self.assertEqual(r.value["monthly_gap"], 1_000_000)
        self.assertEqual(r.citations, [])  # 고객 지정값이므로 통계 인용 없음

    def test_citation_present_for_statistic_target(self):
        r = calc_income_gap(national_pension=1_000_000)
        self.assertTrue(r.citations)

    def test_single_vs_couple(self):
        s = calc_income_gap(national_pension=1_000_000, household="single")
        c = calc_income_gap(national_pension=1_000_000, household="couple")
        self.assertLess(s.value["target_cost"], c.value["target_cost"])


class TestPensionCrevasse(unittest.TestCase):
    def test_gap_years_positive(self):
        r = calc_pension_crevasse(current_age=38)
        self.assertGreater(r.value["gap_years"], 0)
        self.assertEqual(r.value["pension_start_age"], 65)

    def test_conservative_gives_shorter_gap(self):
        typical = calc_pension_crevasse(current_age=40)
        conservative = calc_pension_crevasse(current_age=40, conservative=True)
        self.assertLess(
            conservative.value["gap_years"], typical.value["gap_years"]
        )

    def test_no_negative_gap_for_late_retirement(self):
        r = calc_pension_crevasse(current_age=60, retirement_age=70)
        self.assertEqual(r.value["gap_years"], 0)
        self.assertEqual(r.value["total_needed"], 0)

    def test_total_needed_matches_months(self):
        r = calc_pension_crevasse(
            current_age=40, retirement_age=55, monthly_need=2_000_000
        )
        expected = int(10 * 12 * 2_000_000)
        self.assertEqual(r.value["total_needed"], expected)


class TestSimulateAccumulation(unittest.TestCase):
    def test_zero_rate_equals_principal(self):
        r = simulate_accumulation(200_000, 10, annual_rate=0.0)
        self.assertEqual(r.value["future_value"], r.value["principal"])
        self.assertEqual(r.value["investment_return"], 0)

    def test_compound_exceeds_principal(self):
        r = simulate_accumulation(200_000, 20, annual_rate=0.03)
        self.assertGreater(r.value["future_value"], r.value["principal"])

    def test_longer_period_yields_more(self):
        short = simulate_accumulation(200_000, 10)
        long = simulate_accumulation(200_000, 20)
        self.assertGreater(long.value["future_value"], short.value["future_value"])

    def test_rate_cap_enforced(self):
        """FB-014 — 4%를 넘는 이율 가정은 차단되어야 한다."""
        with self.assertRaises(SimulationRateError):
            simulate_accumulation(200_000, 20, annual_rate=0.08)

    def test_rate_at_cap_allowed(self):
        r = simulate_accumulation(200_000, 20, annual_rate=MAX_ALLOWED_RATE)
        self.assertGreater(r.value["future_value"], 0)

    def test_mandatory_disclosures(self):
        """시뮬레이션 결과에는 가정 명시와 사업비 고지가 붙어야 한다."""
        r = simulate_accumulation(200_000, 20)
        self.assertIn("DISC-006", r.disclosures)
        self.assertIn("DISC-004", r.disclosures)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(ValueError):
            simulate_accumulation(0, 10)
        with self.assertRaises(ValueError):
            simulate_accumulation(200_000, 0)


class TestCompareStartTiming(unittest.TestCase):
    def test_delay_reduces_future_value(self):
        r = compare_start_timing(monthly_premium=300_000, current_age=35)
        rows = r.value["rows"]
        values = [row["future_value"] for row in rows]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_required_premium_increases_with_delay(self):
        r = compare_start_timing(monthly_premium=300_000, current_age=35)
        required = [row["required_premium_to_match"] for row in r.value["rows"]]
        self.assertEqual(required, sorted(required))

    def test_baseline_has_zero_loss(self):
        r = compare_start_timing(monthly_premium=200_000, current_age=38)
        self.assertEqual(r.value["rows"][0]["loss_vs_now"], 0)

    def test_skips_impossible_periods(self):
        """지연 후 납입 기간이 없으면 해당 행은 제외된다."""
        r = compare_start_timing(
            monthly_premium=200_000, current_age=60, delay_years=[0, 5, 10]
        )
        for row in r.value["rows"]:
            self.assertGreater(row["payment_years"], 0)


class TestTaxCredit(unittest.TestCase):
    def test_low_income_rate(self):
        r = calc_tax_credit(annual_premium=6_000_000, annual_income=48_000_000)
        self.assertAlmostEqual(r.value["applied_rate"], 0.165)

    def test_high_income_rate(self):
        r = calc_tax_credit(annual_premium=6_000_000, annual_income=70_000_000)
        self.assertAlmostEqual(r.value["applied_rate"], 0.132)

    def test_threshold_boundary_inclusive(self):
        """총급여 5,500만 원 '이하'는 16.5%가 적용된다."""
        at = calc_tax_credit(annual_premium=6_000_000, annual_income=55_000_000)
        over = calc_tax_credit(annual_premium=6_000_000, annual_income=55_000_001)
        self.assertAlmostEqual(at.value["applied_rate"], 0.165)
        self.assertAlmostEqual(over.value["applied_rate"], 0.132)

    def test_pension_saving_limit_capped(self):
        """연금저축 단독 납입은 600만 원까지만 공제 대상이다."""
        r = calc_tax_credit(annual_premium=10_000_000, annual_income=48_000_000)
        self.assertEqual(r.value["eligible_amount"], 6_000_000)
        self.assertEqual(r.value["excess_amount"], 4_000_000)

    def test_combined_limit_with_irp(self):
        r = calc_tax_credit(
            annual_premium=6_000_000,
            annual_income=48_000_000,
            has_irp=True,
            irp_premium=5_000_000,
        )
        self.assertEqual(r.value["eligible_amount"], TAX_CREDIT_LIMIT_COMBINED)
        self.assertEqual(r.value["excess_amount"], 2_000_000)

    def test_max_refund_low_income(self):
        """900만 원 × 16.5% = 148.5만 원"""
        r = calc_tax_credit(
            annual_premium=6_000_000,
            annual_income=40_000_000,
            has_irp=True,
            irp_premium=3_000_000,
        )
        self.assertEqual(r.value["estimated_refund"], 1_485_000)

    def test_max_refund_high_income(self):
        """900만 원 × 13.2% = 118.8만 원"""
        r = calc_tax_credit(
            annual_premium=6_000_000,
            annual_income=80_000_000,
            has_irp=True,
            irp_premium=3_000_000,
        )
        self.assertEqual(r.value["estimated_refund"], 1_188_000)

    def test_net_burden_less_than_paid(self):
        r = calc_tax_credit(annual_premium=2_400_000, annual_income=48_000_000)
        self.assertLess(r.value["net_burden_annual"], r.value["total_paid"])

    def test_mandatory_disclosures(self):
        """세액공제 안내에는 중도해지 페널티(DISC-007) 고지가 필수다."""
        r = calc_tax_credit(annual_premium=2_400_000, annual_income=48_000_000)
        self.assertIn("DISC-007", r.disclosures)
        self.assertIn("DISC-008", r.disclosures)

    def test_comprehensive_income_threshold(self):
        r = calc_tax_credit(
            annual_premium=6_000_000,
            annual_income=46_000_000,
            income_type="comprehensive",
        )
        self.assertAlmostEqual(r.value["applied_rate"], 0.132)

    def test_negative_premium_raises(self):
        with self.assertRaises(ValueError):
            calc_tax_credit(annual_premium=-1, annual_income=40_000_000)


class TestAnnuityPayout(unittest.TestCase):
    def test_tax_rate_by_age(self):
        self.assertAlmostEqual(
            simulate_annuity_payout(100_000_000, start_age=60).value["tax_rate"], 0.055
        )
        self.assertAlmostEqual(
            simulate_annuity_payout(100_000_000, start_age=72).value["tax_rate"], 0.044
        )
        self.assertAlmostEqual(
            simulate_annuity_payout(100_000_000, start_age=82).value["tax_rate"], 0.033
        )

    def test_net_less_than_gross(self):
        r = simulate_annuity_payout(100_000_000, start_age=65)
        self.assertLess(r.value["net_monthly"], r.value["gross_monthly"])

    def test_gender_affects_payout_years(self):
        m = simulate_annuity_payout(100_000_000, gender="male")
        f = simulate_annuity_payout(100_000_000, gender="female")
        self.assertLess(m.value["payout_years"], f.value["payout_years"])
        # 기간이 길수록 월 수령액은 적어진다
        self.assertGreater(m.value["gross_monthly"], f.value["gross_monthly"])


class TestEarlyWithdrawalLoss(unittest.TestCase):
    def test_tax_applied(self):
        r = calc_early_withdrawal_loss(
            accumulated=10_000_000, total_credited=9_600_000
        )
        self.assertAlmostEqual(r.value["tax_rate"], 0.165)
        self.assertEqual(r.value["tax_amount"], 1_650_000)
        self.assertEqual(r.value["net_received"], 8_350_000)

    def test_net_less_than_accumulated(self):
        r = calc_early_withdrawal_loss(
            accumulated=50_000_000, total_credited=45_000_000
        )
        self.assertLess(r.value["net_received"], r.value["accumulated"])

    def test_disclosure_attached(self):
        r = calc_early_withdrawal_loss(accumulated=1_000_000, total_credited=900_000)
        self.assertIn("DISC-007", r.disclosures)


class TestComplianceInvariants(unittest.TestCase):
    """컴플라이언스 불변식 — 이 테스트가 깨지면 배포하면 안 된다."""

    def test_every_numeric_result_has_assumptions(self):
        results = [
            estimate_national_pension(38, 3_000_000),
            calc_income_gap(900_000),
            calc_pension_crevasse(38),
            simulate_accumulation(200_000, 20),
            compare_start_timing(200_000, 38),
            calc_tax_credit(2_400_000, 48_000_000),
            simulate_annuity_payout(100_000_000),
            calc_early_withdrawal_loss(10_000_000, 9_000_000),
        ]
        for r in results:
            self.assertTrue(
                r.assumptions, f"가정 조건이 비어 있음: {r.value}"
            )

    def test_simulations_carry_rate_disclosure(self):
        """이율 가정이 들어간 계산에는 DISC-006이 반드시 있어야 한다."""
        for r in [
            simulate_accumulation(200_000, 20),
            compare_start_timing(200_000, 38),
            simulate_annuity_payout(100_000_000),
        ]:
            self.assertIn("DISC-006", r.disclosures)

    def test_no_simulation_exceeds_rate_cap(self):
        for rate in [0.041, 0.05, 0.10, 1.0]:
            with self.assertRaises(SimulationRateError):
                simulate_accumulation(200_000, 20, annual_rate=rate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
