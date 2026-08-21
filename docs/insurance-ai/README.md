# insurance AI — 제품 스펙

> **insurance AI**는 아이에프에이(iFA AI & Co.)의 **자회사**로 신설되는 독립 사업체입니다.
> 모회사의 2년간 운영 경험과 데이터 생태계를 기술 기반으로 삼되, 브랜드와 사업은 독립적으로 운영합니다.

| 문서 | 답하는 질문 |
| --- | --- |
| [`definition.md`](definition.md) | **무엇인가** — 정의, 사업 구조, 위치, 역할, 표기 |
| [`personas.md`](personas.md) | **누가 답하는가** — insurance AI + 전문 페르소나 4인 |
| [`guidelines.md`](guidelines.md) | **어떻게 행동하는가** — 운영 지침 7장 |
| [`layers.md`](layers.md) | **어떤 구조 위에서 동작하는가** — 6레이어 구성과 처리 흐름 |
| [`../prompt/insurance-ai.system.md`](../prompt/insurance-ai.system.md) | **배포물** — 시스템 프롬프트 |

---

## 확정 사항 (2026-08-21)

| # | 항목 | 결정 |
| --- | --- | --- |
| 1 | 사업 형태 | **아이에프에이의 자회사** — 신설 법인으로 출범 |
| 2 | 채널 | **신규 독립 앱/웹** (기존 Ai Link 탑재 아님) |
| 3 | 사업 대상 | **B2C + B2B** — 일반 소비자 직접 서비스 + 보험사·GA 공급 |
| 4 | 표기 | **insurance AI** (소문자 insurance + 대문자 AI) |
| 5 | 두뇌 | 벨루가 6개월 구축(상품 에이전트 + 약관 RAG + 오케스트레이터) |
| 6 | 전문 서비스 | **독립된 4개 페르소나** — MediCode · VFA · HopePlan · Legacy Plan<br>*페르소나 수준까지만 정의, 개별 프롬프트 없음* |
| 7 | 연결 방식 | insurance AI가 관문 겸 안내자로 **전문 페르소나에 인계** |
| 8 | 질병예측 | 「AI 질병예측」은 별도 서비스로 두지 않음. **MediCode로 단일화** |
| 9 | 아이에프에이 관계 | **자회사로 명시** — 모회사의 기술·데이터 기반 위에서 출발 |
| 10 | ORCA Ai / Ai Link | **내부 서비스** — insurance AI 문서에서 다루지 않음 |

## 아이에프에이와의 관계

```
아이에프에이 (iFA AI & Co.) — 모회사
  ORCA Ai      FA 전용 업무 AI      ┐
  Ai Link      기존 고객 채널        ├ 내부 서비스 (이 폴더에서 다루지 않음)
  보험설계·계약관리 운영 자산        ┘
        │
        │  기술 · 데이터 · 2년간 운영 경험
        ▼
insurance AI — 자회사 ← 이 폴더
  독립 앱/웹 · B2C + B2B · 자체 브랜드
```

**표준 문장**
> insurance AI는 아이에프에이(iFA AI & Co.)의 자회사로,
> 2년간의 실제 보험설계·계약관리 운영 경험과 데이터 생태계 위에서 출발했습니다.

모회사의 내부 서비스(ORCA Ai·Ai Link)는 insurance AI의 제품 범위에 포함되지 않습니다.

## 상위 정본과의 관계

```
Manifesto · Charter        철학 (공통 — 계속 유효)
Glossary                   용어 (공통)
        │
        ▼
insurance-ai/              definition → personas → guidelines → layers
        │
        ▼
prompt/insurance-ai.system.md   배포
```
