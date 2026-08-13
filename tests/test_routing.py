import json

import pytest

from orca.routing import Classification, classify, parse_classification, route
from orca.types import QuestionType, Source, VersionSensitivity


def _cls(question_type, **kwargs):
    return Classification(question_type=question_type, **kwargs)


class TestRoute:
    def test_개념_질문은_미키만_쓰고_시점을_따지지_않는다(self):
        decision = route(_cls(QuestionType.CONCEPT))
        assert decision.sources == (Source.MICKY,)
        assert not decision.uses_veluga
        assert decision.version_sensitivity is VersionSensitivity.NONE

    def test_보상_질문은_약관을_쓰고_시점_특정이_필수다(self):
        decision = route(_cls(QuestionType.COVERAGE))
        assert decision.sources == (Source.VELUGA,)
        assert decision.version_sensitivity is VersionSensitivity.REQUIRED

    def test_인수_질문도_시점_특정이_필수다(self):
        decision = route(_cls(QuestionType.UNDERWRITING))
        assert decision.version_sensitivity is VersionSensitivity.REQUIRED

    def test_상품_설명은_시점_특정이_권장이다(self):
        decision = route(_cls(QuestionType.PRODUCT_INFO))
        assert decision.uses_veluga
        assert decision.version_sensitivity is VersionSensitivity.PREFERRED

    def test_상품이_붙은_세일즈_질문은_약관을_함께_쓴다(self):
        decision = route(_cls(QuestionType.SALES, product_mentioned="오토파일럿 변액연금"))
        assert decision.sources == (Source.MICKY, Source.VELUGA)

    def test_상품이_없는_세일즈_질문은_미키만_쓴다(self):
        decision = route(_cls(QuestionType.SALES))
        assert decision.sources == (Source.MICKY,)

    def test_계약_금액_질문은_범위_밖이다(self):
        decision = route(_cls(QuestionType.CONTRACT_VALUE))
        assert decision.sources == ()
        assert not decision.in_scope


class TestParseClassification:
    def test_평범한_JSON(self):
        raw = json.dumps(
            {
                "question_type": "coverage",
                "product_mentioned": "무배당 운전자보험",
                "period_mentioned": "2021년 6월",
                "rider_mentioned": None,
                "needs_policy_terms": True,
                "reason": "지급 여부를 묻고 있음",
            },
            ensure_ascii=False,
        )
        result = parse_classification(raw)
        assert result.question_type is QuestionType.COVERAGE
        assert result.product_mentioned == "무배당 운전자보험"
        assert result.period_mentioned == "2021년 6월"
        assert result.rider_mentioned is None
        assert result.needs_policy_terms is True

    def test_코드블록으로_감싸도_읽는다(self):
        raw = '```json\n{"question_type": "concept", "needs_policy_terms": false}\n```'
        assert parse_classification(raw).question_type is QuestionType.CONCEPT

    def test_앞뒤에_말이_붙어도_읽는다(self):
        raw = '분류 결과입니다.\n{"question_type": "sales"}\n도움이 되었길 바랍니다.'
        assert parse_classification(raw).question_type is QuestionType.SALES

    def test_빈_문자열_필드는_None으로_정리한다(self):
        raw = '{"question_type": "concept", "product_mentioned": "없음", "period_mentioned": ""}'
        result = parse_classification(raw)
        assert result.product_mentioned is None
        assert result.period_mentioned is None

    def test_모르는_유형은_거부한다(self):
        with pytest.raises(ValueError):
            parse_classification('{"question_type": "무엇인가"}')

    def test_JSON이_없으면_거부한다(self):
        with pytest.raises(ValueError):
            parse_classification("분류할 수 없습니다")


def test_classify는_주입된_LLM을_쓴다():
    captured = {}

    def fake_llm(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"question_type": "coverage", "needs_policy_terms": true}'

    result = classify("음주운전 사고인데 보험금 나오나요?", fake_llm)
    assert result.question_type is QuestionType.COVERAGE
    assert "음주운전 사고인데 보험금 나오나요?" in captured["prompt"]
