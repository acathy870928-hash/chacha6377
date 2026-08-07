"""챗봇이 사용할 툴 정의와 실행 로직.

모든 툴은 순수 파이썬 함수로 구현되어 있어 LLM 없이도 단독 테스트가 가능하다.
`TOOL_SCHEMAS` 는 Messages API 의 `tools` 파라미터에 그대로 전달한다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from .config import DATA_DIR
from .knowledge import (
    format_hits,
    get_product,
    load_claim_guides,
    load_products,
    search,
)
from .pension import check_suitability, simulate_pension, start_application

# ---------------------------------------------------------------------------
# 보험료 산출
# ---------------------------------------------------------------------------

_BASELINE_AGE = 40
_AGE_STEP = 0.03  # 기준연령 대비 1세당 ±3%
_AGE_FACTOR_FLOOR = 0.5
_GENDER_FACTOR = {"male": 1.0, "female": 0.9}
_SMOKER_FACTOR = 1.25


def calculate_premium(
    product_id: str,
    age: int,
    gender: str,
    coverage_amount_manwon: int,
    smoker: bool = False,
) -> dict[str, Any]:
    """예상 월 보험료를 계산한다.

    실제 보험료는 언더라이팅 결과에 따라 달라지므로 참고용 추정치다.
    """
    product = get_product(product_id)
    if product is None:
        return {
            "error": "unknown_product",
            "message": f"'{product_id}' 상품을 찾을 수 없습니다.",
            "available_products": [
                {"id": p["id"], "name": p["name"]} for p in load_products()
            ],
        }

    if product.get("premium_basis") == "payment":
        # 연금은 가입금액이 아니라 납입액 기준이므로 계산 방식이 다르다.
        return {
            "error": "use_simulate_pension",
            "message": (
                f"{product['name']}은 납입액 기준 상품입니다. "
                "보험료 계산 대신 simulate_pension 툴로 예상 연금액을 산출하세요."
            ),
        }

    if gender not in _GENDER_FACTOR:
        return {
            "error": "invalid_gender",
            "message": "gender 는 'male' 또는 'female' 이어야 합니다.",
        }

    if not (product["min_age"] <= age <= product["max_age"]):
        return {
            "error": "age_out_of_range",
            "message": (
                f"{product['name']}의 가입 가능 연령은 만 {product['min_age']}세"
                f"~{product['max_age']}세입니다. (입력: 만 {age}세)"
            ),
        }

    if coverage_amount_manwon <= 0:
        return {
            "error": "invalid_coverage",
            "message": "coverage_amount_manwon 은 1 이상이어야 합니다.",
        }

    age_factor = max(_AGE_FACTOR_FLOOR, 1 + (age - _BASELINE_AGE) * _AGE_STEP)
    gender_factor = _GENDER_FACTOR[gender]
    smoker_factor = _SMOKER_FACTOR if smoker else 1.0

    base = coverage_amount_manwon * product["base_rate_per_10k"]
    monthly = base * age_factor * gender_factor * smoker_factor
    monthly = int(round(monthly / 10) * 10)  # 10원 단위 반올림

    return {
        "product_id": product_id,
        "product_name": product["name"],
        "age": age,
        "gender": gender,
        "smoker": smoker,
        "coverage_amount_manwon": coverage_amount_manwon,
        "monthly_premium_krw": monthly,
        "annual_premium_krw": monthly * 12,
        "factors": {
            "base_krw": int(base),
            "age_factor": round(age_factor, 3),
            "gender_factor": gender_factor,
            "smoker_factor": smoker_factor,
        },
        "renewal": product["renewal"],
        "disclaimer": "실제 보험료는 건강 상태·직업 등 인수심사 결과에 따라 달라질 수 있는 참고용 추정치입니다.",
    }


# ---------------------------------------------------------------------------
# 약관 / FAQ 검색
# ---------------------------------------------------------------------------


def search_policy(query: str, limit: int = 3) -> dict[str, Any]:
    """약관·상품·FAQ 문서를 검색한다."""
    hits = search(query, limit=limit)
    return {
        "query": query,
        "match_count": len(hits),
        "documents": format_hits(hits),
        "source_ids": [hit.document.doc_id for hit in hits],
    }


def list_products() -> dict[str, Any]:
    """취급 중인 상품 목록을 반환한다."""
    return {
        "products": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "summary": p["summary"],
            }
            for p in load_products()
        ]
    }


# ---------------------------------------------------------------------------
# 보험금 청구 안내
# ---------------------------------------------------------------------------


def get_claim_guide(claim_type: str) -> dict[str, Any]:
    """청구 유형별 필요 서류와 절차를 반환한다."""
    guides = load_claim_guides()
    guide = guides.get(claim_type)
    if guide is None:
        return {
            "error": "unknown_claim_type",
            "message": f"'{claim_type}' 유형의 청구 안내가 없습니다.",
            "available_types": list(guides.keys()),
        }
    return {"claim_type": claim_type, **guide}


# ---------------------------------------------------------------------------
# 계약 조회 (목업 데이터)
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _load_contracts() -> list[dict[str, Any]]:
    with open(DATA_DIR / "contracts.json", encoding="utf-8") as f:
        return json.load(f)


def lookup_contract(customer_name: str, birth_date: str) -> dict[str, Any]:
    """이름과 생년월일로 보유 계약을 조회한다 (데모용 목업 데이터).

    실제 서비스에서는 반드시 본인인증을 거친 세션 정보로 조회해야 하며,
    모델이 넘긴 값을 그대로 신뢰해서는 안 된다.
    """
    if not _DATE_RE.match(birth_date):
        return {
            "error": "invalid_birth_date",
            "message": "birth_date 는 YYYY-MM-DD 형식이어야 합니다.",
        }

    for record in _load_contracts():
        if (
            record["customer_name"] == customer_name.strip()
            and record["birth_date"] == birth_date
        ):
            return {
                "customer_name": record["customer_name"],
                "contract_count": len(record["contracts"]),
                "contracts": record["contracts"],
            }

    return {
        "error": "not_found",
        "message": "일치하는 계약 정보를 찾지 못했습니다. 성함과 생년월일을 다시 확인해 주세요.",
    }


# ---------------------------------------------------------------------------
# 상담원 연결
# ---------------------------------------------------------------------------


def escalate_to_agent(
    reason: str, callback_number: str | None = None, priority: str = "normal"
) -> dict[str, Any]:
    """사람 상담원 연결을 요청한다 (데모에서는 티켓 발급만 수행)."""
    now = datetime.now(timezone.utc)
    ticket_no = f"T-{now.strftime('%Y%m%d')}-{abs(hash(reason)) % 10000:04d}"
    return {
        "ticket_no": ticket_no,
        "reason": reason,
        "callback_number": callback_number,
        "priority": priority,
        "message": (
            "상담원 연결이 접수되었습니다. 영업시간(평일 09:00~18:00) 내 순차적으로 "
            "연락드립니다. 급한 경우 고객센터 1588-0000 으로 전화해 주세요."
        ),
    }


# ---------------------------------------------------------------------------
# 스키마 & 디스패치
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_policy",
        "description": (
            "보험 약관·상품 설명·FAQ 문서를 검색합니다. 보장 범위, 면책 사항, "
            "가입 조건, 청약철회, 고지의무, 소멸시효 등 규정에 근거해 답해야 하는 "
            "질문을 받으면 반드시 먼저 이 툴로 근거를 찾은 뒤 답변하세요. "
            "기억에 의존해 약관 내용을 지어내지 마세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 내용. 고객 질문의 핵심 키워드를 포함해 작성합니다. 예: '암보험 면책기간'",
                },
                "limit": {
                    "type": "integer",
                    "description": "반환할 최대 문서 수 (기본 3)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_products",
        "description": "현재 취급 중인 보험 상품 목록과 각 상품의 ID를 반환합니다. 고객이 어떤 상품이 있는지 물어보거나, 보험료 계산을 위해 product_id 를 확인해야 할 때 사용하세요.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate_premium",
        "description": (
            "예상 월 보험료를 계산합니다. 고객이 보험료·견적을 물어보면 사용하세요. "
            "나이·성별·가입금액이 확인되지 않았다면 임의로 값을 정하지 말고 먼저 고객에게 물어보세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "description": "상품 ID. 모르면 list_products 로 먼저 확인합니다.",
                },
                "age": {"type": "integer", "description": "만 나이"},
                "gender": {
                    "type": "string",
                    "enum": ["male", "female"],
                    "description": "성별",
                },
                "coverage_amount_manwon": {
                    "type": "integer",
                    "description": "가입금액 (만원 단위). 예: 3000 은 3,000만원",
                },
                "smoker": {
                    "type": "boolean",
                    "description": "흡연 여부 (기본 false)",
                },
            },
            "required": ["product_id", "age", "gender", "coverage_amount_manwon"],
        },
    },
    {
        "name": "simulate_pension",
        "description": (
            "연금 상품의 예상 적립금·월 연금액·세액공제액을 계산합니다. 고객이 노후 준비, "
            "연금저축, 세액공제, '연금 얼마나 받나요' 등을 물어보면 사용하세요. "
            "직접 계산하지 말고 반드시 이 툴을 쓰세요. 나이와 월 납입액이 확인되지 않았다면 "
            "먼저 물어보세요. 연 소득을 모르면 annual_income_manwon 을 비워두면 소득 구간별 "
            "환급액을 모두 돌려줍니다 — 임의로 소득을 가정하지 마세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "enum": ["pension-001", "pension-002"],
                    "description": "pension-001=연금저축보험(세액공제형), pension-002=일반연금보험(비과세형)",
                },
                "monthly_payment_manwon": {
                    "type": "integer",
                    "description": "월 납입액 (만원 단위). 예: 30 은 30만원",
                },
                "current_age": {"type": "integer", "description": "현재 만 나이"},
                "start_age": {
                    "type": "integer",
                    "description": "연금 개시 희망 연령 (기본 65세). 연금저축은 만 55세 이상만 가능",
                },
                "annual_income_manwon": {
                    "type": "integer",
                    "description": "연간 총급여 (만원). 세액공제율 판정용. 모르면 생략",
                },
                "payout_years": {
                    "type": "integer",
                    "description": "연금 수령 기간 (년, 기본 20년)",
                },
            },
            "required": ["product_id", "monthly_payment_manwon", "current_age"],
        },
    },
    {
        "name": "check_suitability",
        "description": (
            "연금 가입 권유 전 적합성을 진단합니다. 금융소비자보호법상 필수 절차이며, "
            "이 진단 없이는 청약(start_application)이 거부됩니다. "
            "고객이 가입 의사를 밝히면 나이·연소득·희망 납입액·가입목적을 확인한 뒤 호출하세요. "
            "결과가 '부적합'이면 절대 가입을 권유하지 말고 조건 조정을 안내하세요. "
            "'주의'이면 warnings 내용을 고객에게 그대로 설명한 뒤 진행 의사를 다시 확인하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "age": {"type": "integer", "description": "만 나이"},
                "annual_income_manwon": {
                    "type": "integer",
                    "description": "연간 총급여 (만원)",
                },
                "monthly_payment_manwon": {
                    "type": "integer",
                    "description": "희망 월 납입액 (만원)",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["노후자금", "세액공제", "목돈마련", "상속증여", "기타"],
                    "description": "가입 목적",
                },
                "start_age": {
                    "type": "integer",
                    "description": "연금 개시 희망 연령 (기본 65세)",
                },
            },
            "required": [
                "age",
                "annual_income_manwon",
                "monthly_payment_manwon",
                "purpose",
            ],
        },
    },
    {
        "name": "start_application",
        "description": (
            "연금 상품 청약을 접수합니다. 반드시 다음을 모두 마친 뒤에만 호출하세요: "
            "(1) simulate_pension 으로 예상 수령액 제시, (2) check_suitability 통과, "
            "(3) 중도해지 불이익과 원금 손실 가능성 설명, (4) 고객의 명시적 가입 동의. "
            "고객이 '가입할게요'라고 확정하지 않았다면 호출하지 마세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "string",
                    "enum": ["pension-001", "pension-002"],
                },
                "monthly_payment_manwon": {
                    "type": "integer",
                    "description": "월 납입액 (만원). 적합성 진단 시 금액과 일치해야 합니다.",
                },
                "applicant_name": {"type": "string", "description": "청약자 성함"},
                "suitability_id": {
                    "type": "string",
                    "description": "check_suitability 가 반환한 진단 ID",
                },
            },
            "required": [
                "product_id",
                "monthly_payment_manwon",
                "applicant_name",
                "suitability_id",
            ],
        },
    },
    {
        "name": "get_claim_guide",
        "description": "보험금 청구 유형별 필요 서류와 절차, 예상 처리 기간을 반환합니다. 고객이 청구 방법이나 필요 서류를 물어볼 때 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "claim_type": {
                    "type": "string",
                    "enum": ["실손의료비", "암진단", "자동차사고", "사망", "해외여행"],
                    "description": "청구 유형",
                }
            },
            "required": ["claim_type"],
        },
    },
    {
        "name": "lookup_contract",
        "description": (
            "고객이 보유한 계약을 조회합니다. 고객이 '내 보험', '가입한 상품', "
            "'보험료 얼마 내고 있는지' 등을 물어볼 때 사용하세요. "
            "성함과 생년월일이 모두 확인되기 전에는 호출하지 마세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "계약자 성함"},
                "birth_date": {
                    "type": "string",
                    "description": "생년월일 (YYYY-MM-DD)",
                },
            },
            "required": ["customer_name", "birth_date"],
        },
    },
    {
        "name": "escalate_to_agent",
        "description": (
            "사람 상담원 연결을 요청합니다. 고객이 상담원 연결을 명시적으로 요청하거나, "
            "보험금 지급 거절에 대한 이의제기·민원·복잡한 인수심사 등 챗봇이 확정적으로 "
            "답할 수 없는 사안일 때 사용하세요."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "연결이 필요한 사유 요약"},
                "callback_number": {
                    "type": "string",
                    "description": "회신받을 연락처 (고객이 알려준 경우에만)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["normal", "high"],
                    "description": "긴급도 (기본 normal)",
                },
            },
            "required": ["reason"],
        },
    },
]

TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_policy": search_policy,
    "list_products": list_products,
    "calculate_premium": calculate_premium,
    "simulate_pension": simulate_pension,
    "check_suitability": check_suitability,
    "start_application": start_application,
    "get_claim_guide": get_claim_guide,
    "lookup_contract": lookup_contract,
    "escalate_to_agent": escalate_to_agent,
}


def run_tool(name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
    """툴을 실행하고 (직렬화된 결과, is_error) 를 반환한다.

    핸들러 예외는 모델이 복구할 수 있도록 tool_result 의 오류 문자열로 되돌린다.
    """
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"알 수 없는 툴입니다: {name}", True

    try:
        result = handler(**tool_input)
    except TypeError as exc:
        return f"툴 인자가 올바르지 않습니다: {exc}", True
    except Exception as exc:  # noqa: BLE001 - 모델에게 오류를 그대로 전달
        return f"툴 실행 중 오류가 발생했습니다: {exc}", True

    return json.dumps(result, ensure_ascii=False), bool(result.get("error"))
