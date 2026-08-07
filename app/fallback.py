"""API 키가 없을 때 쓰이는 규칙 기반 폴백 엔진.

자연어 이해력은 제한적이지만, 키를 넣지 않아도 앱 전체 흐름(스트리밍 UI, 툴,
지식 검색)을 그대로 시연·테스트할 수 있게 해준다.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator

from .knowledge import search
from .tools import calculate_premium, get_claim_guide, list_products

_GREETING = re.compile(r"안녕|하이|반가|hello|hi\b", re.IGNORECASE)
_PREMIUM = re.compile(r"보험료|얼마|견적|가격|비용")
_CLAIM = re.compile(r"청구|서류|보험금\s*받|접수")
_CONTRACT = re.compile(r"내\s*보험|가입한|계약\s*조회|보유\s*계약")
_AGENT = re.compile(r"상담원|사람|직원|전화\s*연결")
_PRODUCT_LIST = re.compile(r"상품\s*(목록|종류|뭐|어떤)|어떤\s*보험")

_AGE = re.compile(r"(\d{1,3})\s*(?:살|세)")
_AMOUNT = re.compile(r"(\d{1,6})\s*만\s*원")
_FEMALE = re.compile(r"여자|여성|female")
_MALE = re.compile(r"남자|남성|male")

_CLAIM_TYPE_HINTS = {
    "실손의료비": ("실손", "실비", "병원비", "의료비", "통원", "입원"),
    "암진단": ("암", "진단금", "항암"),
    "자동차사고": ("자동차", "차사고", "접촉", "교통사고"),
    "사망": ("사망", "유족", "상속"),
    "해외여행": ("해외", "여행", "휴대품"),
}

_PRODUCT_HINTS = {
    "health-001": ("실손", "실비", "의료비", "병원비"),
    "cancer-001": ("암",),
    "life-001": ("종신", "사망"),
    "auto-001": ("자동차", "차보험", "자차"),
    "driver-001": ("운전자", "벌금", "변호사"),
    "travel-001": ("여행", "해외"),
}


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                return " ".join(texts)
    return ""


def _match_hint(text: str, hints: dict[str, tuple[str, ...]]) -> str | None:
    for key, words in hints.items():
        if any(word in text for word in words):
            return key
    return None


def _won(value: int) -> str:
    return f"{value:,}원"


def build_fallback_reply(text: str) -> str:
    """마지막 사용자 발화에 대한 규칙 기반 답변을 만든다."""
    text = text.strip()
    if not text:
        return "무엇을 도와드릴까요? 상품 안내, 보험료 견적, 보험금 청구 방법 등을 안내해 드릴 수 있습니다."

    if _GREETING.search(text) and len(text) <= 20:
        return (
            "안녕하세요, 한화롭게보험 상담 챗봇입니다.\n"
            "상품 안내, 보험료 견적, 보험금 청구 절차를 도와드릴 수 있습니다. 무엇이 궁금하신가요?"
        )

    if _AGENT.search(text):
        return (
            "상담원 연결을 도와드리겠습니다. 고객센터 1588-0000 (평일 09:00~18:00) 으로 연락 주시거나, "
            "회신받으실 연락처를 남겨주시면 순차적으로 연락드립니다."
        )

    if _PRODUCT_LIST.search(text):
        products = list_products()["products"]
        lines = [f"- {p['name']}: {p['summary']}" for p in products]
        return "현재 취급 중인 상품입니다.\n" + "\n".join(lines)

    if _CONTRACT.search(text):
        return (
            "보유 계약 조회를 도와드리겠습니다. 본인 확인을 위해 성함과 생년월일(YYYY-MM-DD)을 알려주세요.\n"
            "예: 홍길동 / 1985-03-12"
        )

    if _PREMIUM.search(text):
        return _premium_reply(text)

    if _CLAIM.search(text):
        claim_type = _match_hint(text, _CLAIM_TYPE_HINTS)
        if claim_type is None:
            return (
                "보험금 청구를 도와드리겠습니다. 어떤 청구인지 알려주세요.\n"
                "실손의료비 / 암진단 / 자동차사고 / 사망 / 해외여행"
            )
        guide = get_claim_guide(claim_type)
        docs = "\n".join(f"- {d}" for d in guide["documents"])
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(guide["steps"], start=1))
        return (
            f"{guide['title']}\n\n"
            f"[필요 서류]\n{docs}\n\n"
            f"[절차]\n{steps}\n\n"
            f"예상 처리 기간: 영업일 기준 {guide['processing_days']}일\n{guide['note']}"
        )

    hits = search(text, limit=2)
    if hits:
        top = hits[0].document
        source = "약관·상품 설명" if top.kind == "product" else "FAQ"
        return f"{top.title}\n\n{top.body}\n\n(출처: {source} · {top.doc_id})"

    return (
        "죄송합니다, 질문을 정확히 이해하지 못했습니다.\n"
        "상품 안내, 보험료 견적, 보험금 청구 방법 중 어떤 것이 궁금하신지 알려주시거나, "
        "상담원 연결을 요청해 주세요."
    )


def _premium_reply(text: str) -> str:
    product_id = _match_hint(text, _PRODUCT_HINTS)
    age_match = _AGE.search(text)
    amount_match = _AMOUNT.search(text)
    gender = "female" if _FEMALE.search(text) else "male" if _MALE.search(text) else None

    missing = []
    if product_id is None:
        missing.append("상품 (예: 암보험, 실손보험)")
    if age_match is None:
        missing.append("나이 (예: 40세)")
    if gender is None:
        missing.append("성별")
    if amount_match is None:
        missing.append("가입금액 (예: 3000만원)")

    if missing:
        return "보험료를 계산하려면 다음 정보가 필요합니다.\n" + "\n".join(
            f"- {item}" for item in missing
        )

    result = calculate_premium(
        product_id=product_id,
        age=int(age_match.group(1)),
        gender=gender,
        coverage_amount_manwon=int(amount_match.group(1)),
    )
    if result.get("error"):
        return result["message"]

    return (
        f"{result['product_name']} 예상 보험료입니다.\n"
        f"- 월 보험료: {_won(result['monthly_premium_krw'])}\n"
        f"- 연 환산: {_won(result['annual_premium_krw'])}\n"
        f"- 조건: 만 {result['age']}세 / "
        f"{'여성' if result['gender'] == 'female' else '남성'} / "
        f"가입금액 {result['coverage_amount_manwon']:,}만원\n"
        f"- {result['renewal']}\n\n{result['disclaimer']}"
    )


async def stream_fallback_reply(
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """LLM 모드와 동일한 이벤트 형태로 규칙 기반 답변을 스트리밍한다."""
    reply = build_fallback_reply(_last_user_text(messages))
    messages.append({"role": "assistant", "content": reply})

    # 타이핑되는 느낌을 주기 위해 조각내어 내보낸다.
    chunk_size = 12
    for i in range(0, len(reply), chunk_size):
        yield {"type": "text", "text": reply[i : i + chunk_size]}
        await asyncio.sleep(0.01)

    yield {"type": "done"}
