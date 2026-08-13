"""질문 분류와 소스 라우팅.

분류(의도 파악)는 LLM이 하고, 그 결과로부터 '어느 소스를 쓸지'와
'가입 시점 특정이 필요한지'는 ROUTING_TABLE이 결정한다.
보상 판단이 걸린 영역이라, 판단 규칙을 매번 LLM 생성에 맡기지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from .types import (
    ROUTING_TABLE,
    QuestionType,
    RoutingPolicy,
    Source,
    VersionSensitivity,
)

CLASSIFICATION_PROMPT = """\
당신은 보험 상담 도구의 질문 분류기입니다. 사용자는 FA(보험설계사)입니다.
질문을 읽고 아래 JSON 형식으로만 답하십시오. 설명을 덧붙이지 마십시오.

[질문 유형]
- concept        : 개념 · 이론 · 제도 · 법령에 대한 일반 질문
                   예) 「글라이드패스가 뭔가요?」 「변액보험 사업비 구조는?」
- sales          : 판매 화법 · 상담 전략 · 고객 설득 방법
                   예) 「변액연금 잘 팔려면?」
- product_info   : 특정 상품의 구조 · 특징 · 보장 구성에 대한 설명 요청
                   예) 「오토파일럿 변액연금 어떤 상품이야?」
- benefit_term   : 약관에 정의된 담보 · 급부 용어의 뜻을 묻는 질문
                   예) 「골절진단비가 뭔가요?」 「후유장해가 뭐예요?」 「면책기간이 뭔가요?」
- coverage       : 특정 상황에서 보험금이 지급되는지, 면책인지에 대한 질문
                   예) 「음주운전 사고인데 보험금 나오나요?」 「갑상선암도 진단금 대상인가요?」
- underwriting   : 가입 가능 여부 · 인수 조건 · 고지의무
                   예) 「고혈압 있어도 가입되나요?」
- procedure      : 청구 절차 · 필요 서류 · 처리 기간
                   예) 「진단금 청구할 때 뭐가 필요해요?」
- contract_value : 특정 계약의 실제 값을 묻는 질문 (가입금액, 해지환급금, 수수료 등)
                   예) 「이 고객 진단금 얼마 나와요?」 「제 이번달 수수료는?」

판단이 애매하면 다음을 기준으로 하십시오.
- 「이런 경우에 되나요 / 나오나요 / 해당되나요」 → coverage
- 「얼마인가요」처럼 금액 자체를 묻는다 → contract_value
- 「○○(진단비/수술비/입원비/담보/특약)가 뭔가요」처럼 약관에 나오는 담보 용어의 뜻 → benefit_term
- 보험 이론 · 제도 · 금융 일반처럼 약관 밖의 개념 설명 → concept
  (글라이드패스 → concept, 골절진단비 → benefit_term)

[출력 형식]
{{
  "question_type": "위 유형 중 하나",
  "product_mentioned": "질문에 등장한 상품명, 없으면 null",
  "period_mentioned": "질문에 등장한 가입 시점 표현, 없으면 null",
  "rider_mentioned": "질문에 등장한 특약명, 없으면 null",
  "needs_policy_terms": true 또는 false,
  "reason": "한 문장"
}}

needs_policy_terms는 답하기 위해 보험약관을 확인해야 하는지 여부입니다.
상품마다 달라지는 내용이면 true, 일반 지식으로 답할 수 있으면 false입니다.

[질문]
{question}
"""


class LLMClient(Protocol):
    """분류에 쓰는 최소 인터페이스. 어떤 provider를 쓰든 이 형태만 맞추면 된다."""

    def __call__(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Classification:
    question_type: QuestionType
    product_mentioned: str | None = None
    period_mentioned: str | None = None
    rider_mentioned: str | None = None
    needs_policy_terms: bool = False
    reason: str = ""

    question: str = ""
    """원 질문. 미등록 약관 요청을 남길 때 함께 기록한다."""


@dataclass(frozen=True)
class RoutingDecision:
    sources: tuple[Source, ...]
    version_sensitivity: VersionSensitivity
    classification: Classification
    note: str = ""

    @property
    def uses_veluga(self) -> bool:
        return Source.VELUGA in self.sources

    @property
    def in_scope(self) -> bool:
        return bool(self.sources)


def build_classification_prompt(question: str) -> str:
    return CLASSIFICATION_PROMPT.format(question=question)


def parse_classification(raw: str) -> Classification:
    """LLM 응답(JSON)을 Classification으로. 앞뒤 군더더기는 걷어낸다."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"분류 응답에서 JSON을 찾지 못했습니다: {raw!r}")

    data = json.loads(text[start : end + 1])
    try:
        question_type = QuestionType(data["question_type"])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"알 수 없는 질문 유형입니다: {data.get('question_type')!r}") from exc

    return Classification(
        question_type=question_type,
        product_mentioned=_clean(data.get("product_mentioned")),
        period_mentioned=_clean(data.get("period_mentioned")),
        rider_mentioned=_clean(data.get("rider_mentioned")),
        needs_policy_terms=bool(data.get("needs_policy_terms", False)),
        reason=str(data.get("reason", "")),
    )


def classify(question: str, llm: LLMClient | Callable[[str], str]) -> Classification:
    classification = parse_classification(llm(build_classification_prompt(question)))
    return replace(classification, question=question)


def policy_for(classification: Classification) -> RoutingPolicy:
    return ROUTING_TABLE[classification.question_type]


def route(classification: Classification) -> RoutingDecision:
    """분류 결과 → 소스와 시점 민감도. 결정적으로 계산한다."""
    policy = policy_for(classification)
    sources = list(policy.sources)
    note = policy.note

    # 개념 · 세일즈 질문이라도 상품이 특정되면 약관 근거가 함께 필요하다.
    # 예) 「오토파일럿 변액연금 잘 팔려면?」 → 세일즈 화법(Micky) + 상품 내용(VELUGA)
    if (
        classification.question_type in (QuestionType.CONCEPT, QuestionType.SALES)
        and (classification.product_mentioned or classification.needs_policy_terms)
        and Source.VELUGA not in sources
    ):
        sources.append(Source.VELUGA)
        note = "상품이 특정되어 약관 근거를 함께 사용합니다."

    return RoutingDecision(
        sources=tuple(sources),
        version_sensitivity=policy.version_sensitivity,
        classification=classification,
        note=note,
    )


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "없음"}:
        return None
    return text
