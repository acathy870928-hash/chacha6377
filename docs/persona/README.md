# 페르소나 정의 (Persona Definition)

이 디렉터리는 **iFA AI**와 **Insurance AI**에게 가장 먼저 학습시켜야 할 정체성 정의입니다.
기능·상품·데이터보다 **먼저** 주입되어야 합니다. 페르소나가 없는 AI는 보험을 이해해도 보험을 대하는 태도를 알지 못합니다.

## 문서 구조

| 문서 | 역할 |
| --- | --- |
| [`../manifesto.md`](../manifesto.md) | **왜 존재하는가** — 신념 |
| [`../charter.md`](../charter.md) | **어떻게 행동하는가** — 10개 조항의 행동 규범 |
| [`core.md`](core.md) | 두 AI가 공유하는 **공통 페르소나 코어** |
| [`ifa-ai.md`](ifa-ai.md) | **iFA AI** — 전문가(설계사·FA) 증강 페르소나 |
| [`insurance-ai.md`](insurance-ai.md) | **Insurance AI** — 보험 도메인 버티컬 인텔리전스 / 고객 대면 페르소나 |

## 학습·주입 순서

```
1. Manifesto      → 존재 이유와 세계관
2. Charter        → 행동 규범 (하한선)
3. Persona Core   → 공통 정체성·톤·금지사항
4. Persona 개별   → iFA AI / Insurance AI 역할 분화
5. 도메인 지식    → 상품·약관·법령·설계 데이터
```

각 페르소나 문서 하단의 **시스템 프롬프트 블록**은 그대로 복사해 모델의 system prompt로 사용할 수 있도록 작성되어 있습니다.

> **확인 필요한 전제**
> 현재 두 페르소나는 *iFA AI = 전문가 증강*, *Insurance AI = 보험 도메인 지능·고객 대면* 으로 구분해
> 정의했습니다. 실제 제품 정의와 다르면 역할 구분만 조정하면 되며, Manifesto·Charter·Core는 그대로 유지됩니다.
