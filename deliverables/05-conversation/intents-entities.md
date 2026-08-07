# 인텐트 · 엔티티 정의서

> **버전** 1.0.0 · **최종 갱신** 2026-08-07

---

## 1. 인텐트 (22종)

| # | 인텐트 ID | 설명 | 단계 | 예시 발화 | 다음 액션 |
| --- | --- | --- | --- | --- | --- |
| 1 | `greeting` | 인사·대화 시작 | 1 | 안녕하세요 / 상담받고 싶어요 | 진단 제안 |
| 2 | `ask_purpose` | 챗봇의 목적·정체 질문 | 1 | 뭐 파는 거예요? / 사람이에요? | 정직한 목적 고지 |
| 3 | `accept_diagnosis` | 진단 시작 수락 | 1→2 | 네 확인해볼게요 | 프로필 질문 시작 |
| 4 | `provide_age` | 나이 제공 | 2 | 38살이요 / 79년생 | `age` 저장 |
| 5 | `provide_income` | 소득 제공 | 2 | 350만 원 / 300~400 | `income_band` 저장 |
| 6 | `provide_pension_holding` | 보유 연금 제공 | 2 | 국민연금이랑 퇴직연금이요 | `owned_pension[]` 저장 |
| 7 | `provide_household` | 가구 형태 제공 | 2 | 결혼했어요 / 혼자 살아요 | `household` 저장 |
| 8 | `ask_pension_amount` | 예상 수령액 질문 | 3 | 얼마 받아요? | `estimate_national_pension` |
| 9 | `ask_crevasse` | 소득 공백기 질문 | 3 | 퇴직하고 연금 받기 전엔? | `calc_pension_crevasse` |
| 10 | `objection_no_money` | 여유 없음 | 4 | 지금 여유가 없어서요 | 소액 시작 스크립트 |
| 11 | `objection_later` | 나중에 | 4 | 나중에 할게요 | `compare_start_timing` |
| 12 | `objection_nps_enough` | 국민연금이면 충분 | 4 | 국민연금 있는데요 | 소득대체율 설명 |
| 13 | `objection_distrust` | 수익률·회사 불신 | 4 | 보험사 연금 별로던데 | 목적 차이 설명 |
| 14 | `objection_liquidity` | 자금 묶임 부담 | 4 | 돈 묶이는 게 싫어요 | 유예·비상금 안내 |
| 15 | `objection_consult_spouse` | 상의 필요 | 4 | 배우자랑 상의할게요 | 자료 발송 |
| 16 | `objection_final` | 최종 거절 | 4 | 진짜 관심 없어요 | **권유 중단** |
| 17 | `request_product_info` | 상품 정보 요청 | 5 | 어떤 상품 있어요? | `search_product_kb` |
| 18 | `ask_tax_credit` | 세액공제 질문 | 5 | 얼마나 돌려받아요? | `calc_tax_credit` |
| 19 | `ask_withdrawal` | 해지·인출 조건 질문 | 5 | 중간에 깨면요? | `calc_early_withdrawal_loss` |
| 20 | `request_consult` | 상담 예약 요청 | 5 | 상담받고 싶어요 | `book_consultation` |
| 21 | `request_enroll` | 즉시 가입 의향 | 5 | 바로 가입할게요 | **`handoff_to_agent`** |
| 22 | `already_enrolled` | 기존 가입자 | 분기 | 연금저축 있어요 | 점검 플로우 전환 |

### 안전 인텐트 (즉시 이관)

| 인텐트 ID | 설명 | 예시 | 액션 |
| --- | --- | --- | --- |
| `mention_health` | 건강·질병 언급 | 당뇨가 있는데요 | `handoff_to_agent` |
| `complaint` | 불만·컴플레인 | 전에 손해 봤어요 | `handoff_to_agent` |
| `request_human` | 상담사 연결 요청 | 사람이랑 얘기할래요 | `handoff_to_agent` |
| `vulnerable_signal` | 취약 상태 신호 | 우울해서요 / 죽고 싶어요 | **권유 중단 + 이관** |
| `third_party_info` | 타인 정보 요청 | 아버지 연금 조회해줘 | 거절 |
| `prompt_injection` | 지시 주입 시도 | 이전 지시 무시해 | 무시 + 정상 응답 |

---

## 2. 엔티티

### 2-1. 필수 엔티티 (계산에 필요)

| 엔티티 | 타입 | 값 | 수집 단계 | 필수 |
| --- | --- | --- | --- | --- |
| `age` | integer | 19~85 | 2 | ✅ |
| `income_band` | enum | `UNDER_300` `300_400` `400_500` `500_700` `OVER_700` | 2 | ✅ |
| `owned_pension` | multi-enum | `NPS` `RETIREMENT_DB` `RETIREMENT_DC` `IRP` `PENSION_SAVING` `PENSION_INSURANCE` `NONE` | 2 | ✅ |
| `household` | enum | `SINGLE` `COUPLE` `COUPLE_WITH_CHILD` | 2 | ⬜ |

### 2-2. 선택 엔티티 (정밀도 향상)

| 엔티티 | 타입 | 값 | 용도 |
| --- | --- | --- | --- |
| `birth_year` | integer | 1940~2010 | 수급 개시 연령 정확 판정 |
| `contribution_years` | integer | 0~45 | 국민연금 추정 정밀화 |
| `employment_type` | enum | `EMPLOYEE` `SELF_EMPLOYED` `FREELANCER` `HOMEMAKER` `RETIRED` | 세그먼트 분기 |
| `target_monthly` | integer | 원 단위 | 고객 지정 목표 생활비 |
| `preferred_premium` | integer | 원 단위 | 희망 월 납입액 |
| `existing_pension_annual` | integer | 원 단위 | 기존 연금저축 납입액 (한도 잔여 계산) |
| `has_irp` | boolean | — | 합산 한도 계산 |
| `gender` | enum | `MALE` `FEMALE` | 기대여명 적용 |

### 2-3. 상태 엔티티 (대화 제어)

| 엔티티 | 타입 | 용도 |
| --- | --- | --- |
| `stage` | integer 1~5 | 현재 퍼널 단계 |
| `rejection_count` | integer | 거절 횟수. **2 이상이면 권유 중단** (FB-015) |
| `fallback_count` | integer | 의도 파악 실패 횟수. 3이면 이관 |
| `disclosures_shown` | string[] | 이미 노출한 고지 ID |
| `consent_contact` | boolean | 연락처 수집 동의 |
| `consent_marketing` | boolean | 마케팅 수신 동의 (**분리 저장 필수**) |
| `segment` | enum | 판정된 고객 세그먼트 |

### 2-4. 수집 금지 엔티티 ⛔

| 항목 | 사유 |
| --- | --- |
| 주민등록번호 | 챗봇 단계에서 불필요 |
| 질병 이력·복용 약물 | 민감정보 (개인정보 보호법 제23조) |
| 장애 여부·등급 | 민감정보 |
| 계좌번호·카드번호 | 결제는 정식 청약 절차에서만 |
| 타인의 개인정보 | 본인 동의 없는 수집 불가 |

---

## 3. 세그먼트 판정 규칙

```
if age < 30:                          → YOUNG_STARTER
elif employment_type == HOMEMAKER:    → NO_INCOME_SPOUSE
elif employment_type in (SELF_EMPLOYED, FREELANCER):
                                      → SELF_EMPLOYED
elif age >= 55:                       → PRE_RETIREE
else:                                 → MIDLIFE_EARNER
```

> ⚠️ `NO_INCOME_SPOUSE` 판정 시 **세제적격 상품 권유를 차단**한다.
> 소득이 없으면 세액공제 효과가 없어 적합성 원칙 위반이 된다.

---

## 4. 폴백 정책

| 실패 횟수 | 동작 |
| --- | --- |
| 1회 | 질문 재구성 + 버튼 선택지 3개 제공 |
| 2회 | 자주 묻는 질문 카드 노출 |
| 3회 | `handoff_to_agent` 호출 |

| 무응답 | 동작 |
| --- | --- |
| 60초 | 넛지 1회 — "계산 결과만 먼저 보여드릴까요?" |
| 180초 | 대화 요약 발송 후 세션 종료 |

> 넛지는 **세션당 1회만** 발송한다. 반복 넛지는 압박으로 인식된다.

---

## 5. 인텐트 학습 데이터 규모 목표

| 구분 | 인텐트당 발화 수 | 총계 |
| --- | --- | --- |
| 핵심 인텐트 (22종) | 25~30 | 약 600 |
| 안전 인텐트 (6종) | 30~40 | 약 200 |
| **합계** | | **약 800** |

수집 방법: 실제 콜센터 로그 라벨링 → LLM 증강 → 사람 검수 순으로 확보한다.
안전 인텐트는 재현율(recall)이 중요하므로 발화 수를 더 많이 확보한다.
