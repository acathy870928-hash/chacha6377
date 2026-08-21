# Insurance AI 스펙 (Specification)

> Insurance AI 하나만을 위한 완결된 스펙 세트입니다.
> "Insurance AI가 무엇인지, 어떻게 행동하는지, 어떤 구조 위에서 동작하는지"를 이 폴더 안에서 전부 답합니다.

| 문서 | 답하는 질문 |
| --- | --- |
| [`definition.md`](definition.md) | **무엇인가** — 정의, 위치, 역할, 표기 |
| [`guidelines.md`](guidelines.md) | **어떻게 행동하는가** — 운영 지침 7장 |
| [`layers.md`](layers.md) | **어떤 구조 위에서 동작하는가** — 레이어 구성과 처리 흐름 |
| [`../prompt/insurance-ai.system.md`](../prompt/insurance-ai.system.md) | **배포물** — 위 세 문서를 조립한 시스템 프롬프트 (v1.1) |

## 전제 (미확정 시 적용한 기본값)

아래 전제로 작성했습니다. 다르면 알려주시면 일괄 수정합니다.

1. **Insurance AI는 고객용 AI입니다.** 전문가용은 iFA AI(ORCA Ai) 트랙으로, 이번 범위에서 제외합니다.
2. **제공 채널은 Ai Link입니다.** 「○○○의 Ai Link」의 챗봇 두뇌가 Insurance AI입니다.
3. **벨루가 6개월 구축의 결과물(상품 에이전트 + 약관 RAG)이 Insurance AI의 1차 두뇌입니다.**

## 상위 정본과의 관계

```
Manifesto · Charter        (철학 — 공통)
Company · Glossary         (전략·용어 — 공통)
        │
        ▼  Insurance AI로 좁혀서
insurance-ai/  ← 이 폴더    definition → guidelines → layers
        │
        ▼  조립
prompt/insurance-ai.system.md  (배포)
```
