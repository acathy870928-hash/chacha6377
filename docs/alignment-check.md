# 정합성 점검 (Alignment Check)

> 매니페스토 · 회사정의 · 아키텍처 · FA 안내문 · MediCode 용어 정의 · 벨루가 To-Be 요구사항.
> 여섯 자료를 겹쳐 놓고 **같은 것을 다르게 부르거나, 한쪽에만 있는 것**을 찾아 정리했습니다.
>
> 대부분은 자료가 **각각 다른 시점에 다른 목적으로** 만들어졌기 때문에 생긴 것이고,
> 지금 한 번 맞춰 두면 이후로는 어긋나지 않습니다.
> **결정이 필요한 항목**은 ⚑로 표시했습니다.

---

## #1 ⚑ Specialized AI Layer(전략 [3]) vs 멀티 도메인 에이전트(구축 L3)

이름이 거의 같은데 **분류 축이 다릅니다.**

| | 분류 축 | 구성 |
| --- | --- | --- |
| 전략 [3] Specialized AI | **고객 가치** (If / When) | MediCode · VFA · HopePlan · Legacy Plan |
| 구축 L3 에이전트 | **사내 업무 도메인** | 상품 · 계약 · 수수료 · FA 교육 |

읽는 사람은 "MediCode가 L3의 다섯 번째 에이전트인가?"라고 오해하게 됩니다.
실제로는 **직교(orthogonal)** 관계입니다 — MediCode 하나가 동작하려면 상품 에이전트와 계약
에이전트를 함께 호출합니다.

**제안**: 층 이름을 분리해 부릅니다.
- 전략 [3] → **Solution Layer** (고객이 사는 것)
- 구축 L3 → **Agent Layer** (시스템이 하는 일)

> **결정 사항**: 명칭을 분리할지, 아니면 현행 유지하고 매핑표로만 설명할지.

---

## #2 ⚑ ORCA Ai가 전략 아키텍처에 없다

전략 아키텍처 [5] AI Service Layer에는 **AI Link만** 기술되어 있습니다.
"보험소비자가 Insurance Vertical AI에 접근하는 AI Gateway."

그런데 실제로는 게이트웨이가 **둘**입니다.

```
[5] AI Service Layer
     ├─ Ai Link   → 고객   (Micky + BumE_C + Cloud)
     └─ ORCA Ai   → FA     (Micky + BumE_F + Cloud + External MCP)   ← 문서에 없음
```

FA는 [6] Client Layer에 "Financial Advisor"로 존재하는데, **FA가 접속할 문이 아키텍처에 없습니다.**
2년간 운영해 온 주력 서비스가 전략 문서에서 빠져 있는 상태입니다.

이는 벨루가 L1의 "**채널별 테넌트 격리**" 요구사항과 정확히 대응합니다 —
설계사 앱 / 고객 앱 = ORCA Ai / Ai Link 테넌트.

> **결정 사항**: 아키텍처 도식에 ORCA Ai를 추가할 것. (권장 — 사실 관계 수정)

---

## #3 데이터 명칭이 자료마다 다르다

| 데이터 | 전략 아키텍처 | FA 안내문 | 상태 |
| --- | --- | --- | --- |
| Micky | Micky DATA | Micky DATA | ✅ |
| Veluga | **Veluga** DATA | **VELUGA** DATA | ⚠️ 대소문자 |
| My | My DATA | My DATA (마이데이터) | ✅ |
| Cloud | Cloud DATA | Cloud DATA | ✅ |
| External MCP | External MCP | External MCP | ✅ |
| **BumE_F** | **없음** | BumE_F DATA (FA 세일즈·사내 제도) | ❌ 누락 |
| **BumE_C** | **없음** | BumE_C DATA (고객 필요 데이터) | ❌ 누락 |

BumE 계열 2종이 전략 문서 Data Layer에 없습니다. **현재 운영 중인 데이터**입니다.

**제안 표준 표기** — `Micky DATA` `Veluga DATA` `BumE_F DATA` `BumE_C DATA` `Cloud DATA` `My DATA` `External MCP`
(고유명사는 파스칼 표기, DATA는 대문자 유지)

---

## #4 ⚑ 「메디코드 보험설계」와 「AI 질병예측」이 나란히 있다

Ai Link 맞춤 분석 서비스 3종: 메디코드 보험설계 / VFA / **AI 질병예측**

그런데 메디코드의 표준 정의는 —
> 메디코드 보험설계는 **질병예측모형 기반의** AI 보험설계입니다.

고객 화면에서 두 메뉴가 나란히 보이면 "무엇이 다른가?"라는 질문이 생깁니다.

**해석 가능한 구조** (둘 중 하나로 정리 필요)
- **(A) 포함 관계** — AI 질병예측은 메디코드의 *분석 단계*. → 메디코드 안으로 흡수하고 단계로 표시
- **(B) 별개 서비스** — 질병예측은 *진단만*, 메디코드는 *설계까지*. → 이름을 구분되게 바꿔야 함
  (예: 「AI 질병예측 리포트」 vs 「메디코드 보험설계」)

> **결정 사항**: A인지 B인지. 현재는 고객이 판단할 근거가 없습니다.

---

## #5 If/When 정의가 두 버전 존재 — 새 버전이 훨씬 강합니다

| | 초기 정의 | **정교화된 정의 (회사정의 문서)** |
| --- | --- | --- |
| If | 질병, 사고, 예상하지 못한 위험 | **Insurance** — 발생 여부가 불확실한 위험 (**Contingent Risk**) |
| When | 은퇴, 장수 | **Assurance** — 반드시 발생하나 시기를 특정하기 어려운 미래 (**Eventual Risk**) |

**Insurance / Assurance 구분은 이 회사가 가진 가장 강한 개념 자산입니다.**
- 감성적 수사가 아니라 **보험학적으로 정확한 분류**입니다
- 그리고 이 분류가 그대로 **조직·제품 구조**가 됩니다
  → Insurance Domain(Protection AI: MediCode) / Assurance Domain(VFA·HopePlan·Legacy Plan)
- 즉 **철학 한 문장이 아키텍처를 결정**하는 드문 구조입니다. 이런 정합성은 흔치 않습니다.

**조치 완료**: [Company](company.md) 7항, [Glossary](glossary.md), [Architecture](architecture.md)에 반영.
**조치 필요**: 매니페스토·페르소나·광고 카피는 아직 초기 정의를 씁니다. 상향 반영 여부 판단 필요.

> **결정 사항**: 고객 대면 카피에도 Insurance/Assurance 용어를 쓸 것인지,
> 고객에게는 '만약/언젠가'로만 말하고 전문가·IR 문맥에서만 쓸 것인지.
> (권장: 후자 — 고객에게 Contingent/Eventual Risk는 어렵습니다)

---

## #6 회사·서비스 표기 정본이 없다

같은 문서 안에서도 표기가 흔들립니다.

| 대상 | 발견된 표기 | 제안 표준 |
| --- | --- | --- |
| 회사 (영문) | iFA AI & Co. / FA AI & Co.(오타) / iFA | **iFA AI & Co.** |
| 회사 (국문) | 아이에프에이 | **아이에프에이** |
| 조직 | iFA AX팀 | **iFA AX팀** |
| 플랫폼 | iFA 클라우드 / AI·Cloud | **iFA 클라우드** |
| FA용 AI | ORCA Ai | **ORCA Ai** |
| 고객용 AI | Ai Link / AI Link | ⚑ **택일 필요** |

⚑ **Ai Link vs AI Link** — FA 안내문은 `Ai Link`, 아키텍처 문서는 `AI Link`.
서비스명이므로 하나로 고정해야 합니다. (권장: 실제 서비스 화면 표기를 따름)

---

## #7 페르소나 이름과 서비스 이름이 다르다

앞서 정의한 페르소나와 실제 서비스의 대응입니다.

| 페르소나 문서 | 실제 서비스 | 대상 |
| --- | --- | --- |
| [iFA AI](persona/ifa-ai.md) | **ORCA Ai** | FA |
| [Insurance AI](persona/insurance-ai.md) | **Ai Link** 챗봇 | 고객 |

혼선 소지: `iFA AI`는 ①회사(iFA AI & Co.) ②페르소나 ③전체 AI의 총칭으로 **세 가지 뜻**으로 쓰입니다.

> **결정 사항**: 페르소나 명칭을 서비스명(ORCA Ai / Ai Link)으로 통일할지,
> 내부 페르소나 명칭을 별도로 유지할지.
> (권장: 서비스명으로 통일 — 사용자가 만나는 이름과 AI가 자기를 부르는 이름이 같아야 합니다)

---

## #8 MediCode가 세 층위에서 쓰인다 — 정리 완료

| 층위 | 명칭 | 쓰는 곳 |
| --- | --- | --- |
| 전략 [3] 서비스 | **MediCode** | 아키텍처, 서비스 라인업 |
| 방법론 (내부) | **MediCode Insurance Methodology (MIM™)** | 기술 문서, 특허, AI 학습 |
| 서비스 (대외) | **메디코드 보험설계 / MediCode Insurance Design** | 홈페이지, 상담, 광고 |
| 엔진 | **MediCode AI** | 기술 실체 |

→ [Glossary](glossary.md)에 4층 관계로 정리 완료. 추가 결정 불필요.

---

## #9 ⚑ HopePlan · Legacy Plan의 현재 상태가 불명확

전략 문서 Specialized AI Layer에는 4개 서비스가 있습니다: MediCode · VFA · HopePlan · Legacy Plan.
그런데 Ai Link 실제 서비스 목록에는 —

| 서비스 | Ai Link 현황 |
| --- | --- |
| MediCode | ✅ 「메디코드 보험설계」 |
| VFA | ✅ 「변액보험 펀드 추천(VFA)」 |
| HopePlan | ❓ 「연금 계산기」만 존재 |
| Legacy Plan | ❓ 「상속증여 계산기」만 존재 |

계산기가 곧 HopePlan/Legacy Plan인지, 아니면 이들은 아직 **로드맵**인지 구분되지 않습니다.

> **결정 사항**: 대외 자료에서 4개를 나란히 놓을 때 **현재 제공 / 개발 중**을 구분 표기할지.
> (구분하지 않으면 과약속 리스크. 특히 IR·제안서)

---

## #10 ⚑ 구축 범위와 대외 메시지 사이의 간격

벨루가 6개월 차수의 실제 범위:

```
★ 상품 에이전트(보험 약관)만 집중 구축
  타 에이전트(계약·수수료·교육)는 "플랫폼 방향성 기반 단계적 진행"
  상품DB 우선 연동, 타 DB는 향후
  4~5명 / 6개월 / 6.5~7억
```

전략 문서가 말하는 것: 6계층 플랫폼, 4개 Specialized AI, Agentic AI, 7단계 고객 여정.

**둘 다 사실이지만 시점이 다릅니다.** 이번 차수는 [2] Core Intelligence를 세우는 공사이고,
그 위의 서비스들은 그 다음입니다.

> **결정 사항**: 대외 자료에 **Today / Tomorrow / Future** 구분을 명시적으로 표기할 것.
> Roadmap 3단계가 이미 있으므로, 각 서비스·기능을 이 3단계에 배치하기만 하면 됩니다.
> (권장: 홈페이지·제안서에 "현재 제공 중" 배지를 다는 방식)

---

## 결정 요청 항목 요약

| # | 항목 | 권장안 | 영향 범위 |
| --- | --- | --- | --- |
| 1 | Specialized AI vs Agent 층 명칭 | Solution Layer / Agent Layer로 분리 | 아키텍처 도식, 제안서 |
| 2 | ORCA Ai를 아키텍처에 추가 | 추가 (사실 관계) | 아키텍처 도식 |
| 4 | 메디코드 ↔ AI 질병예측 관계 | 포함(A) 또는 분리(B) 택일 | Ai Link 메뉴, 카피 |
| 5 | Insurance/Assurance 용어 노출 범위 | 전문가·IR만, 고객은 만약/언젠가 | 카피, 페르소나 |
| 6 | `Ai Link` vs `AI Link` | 서비스 화면 표기로 고정 | 전 자료 |
| 7 | 페르소나 명칭 ↔ 서비스명 | 서비스명으로 통일 | 페르소나 문서, 시스템 프롬프트 |
| 9 | HopePlan·Legacy Plan 현황 표기 | 현재 제공/개발 중 구분 | IR, 제안서, 홈페이지 |
| 10 | Today/Tomorrow/Future 배지 | 명시 표기 | 홈페이지, 제안서 |

이 8가지가 정해지면 남은 문서는 기계적으로 정렬됩니다.
결정해 주시면 전 문서에 일괄 반영하겠습니다.
