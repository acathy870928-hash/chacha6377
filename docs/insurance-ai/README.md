# iNSURANCE AI — 제품 스펙

> **iNSURANCE AI**는 신설 사업자로 출범하는 독립 브랜드입니다.
> 아이에프에이의 2년간 운영 경험과 데이터 생태계 위에서 출발하지만, 사업체와 브랜드는 별개입니다.

| 문서 | 답하는 질문 |
| --- | --- |
| [`definition.md`](definition.md) | **무엇인가** — 정의, 사업 구조, 위치, 역할, 표기 |
| [`personas.md`](personas.md) | **누가 답하는가** — iNSURANCE AI + 전문 페르소나 4인 |
| [`guidelines.md`](guidelines.md) | **어떻게 행동하는가** — 운영 지침 7장 |
| [`layers.md`](layers.md) | **어떤 구조 위에서 동작하는가** — 6레이어 구성과 처리 흐름 |
| [`../prompt/insurance-ai.system.md`](../prompt/insurance-ai.system.md) | **배포물** — 시스템 프롬프트 |

---

## 확정 사항 (2026-08-21)

| # | 항목 | 결정 |
| --- | --- | --- |
| 1 | 사업 형태 | **신설 사업자** — 독립 법인으로 출범 |
| 2 | 채널 | **신규 독립 앱/웹** (기존 Ai Link 탑재 아님) |
| 3 | 사업 대상 | **B2C + B2B** — 일반 소비자 직접 서비스 + 보험사·GA 공급 |
| 4 | 표기 | **iNSURANCE AI** (소문자 i + 대문자, iFA 모티프 계승) |
| 5 | 두뇌 | 벨루가 6개월 구축(상품 에이전트 + 약관 RAG + 오케스트레이터) |
| 6 | 전문 서비스 | **독립된 4개 페르소나** — MediCode · VFA · HopePlan · Legacy Plan |
| 7 | 연결 방식 | iNSURANCE AI가 관문 겸 안내자로 **전문 페르소나에 인계** |
| 8 | 질병예측 | 「AI 질병예측」은 별도 서비스로 두지 않음. **MediCode로 단일화** |
| 9 | 아이에프에이 관계 | **기술 기반으로만 언급** — 모회사·자회사 관계는 서술하지 않음 |
| 10 | ORCA Ai / Ai Link | **내부 서비스** — iNSURANCE AI 문서에서 다루지 않음 |

## 아이에프에이 자산과의 경계

```
아이에프에이 내부 (이 폴더에서 다루지 않음)
  ORCA Ai      FA 전용 업무 AI
  Ai Link      「○○○의 Ai Link」 기존 고객 채널
        │
        │  기술·데이터·운영 경험을 기반으로
        ▼
iNSURANCE AI (신설 사업자) ← 이 폴더
  독립 앱/웹 · B2C + B2B · 자체 브랜드
```

대외 문서에서 아이에프에이를 언급할 때는 **신뢰의 근거**로만 씁니다.
예: "2년간의 실제 보험설계·계약관리 운영 경험과 데이터 생태계 위에서 출발했습니다."
모회사·자회사·스핀오프 같은 지분 관계는 서술하지 않습니다.

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
