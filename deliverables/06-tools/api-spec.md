# 도구(Tool) 명세

> 챗봇이 호출하는 함수 정의. LLM 도구 스키마로 그대로 변환할 수 있습니다.
> 구현 참조: `pension_calc.py`

---

## 공통 규약

모든 계산 도구는 아래 구조로 반환합니다.

```json
{
  "value": { "...계산 결과..." },
  "assumptions": ["연 3% 복리 가정", "..."],
  "disclosures": ["DISC-006", "DISC-004"],
  "citations": ["(국민연금공단 공표통계)"]
}
```

| 필드 | 챗봇의 의무 |
| --- | --- |
| `value` | 답변에 사용 |
| `assumptions` | **반드시 답변에 노출** |
| `disclosures` | 해당 고지문을 `required-disclosures.json`에서 가져와 출력 |
| `citations` | 통계 인용 시 그대로 병기 |

> ⚠️ `assumptions`와 `disclosures`를 생략한 응답은 출력 필터에서 차단되거나 재생성됩니다.

---

## 1. `get_statistic`

통계 수치 조회.

```json
{
  "name": "get_statistic",
  "description": "노후 생활비, 국민연금 평균 수령액, 기대여명 등 통계 수치를 조회한다. 챗봇은 통계를 기억에서 말하지 말고 반드시 이 도구를 호출해야 한다.",
  "parameters": {
    "type": "object",
    "properties": {
      "metric_id": {
        "type": "string",
        "description": "statistics.yaml의 id (예: STAT-LC-003)"
      },
      "metric_name": {
        "type": "string",
        "description": "id를 모를 때 사용하는 이름 검색 (예: 부부_노후_적정생활비_월)"
      }
    }
  }
}
```

**동작:** `expires_at`이 경과한 항목은 조회 결과에서 제외하고 `null`을 반환합니다. 챗봇은 이 경우 "확인 후 안내드리겠습니다"로 응답해야 합니다.

---

## 2. `get_tax_rule`

세제 규칙 조회.

```json
{
  "name": "get_tax_rule",
  "parameters": {
    "type": "object",
    "properties": {
      "rule_id": { "type": "string", "description": "예: TAX-LIM-002" },
      "topic": {
        "type": "string",
        "enum": ["세액공제한도", "공제율", "연금소득세", "중도해지", "비과세요건"]
      }
    }
  }
}
```

---

## 3. `estimate_national_pension`

```json
{
  "name": "estimate_national_pension",
  "description": "국민연금 예상 월 수령액을 추정한다. 소득대체율 방식과 통계 평균 방식을 모두 계산해 보수적인 값을 반환한다.",
  "parameters": {
    "type": "object",
    "required": ["age", "monthly_income"],
    "properties": {
      "age": { "type": "integer", "minimum": 18, "maximum": 100 },
      "monthly_income": { "type": "integer", "minimum": 0 },
      "contribution_years": { "type": "integer", "description": "생략 시 27세 가입~60세 납부로 가정" },
      "birth_year": { "type": "integer", "description": "수급 개시 연령 판정용" }
    }
  }
}
```

**반환 예시**

```json
{
  "value": {
    "estimated_monthly": 1121000,
    "start_age": 65,
    "contribution_years": 33,
    "method_rate_based": 1242000,
    "method_statistic_based": 1120539,
    "years_until_start": 27
  },
  "assumptions": ["가입기간 33년 가정", "명목소득대체율 43% 적용 (40년 가입 기준)", "두 방식 중 보수적인 값을 대표값으로 제시"],
  "disclosures": ["DISC-015"],
  "citations": ["(국민연금공단 공표통계)", "(보건복지부, 2025년 연금개혁법 기준)"]
}
```

> ⚠️ `DISC-015` — 반드시 "추정치이며 국민연금공단에서 정확히 확인 가능"을 함께 안내합니다.

---

## 4. `calc_income_gap`

```json
{
  "name": "calc_income_gap",
  "parameters": {
    "type": "object",
    "required": ["national_pension"],
    "properties": {
      "national_pension": { "type": "integer" },
      "retirement_pension": { "type": "integer", "default": 0 },
      "private_pension": { "type": "integer", "default": 0 },
      "household": { "type": "string", "enum": ["single", "couple"], "default": "couple" },
      "target_level": { "type": "string", "enum": ["minimum", "adequate"], "default": "adequate" },
      "custom_target": { "type": "integer", "description": "고객이 직접 지정한 목표 생활비" }
    }
  }
}
```

---

## 5. `calc_pension_crevasse`

```json
{
  "name": "calc_pension_crevasse",
  "description": "퇴직 시점과 국민연금 수급 개시 사이의 소득 공백기를 계산한다.",
  "parameters": {
    "type": "object",
    "required": ["current_age"],
    "properties": {
      "current_age": { "type": "integer" },
      "birth_year": { "type": "integer" },
      "retirement_age": { "type": "number", "description": "생략 시 통계 평균 49.4세" },
      "monthly_need": { "type": "integer", "description": "생략 시 부부 최소생활비" },
      "conservative": { "type": "boolean", "description": "true면 53.0세 기준(더 짧은 공백)" }
    }
  }
}
```

---

## 6. `simulate_accumulation`

```json
{
  "name": "simulate_accumulation",
  "parameters": {
    "type": "object",
    "required": ["monthly_premium", "years"],
    "properties": {
      "monthly_premium": { "type": "integer", "minimum": 1 },
      "years": { "type": "integer", "minimum": 1 },
      "annual_rate": { "type": "number", "default": 0.03, "maximum": 0.04 }
    }
  }
}
```

> 🚫 `annual_rate > 0.04`면 `SimulationRateError`를 발생시킵니다 (FB-014).
> 이것이 과도한 수익률 가정에 대한 **1차 방어선**이며, 출력 필터 정규식은 보조 수단입니다.

---

## 7. `compare_start_timing`

"나중에 할게요" 반론 처리 전용.

```json
{
  "name": "compare_start_timing",
  "parameters": {
    "type": "object",
    "required": ["monthly_premium", "current_age"],
    "properties": {
      "monthly_premium": { "type": "integer" },
      "current_age": { "type": "integer" },
      "target_age": { "type": "integer", "default": 65 },
      "delay_years": { "type": "array", "items": { "type": "integer" }, "default": [0, 5, 10] },
      "annual_rate": { "type": "number", "default": 0.03 }
    }
  }
}
```

**반환에 포함되는 `required_premium_to_match`** — 지연분을 만회하려면 월 얼마를 넣어야 하는지. 반론 처리에서 가장 강력한 수치입니다.

---

## 8. `calc_tax_credit`

```json
{
  "name": "calc_tax_credit",
  "parameters": {
    "type": "object",
    "required": ["annual_premium", "annual_income"],
    "properties": {
      "annual_premium": { "type": "integer" },
      "annual_income": { "type": "integer", "description": "총급여 또는 종합소득금액" },
      "has_irp": { "type": "boolean", "default": false },
      "irp_premium": { "type": "integer", "default": 0 },
      "income_type": {
        "type": "string",
        "enum": ["salary", "comprehensive"],
        "default": "salary",
        "description": "⚠️ 자영업자·프리랜서는 반드시 comprehensive (기준선 4,500만 원)"
      }
    }
  }
}
```

> ⚠️ 이 도구 결과에는 `DISC-007`(중도해지 페널티)과 `DISC-008`(변동 가능성)이 항상 포함됩니다. **같은 응답에** 출력해야 합니다.

---

## 9. `calc_early_withdrawal_loss`

'단점 먼저' 원칙 구현용. 세액공제를 안내할 때 함께 호출하기를 권장합니다.

```json
{
  "name": "calc_early_withdrawal_loss",
  "parameters": {
    "type": "object",
    "required": ["accumulated", "total_credited"],
    "properties": {
      "accumulated": { "type": "integer", "description": "현재 적립금" },
      "total_credited": { "type": "integer", "description": "세액공제를 받은 누적 납입액" }
    }
  }
}
```

---

## 10. `simulate_annuity_payout`

```json
{
  "name": "simulate_annuity_payout",
  "parameters": {
    "type": "object",
    "required": ["accumulated"],
    "properties": {
      "accumulated": { "type": "integer" },
      "start_age": { "type": "integer", "default": 65 },
      "payout_years": { "type": "integer", "description": "생략 시 성별 기대여명 적용" },
      "gender": { "type": "string", "enum": ["male", "female"] }
    }
  }
}
```

---

## 11. `search_product_kb`

```json
{
  "name": "search_product_kb",
  "description": "상품 정보를 검색한다. 결과에 없는 상품 조건은 절대 생성하지 않는다.",
  "parameters": {
    "type": "object",
    "required": ["query"],
    "properties": {
      "query": { "type": "string" },
      "category": { "type": "string" },
      "segment": {
        "type": "string",
        "description": "고객 세그먼트. not_suitable_for에 해당하는 상품은 결과에서 제외된다."
      }
    }
  }
}
```

**필터링 규칙** — `compliance_approved=false`, `sales_status != 판매중`, `expires_at` 경과 상품은 결과에서 제외합니다.

---

## 12. `book_consultation`

```json
{
  "name": "book_consultation",
  "parameters": {
    "type": "object",
    "required": ["contact", "preferred_slot", "consent_contact"],
    "properties": {
      "contact": { "type": "string" },
      "preferred_slot": { "type": "string" },
      "consent_contact": { "type": "boolean", "description": "필수. false면 호출 거부" },
      "consent_marketing": { "type": "boolean", "description": "⚠️ 반드시 별도 수집" },
      "context_summary": { "type": "string", "description": "상담사에게 전달할 대화 요약" }
    }
  }
}
```

> 🚫 `consent_contact=false`면 호출이 거부됩니다. 침묵을 동의로 처리할 수 없습니다.

---

## 13. `handoff_to_agent`

```json
{
  "name": "handoff_to_agent",
  "parameters": {
    "type": "object",
    "required": ["reason"],
    "properties": {
      "reason": {
        "type": "string",
        "enum": [
          "customer_request", "contract_intent", "health_info",
          "complaint", "vulnerable_customer", "fallback_exceeded",
          "kb_not_found", "age_out_of_scope"
        ]
      },
      "context_summary": { "type": "string" },
      "urgency": { "type": "string", "enum": ["normal", "high"] }
    }
  }
}
```

`vulnerable_customer`와 `complaint`는 `urgency: high`로 처리합니다.

---

## 도구 호출 정책

| 상황 | 정책 |
| --- | --- |
| 수치가 필요한 응답 | **도구 호출 필수.** 기억·추론으로 숫자 생성 금지 |
| 도구가 `null` 반환 | "확인 후 안내드리겠습니다" + 이관 제안 |
| 도구 오류 | 사용자에게 기술적 오류 노출 금지. 이관으로 전환 |
| 연속 호출 | 3~4개까지 허용 (진단→공백→크레바스 등) |
| 재시도 | 최대 1회. 실패 시 이관 |

---

## 구현 상태

| 도구 | 구현 | 테스트 |
| --- | :---: | :---: |
| `estimate_national_pension` | ✅ | ✅ 7건 |
| `calc_income_gap` | ✅ | ✅ 5건 |
| `calc_pension_crevasse` | ✅ | ✅ 4건 |
| `simulate_accumulation` | ✅ | ✅ 7건 |
| `compare_start_timing` | ✅ | ✅ 4건 |
| `calc_tax_credit` | ✅ | ✅ 11건 |
| `simulate_annuity_payout` | ✅ | ✅ 3건 |
| `calc_early_withdrawal_loss` | ✅ | ✅ 3건 |
| `get_statistic` | ⬜ | — |
| `get_tax_rule` | ⬜ | — |
| `search_product_kb` | ⬜ | — |
| `book_consultation` | ⬜ | — |
| `handoff_to_agent` | ⬜ | — |

계산 도구 8종은 구현·검증 완료(48개 테스트 통과)이며, 나머지 5종은 사내 시스템 연동이 필요해 인터페이스만 정의했습니다.
