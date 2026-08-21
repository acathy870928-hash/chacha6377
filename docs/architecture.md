# Vertical AI Platform Architecture

> 두 개의 아키텍처 문서가 존재합니다. **같은 시스템의 서로 다른 뷰**이며, 이 문서가 둘을 하나로 잇습니다.
>
> - **전략 아키텍처 (6계층)** — 회사·대외용. 무엇을 만드는가.
> - **구축 아키텍처 (L1~L5)** — 벨루가 To-Be 요구사항. 어떻게 만드는가.

---

## 1. 전략 아키텍처 — 6계층

```
[6] Client Layer          보험소비자 · FA · GA · Enterprise · 보험회사
        ↑
[5] AI Service Layer      AI Link (Gateway / Customer Access)
        ↑
[4] Insurance Vertical Agentic AI
                          Multi-Agent · Workflow · Planning · Reasoning · Automation · Execution
        ↑
[3] Specialized AI Layer  Insurance Domain(Protection AI) | Assurance Domain(Lifetime Financial Planning AI)
        ↑
[2] Insurance Intelligence Layer  ★ Core Intelligence (공통 지능)
                          보험지식 · 보험법령 · 보험상품 · 보험약관 · 보험실무 · 보험 의사결정 엔진
        ↑
[1] Data Layer            Micky · Veluga · My · Cloud · External MCP
```

> 클라우드 플랫폼(AWS·Azure·GCP)의 계층 구조와 유사한 형태로,
> **데이터 → 공통 지능 → 전문 AI → 에이전트 → 서비스 → 사용자**의 흐름을 보여줍니다.
> 새로운 보험 AI 서비스가 추가되어도 **Specialized AI Layer만 확장**하면 되는 확장 가능한 구조입니다.

### [1] Data Layer

| 데이터 | 내용 | 상태 |
| --- | --- | --- |
| **Micky DATA** | 보험이론, 재무학, 금융법령, 정부기관·보험회사·연구기관 자료 등 보험산업 전문지식 | 연결됨 |
| **BumE_F DATA** | 사내 제도·행사·교육 및 FA 세일즈 자료 (ORCA Ai 전용) | 연결됨 |
| **BumE_C DATA** | 아이에프에이 고객에게 필요한 데이터 (Ai Link 전용) | 연결됨 |
| **External MCP** | 법령, 공공데이터, 제휴 데이터 | 수시 추가 |
| **Veluga DATA** | 보험상품, 보험약관, 상품방법서, 상품해설서 | **10/1 연결 예정** |
| **Cloud DATA** | 보험가입 내역, 유지 내역, 민원 내역, 수수료 내역, 상담 이력 등 AI·Cloud 운영 데이터 | 이후 단계 |
| **My DATA** | 건강검진·유전자 분석·타사 보험가입·금융상품 데이터 (전송요구권 기반) | 다음 단계 |

### [2] Insurance Intelligence Layer — Core Intelligence

모든 서비스가 공유하는 **하나의 공통 지능**. 개별 AI를 각각 만드는 구조가 아닙니다.
보험지식 · 보험법령 · 보험상품 · 보험약관 · 보험실무 · 보험 의사결정 엔진.

### [3] Specialized AI Layer — If / When 축으로 분화

| 도메인 | 성격 | 서비스 |
| --- | --- | --- |
| **Insurance Domain** (Protection AI) — *If* | 발생 여부가 불확실한 위험 | **MediCode** — 건강검진·유전자 분석 데이터 기반 AI 보장설계 (개인별 위험분석 · 보장 최적화 · 가입 및 유지관리) |
| **Assurance Domain** (Lifetime Financial Planning AI) — *When* | 반드시 오지만 시기를 모르는 미래 | **VFA** — 변액보험·변액연금 수익률 관리 (펀드 관리·리밸런싱·수익률 최적화)<br>**HopePlan** — AI 기반 은퇴·연금 설계 (은퇴소득 설계·절세 전략·연금 최적화)<br>**Legacy Plan** — AI 기반 상속·자산승계 설계 (상속·증여 전략·가족 자산 이전) |

### [4] Insurance Vertical Agentic AI
Multi-Agent · Workflow · Planning · Reasoning · Automation · Execution

### [5] AI Service Layer
**AI Link** — 보험소비자가 Insurance Vertical AI에 접근하는 AI Gateway.
고객은 AI Link를 통해 언제 어디서나 보험전문가 수준의 AI 서비스를 이용할 수 있습니다.

> ⚠️ 전략 아키텍처 원문에는 **FA 접점(ORCA Ai)이 명시되어 있지 않습니다.**
> 실제로는 이 계층에 고객용 AI Link와 FA용 ORCA Ai 두 개의 게이트웨이가 존재합니다.
> → [정합성 점검 #2](alignment-check.md)

### [6] Client Layer
Insurance Consumer · Financial Advisor · GA · Enterprise · Insurance Company

---

## 2. 구축 아키텍처 — 벨루가 To-Be (L1~L5)

**핵심 키워드**
하이브리드 오케스트레이션 | 상품 에이전트(보험 상품 약관 집중) | 결정론적 상태머신 기반 워크플로우 |
가드레일 내장 Tool Calling | Vision PDF 파이프라인

| 레이어 | 내용 | 이번 차수 |
| --- | --- | --- |
| **L1 API Gateway** | 멀티채널 단일 수신, 테넌트 격리, 인증·인가 | 2주 |
| **L2 마스터 오케스트레이터** | 2-Tier 하이브리드 의도분류(Rule→LLM, **SLM 제외**), 동적 에이전트 라우팅, 컨텍스트 관리, 모드 전환 판단 | 5~6주 |
| **L3 멀티 도메인 에이전트** | 도메인별 독립 에이전트, **가드레일 내장 Tool Calling**, 설정 기반 확장 | 11~16주 |
| **L4 모드 전환** | 대화 ↔ 워크플로우 실시간 전환, 결정론적 상태머신 + LLM 보조 | — |
| **L5 공유 인프라** | Stateful 상태관리, 지식베이스(**Vision PDF + GraphRAG + 하이브리드 검색**), Structured Trace Log·모니터링 | 3~4주차, 9~14주차 |
| 관리 콘솔 | 에이전트 프로필 GUI, 지식베이스 연결 관리, 실시간 모니터링 | 21~22주차 |
| 기존 시스템 연동 | **상품DB 우선**, 벤더 중립 Skill/MCP 거버넌스 허브 | 17~20주차 |

**규모** 4~5명 투입 · 6개월 · 6.5~7억원 예상

### 에이전트 범위

| 에이전트 | 이번 차수 | 지식소스 |
| --- | --- | --- |
| **상품 에이전트** | ★ **핵심 집중 범위** | 보험 상품 약관/안내서 RAG (Vision PDF, GraphRAG 집중) |
| 계약 에이전트 | 단계적 진행 | 계약 문서 RAG (향후) |
| 수수료 에이전트 | 단계적 진행 | 수수료 규정 RAG (향후) |
| FA 교육 에이전트 | 단계적 진행 | 교육자료 RAG (향후) |

### 벨루가 제안 주요 조정

| 구분 | iFA 원본 요청 | 벨루가 제안 | 사유 |
| --- | --- | --- | --- |
| L2 의도분류 | 순수 LLM | 2-Tier 하이브리드(Rule→LLM) | 단문 모호성, 지연 누적 방지, SLM 제외로 단순화 |
| L3 범위 | 멀티 도메인 동시 자율 구동 | **상품 약관 집중** | 핵심 범위 지정, 타 에이전트는 단계적 확장 |
| L3 Tool Calling | 자율 | 가드레일 + 호출 전 검증 | **보험/금융 도메인 오류 시 법적 리스크 방지** |
| L4 모드 전환 | LLM 판단 | 결정론적 상태머신 + LLM 보조 | 전환 오감지 차단, 상태 복원 신뢰성 |
| L5 지식베이스 | 시맨틱 청킹 + 하이브리드 검색 | Vision PDF + GraphRAG + FiD | 약관 레이아웃 복잡도, **약관 내 교차참조 분석** |
| A2 연동 | API/Skill/MCP | Skill/MCP 거버넌스 허브(벤더 중립) | 상품DB 우선, 타 DB 단계적 |

> **전환의 핵심 의의**
> 개별 AI를 각각 만드는 비효율을 제거하고, 하나의 견고한 플랫폼 아키텍처 위에서
> 상품 약관 구축을 시작으로 N개의 에이전트를 확장해 나가는 플랫폼 패러다임 전환.

---

## 3. ★ 두 아키텍처의 매핑

**이 표가 이번 정리의 핵심입니다.** 전략 문서와 구축 요구사항이 같은 그림임을 증명합니다.

| 전략 아키텍처 (6계층) | 구축 아키텍처 (벨루가) | 대응 관계 |
| --- | --- | --- |
| [6] Client Layer | **L1** 멀티채널 수신 · 테넌트 격리 | 설계사 앱/고객 앱/웹 포털 = FA·고객·GA 채널 |
| [5] AI Service Layer (AI Link, ORCA Ai) | **L1** API Gateway | 게이트웨이가 곧 서비스 접점. **채널별 테넌트 = ORCA Ai / Ai Link 분리** |
| [4] Agentic AI Layer | **L2** 오케스트레이터 + **L4** 모드 전환 | Planning·Reasoning = 의도분류·라우팅, Workflow·Execution = 대화↔워크플로우 전환 |
| [3] Specialized AI Layer | **L3** 멀티 도메인 에이전트 | **여기서 이름이 어긋납니다** — 아래 주의 참조 |
| [2] Insurance Intelligence (Core) | **L3 가드레일** + **L5** 지식베이스·상태관리 | 공통 지능 = 약관/법령 지식 + 도메인 가드레일 |
| [1] Data Layer | **L5** 지식베이스 + **A2** 기존 시스템 연동 | Veluga DATA=상품DB·약관 RAG, Cloud DATA=계약·수수료DB, External MCP=Skill/MCP 허브 |

### ⚠️ 주의 — [3]과 L3은 같은 것이 아닙니다

이름이 비슷해 혼동하기 쉬우나 **분류 축이 다릅니다.**

| | 분류 축 | 구성 |
| --- | --- | --- |
| 전략 [3] Specialized AI | **고객 가치**(If/When) | MediCode · VFA · HopePlan · Legacy Plan |
| 구축 L3 에이전트 | **사내 업무 도메인** | 상품 · 계약 · 수수료 · FA 교육 |

두 축은 배타적이지 않고 **직교(orthogonal)** 합니다.
예: MediCode(전략 [3])는 상품 에이전트 + 계약 에이전트(구축 L3)를 함께 호출해 동작합니다.

→ **결정 필요**: 두 축의 관계를 문서상 어떻게 명시할지. [정합성 점검 #1](alignment-check.md)

### 이번 차수(6개월)가 커버하는 범위

```
[6] Client      ████████████ L1 (채널 수신)
[5] AI Service  ████████████ L1 (Gateway)
[4] Agentic     ████████░░░░ L2·L4 (상품 라우팅 우선 검증)
[3] Specialized ██░░░░░░░░░░ L3 상품 에이전트만 — MediCode/VFA/HopePlan/Legacy Plan은 범위 밖
[2] Core Intel  ████████████ L3 가드레일 + L5 지식베이스 ★ 이번 차수 핵심
[1] Data        ████░░░░░░░░ 상품DB(Veluga)만 — Cloud·My DATA는 향후
```

> **읽는 법**: 이번 6개월은 **[2] Core Intelligence를 세우는 공사**입니다.
> 전략 문서가 말하는 6개 서비스가 이번에 만들어지는 것이 아니라,
> 그 서비스들이 올라탈 **공통 지능의 기준(약관 RAG + 가드레일)** 을 잡는 차수입니다.
> 대외 커뮤니케이션에서 이 둘을 구분하지 않으면 과약속(over-promise)이 됩니다.
