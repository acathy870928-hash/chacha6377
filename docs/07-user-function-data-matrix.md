# 07. User · Function · Data Matrix

**누가 사용하는가 / 어떤 기능을 쓰는가 / 누가 어떤 데이터를 사용하는가**

> 📌 **표기 안내**
> - 원문(Vision 문서)에 **명시된 것** : 사용자 유형(Client Layer), 서비스와 세부 기능(Specialized AI Layer), 데이터 종류(Data Layer), 보험 여정 7단계
> - 원문에 **명시되지 않아 도출한 것** : 사용자 ↔ 기능, 사용자 ↔ 데이터의 연결 관계
>   → 아래 매트릭스의 매핑은 아키텍처 구조에 근거한 **해석**이며, 실제 정책·권한 설계 시 확정이 필요합니다.

---

## 1. 누가 사용하는가 (Who Uses)

Client Layer의 5개 사용자 유형입니다.

| # | 사용자 | 구분 | 무엇을 얻는가 | 대응 핵심가치 |
|---|--------|------|---------------|---------------|
| 1 | **Insurance Consumer**<br>보험소비자 | B2C | 보험전문가 수준의 분석·비교·추천과 평생 관리 | 전문성의 민주화 |
| 2 | **Financial Advisor**<br>보험설계사 | B2B2C | 전문성과 생산성의 증강, 설계 품질의 표준화 | 전문성 증강 |
| 3 | **GA**<br>법인보험대리점 | B2B | 소속 조직의 설계 품질·계약 관리 표준화 | 전문성 증강 |
| 4 | **Enterprise**<br>기업 | B2B | Enterprise License·White Label·API로 AI 내재화 | 가치 증강 |
| 5 | **Insurance Company**<br>보험회사 | B2B | 상품 노출·판매 채널·데이터 기반 인사이트 | 가치 증강 |

**공통 접점** — 5개 사용자 유형 모두 **AI Link**(AI Gateway)를 통해 Insurance Vertical AI™에 접근합니다.
Enterprise와 Insurance Company는 추가로 **MCP/API** 경로를 사용합니다.

---

## 2. 어떤 기능을 사용하는가 (What Functions)

### 2-1. 기능 전체 목록

| 계층 | 기능 단위 | 세부 기능 |
|------|-----------|-----------|
| **Core Intelligence** | Insurance Vertical AI™ | 보험 지식 · 보험법령 · 보험상품 · 보험약관 · 보험 실무 · 보험 의사결정 엔진 |
| **Specialized (Protection)** | **MediCode** | 개인별 위험 분석 · 보장 최적화 · 보험 가입 및 유지관리 |
| **Specialized (Assurance)** | **VFA** | 펀드 관리 · 리밸런싱 · 수익률 최적화 |
| **Specialized (Assurance)** | **HopePlan** | 은퇴소득 설계 · 절세 전략 · 연금 최적화 |
| **Specialized (Assurance)** | **Legacy Plan** | 상속 전략 · 증여 전략 · 가족 자산 이전 계획 |
| **Agentic AI** | Insurance Vertical Agentic AI | Multi-Agent · Workflow · Planning · Reasoning · Automation · Execution |
| **Service** | **AI Link** | Gateway · Customer Access |

### 2-2. 사용자 × 기능 매트릭스

◎ 주 사용자 / ○ 사용 / △ 제한적·간접 사용 / – 해당 없음

| 기능 | Consumer | Advisor | GA | Enterprise | Insurance Co. |
|------|:--------:|:-------:|:--:|:----------:|:-------------:|
| **AI Link** (접근 경로) | ◎ | ○ | ○ | ○ | ○ |
| **Insurance Vertical AI™** (지식·약관·법령 질의) | ◎ | ◎ | ○ | ○ | ○ |
| **MediCode** (보장 설계) | ◎ | ◎ | ○ | △ | △ |
| **VFA** (변액 수익률 관리) | ◎ | ◎ | ○ | △ | △ |
| **HopePlan** (은퇴·연금 설계) | ◎ | ◎ | ○ | △ | △ |
| **Legacy Plan** (상속·자산승계) | ◎ | ◎ | ○ | △ | △ |
| **Agentic AI** (자동 실행) | ◎ | ◎ | ○ | ○ | △ |
| **MCP / API · White Label** | – | △ | ○ | ◎ | ◎ |
| **운영·성과 분석** (계약·유지·민원·수수료) | △<br>*(본인 계약)* | ○<br>*(본인 실적)* | ◎ | ○ | ◎ |

### 2-3. 보험 여정 7단계 × 담당 기능

Agentic AI가 고객의 보험 여정 전체를 지원합니다.

| # | 여정 단계 | 주 담당 기능 | 주 사용자 |
|---|-----------|--------------|-----------|
| 1 | 보험 분석 | Insurance Vertical AI™ + MediCode | Consumer, Advisor |
| 2 | 보험 비교 | Insurance Vertical AI™ (Veluga 기반) | Consumer, Advisor |
| 3 | 보험 추천 | 보험 의사결정 엔진 + MediCode | Consumer, Advisor |
| 4 | 보험 가입 지원 | Agentic AI (Workflow · Execution) | Consumer, Advisor, GA |
| 5 | 계약 유지관리 | Agentic AI + MediCode | Advisor, GA, Consumer |
| 6 | 연금 관리 | VFA + HopePlan | Consumer, Advisor |
| 7 | 상속 계획 | Legacy Plan | Consumer, Advisor |

---

## 3. 누가 어떤 데이터를 사용하는가 (Who Uses What Data)

### 3-1. 데이터 5종 요약

| 데이터 | 성격 | 주요 내용 | 소유·출처 |
|--------|------|-----------|-----------|
| **Micky DATA** | 전문지식 | 보험이론, 재무학, 금융법령, 정부기관·보험회사·연구기관 자료 | 공개·수집 지식 |
| **Veluga DATA** | 상품 | 보험상품, 보험약관, 상품방법서, 상품해설서 | 보험회사 |
| **My DATA** | 개인 (민감) | 건강검진 데이터, 유전자 분석 데이터, 보험가입 데이터, 금융상품 데이터 | **고객 본인** |
| **Cloud DATA** | 운영 | 보험가입·유지·민원·수수료 내역, 상담 이력 | 플랫폼 운영 |
| **External MCP** | 외부 연동 | 법령, 공공데이터, 제휴 데이터 | 외부 기관 |

### 3-2. 사용자 × 데이터 매트릭스

| 사용자 | Micky DATA | Veluga DATA | My DATA | Cloud DATA | External MCP |
|--------|:----------:|:-----------:|:-------:|:----------:|:------------:|
| **Insurance Consumer** | ○<br>결과로 활용 | ○<br>비교·추천 결과 | **◎ 데이터 주체**<br>본인 데이터 제공·조회 | △<br>본인 계약·상담 이력 | △<br>결과로 활용 |
| **Financial Advisor** | ◎<br>지식 조회 | ◎<br>설계·비교 | ○<br>**고객 동의 범위 내** | ○<br>본인 계약·수수료·상담 | ○ |
| **GA** | ○ | ◎<br>상품 운영 | △<br>**동의·권한 범위 내 집계** | ◎<br>조직 계약·유지·민원·수수료 | ○ |
| **Enterprise** | ○ | ○<br>API 연동 | –<br>*원칙적 비접근* | ○<br>계약 범위 내 | ◎<br>제휴 연동 |
| **Insurance Company** | ○ | ◎<br>자사 상품 등록·갱신 | –<br>*원칙적 비접근* | ◎<br>판매·유지·민원 통계 | ○ |

◎ 주 사용 / ○ 사용 / △ 제한적 사용 / – 비접근

### 3-3. 데이터 × 기능 매트릭스

각 기능이 어떤 데이터를 근거로 동작하는지의 관계입니다.

| 기능 | Micky | Veluga | My | Cloud | MCP |
|------|:-----:|:------:|:--:|:-----:|:---:|
| **Insurance Vertical AI™** (Core) | ◎ | ◎ | ○ | ○ | ◎ |
| **MediCode** (보장 설계) | ○ | ◎ | ◎<br>건강검진·유전자 | ○ | ○ |
| **VFA** (변액 수익률) | ○ | ◎<br>펀드·상품 | ◎<br>금융상품 | ○ | ○ |
| **HopePlan** (은퇴·연금) | ◎<br>재무학·세제 | ○ | ◎<br>가입·금융자산 | ○ | ◎<br>법령·공공 |
| **Legacy Plan** (상속·승계) | ◎<br>법령·세제 | ○ | ◎<br>자산 현황 | ○ | ◎<br>법령 |
| **Agentic AI** | ○ | ○ | ◎ | ◎ | ○ |
| **AI Link** | – | – | △<br>인증·전달 | ◎<br>상담 이력 | – |

---

## 4. 한 장 요약 (One-Page Summary)

```
[누가]                    [어떤 기능]                        [어떤 데이터]

Insurance Consumer  ──┐                                  ┌── My DATA (본인, 민감)
Financial Advisor   ──┤                                  │
GA                  ──┼── AI Link ── Agentic AI ──┐      ├── Veluga DATA (상품·약관)
Enterprise          ──┤   (Gateway)                │      │
Insurance Company   ──┘                            │      ├── Micky DATA (전문지식)
                                                   │      │
                        MediCode / VFA /           │      ├── Cloud DATA (운영)
                        HopePlan / Legacy Plan ────┤      │
                                                   │      └── External MCP (법령·공공)
                        Insurance Vertical AI™ ────┘
                        (Core Intelligence)              모든 기능이 5종 데이터를
                                                          공통 지능 위에서 활용
```

**핵심 요약 3줄**

1. **누가** — 보험소비자·설계사·GA·기업·보험회사 5개 유형이 모두 **AI Link** 하나의 관문으로 접근한다.
2. **어떤 기능** — 하나의 **공통 지능**(Insurance Vertical AI™) 위에 4개 전문 AI(MediCode·VFA·HopePlan·Legacy Plan)와 Agentic AI가 얹혀 보험 여정 7단계를 담당한다.
3. **어떤 데이터** — 5종 데이터 중 **My DATA만이 고객 소유의 민감정보**이며, 나머지는 지식·상품·운영·외부 데이터로 전 기능이 공유한다.

---

## 5. 후속 확정이 필요한 항목

이 매트릭스는 구조로부터 도출한 것으로, 다음은 별도 정책 설계가 필요합니다.

- **My DATA 접근 권한** — 건강검진·유전자 데이터는 민감정보로, 설계사·GA의 열람 범위와 고객 동의 절차 정의 필요
- **Cloud DATA 열람 범위** — 설계사 본인 실적 / GA 조직 단위 / 보험회사 통계 단위의 경계 정의 필요
- **Enterprise·Insurance Company의 My DATA 비접근 원칙** — 익명화·집계 데이터 제공 여부 결정 필요
- **역할별 권한 모델(RBAC)** — 위 매트릭스의 ◎/○/△를 실제 권한 정책으로 전환
