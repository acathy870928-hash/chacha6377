import json

import pytest

from app.tools import (
    calculate_premium,
    escalate_to_agent,
    get_claim_guide,
    list_products,
    lookup_contract,
    run_tool,
    search_policy,
)


class TestCalculatePremium:
    def test_baseline_age_has_no_age_adjustment(self):
        result = calculate_premium("cancer-001", age=40, gender="male", coverage_amount_manwon=3000)
        # base_rate_per_10k=12 -> 3000 * 12 = 36,000원, 기준연령/남성/비흡연이므로 계수 1.0
        assert result["monthly_premium_krw"] == 36000
        assert result["annual_premium_krw"] == 36000 * 12

    def test_older_age_costs_more(self):
        young = calculate_premium("cancer-001", 30, "male", 3000)["monthly_premium_krw"]
        old = calculate_premium("cancer-001", 55, "male", 3000)["monthly_premium_krw"]
        assert old > young

    def test_female_is_cheaper_than_male(self):
        male = calculate_premium("life-001", 40, "male", 1000)["monthly_premium_krw"]
        female = calculate_premium("life-001", 40, "female", 1000)["monthly_premium_krw"]
        assert female < male

    def test_smoker_surcharge_applied(self):
        base = calculate_premium("cancer-001", 40, "male", 3000)["monthly_premium_krw"]
        smoker = calculate_premium("cancer-001", 40, "male", 3000, smoker=True)[
            "monthly_premium_krw"
        ]
        assert smoker == pytest.approx(base * 1.25, rel=0.01)

    def test_age_factor_has_floor(self):
        # 매우 어린 나이여도 계수가 0 이하로 떨어지지 않아야 한다.
        result = calculate_premium("health-001", 0, "male", 5000)
        assert result["monthly_premium_krw"] > 0
        assert result["factors"]["age_factor"] == 0.5

    def test_unknown_product_returns_error_with_options(self):
        result = calculate_premium("nope-999", 40, "male", 1000)
        assert result["error"] == "unknown_product"
        assert any(p["id"] == "cancer-001" for p in result["available_products"])

    def test_age_out_of_range(self):
        result = calculate_premium("cancer-001", 80, "male", 3000)
        assert result["error"] == "age_out_of_range"

    def test_invalid_gender(self):
        assert calculate_premium("cancer-001", 40, "x", 3000)["error"] == "invalid_gender"

    def test_invalid_coverage(self):
        assert calculate_premium("cancer-001", 40, "male", 0)["error"] == "invalid_coverage"


class TestSearchPolicy:
    def test_finds_cancer_product(self):
        result = search_policy("암보험 면책기간")
        assert result["match_count"] > 0
        assert "cancer-001" in result["source_ids"] or "faq-006" in result["source_ids"]

    def test_finds_duplicate_coverage_faq(self):
        result = search_policy("실손보험 중복 가입해도 되나요")
        assert "faq-007" in result["source_ids"]

    def test_empty_query_returns_no_match(self):
        assert search_policy("   ")["match_count"] == 0

    def test_respects_limit(self):
        assert len(search_policy("보험", limit=2)["source_ids"]) <= 2


class TestClaimGuide:
    def test_known_type(self):
        guide = get_claim_guide("암진단")
        assert guide["documents"]
        assert guide["steps"]
        assert guide["processing_days"] > 0

    def test_unknown_type_lists_options(self):
        result = get_claim_guide("우주여행")
        assert result["error"] == "unknown_claim_type"
        assert "실손의료비" in result["available_types"]


class TestLookupContract:
    def test_found(self):
        result = lookup_contract("홍길동", "1985-03-12")
        assert result["contract_count"] == 2
        assert result["contracts"][0]["contract_no"].startswith("P-")

    def test_not_found(self):
        assert lookup_contract("없는사람", "1990-01-01")["error"] == "not_found"

    def test_rejects_bad_date_format(self):
        assert lookup_contract("홍길동", "1985/03/12")["error"] == "invalid_birth_date"


class TestMisc:
    def test_list_products_has_ids(self):
        products = list_products()["products"]
        assert len(products) >= 6
        assert all("id" in p and "name" in p for p in products)

    def test_escalate_returns_ticket(self):
        result = escalate_to_agent("지급 거절 이의제기", callback_number="010-0000-0000")
        assert result["ticket_no"].startswith("T-")
        assert result["callback_number"] == "010-0000-0000"


class TestRunTool:
    def test_dispatches_and_serializes(self):
        content, is_error = run_tool("get_claim_guide", {"claim_type": "실손의료비"})
        assert not is_error
        assert json.loads(content)["title"]

    def test_unknown_tool_is_error(self):
        content, is_error = run_tool("does_not_exist", {})
        assert is_error
        assert "알 수 없는 툴" in content

    def test_bad_arguments_do_not_raise(self):
        content, is_error = run_tool("calculate_premium", {"wrong": 1})
        assert is_error
        assert "인자" in content

    def test_tool_level_error_marked(self):
        content, is_error = run_tool("get_claim_guide", {"claim_type": "없음"})
        assert is_error
        assert json.loads(content)["error"] == "unknown_claim_type"
