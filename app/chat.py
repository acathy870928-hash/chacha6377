"""Claude 기반 대화 엔진.

스트리밍 + 툴 사용을 함께 써야 하므로 SDK 의 tool_runner 대신 수동 루프를 쓴다.
(tool_runner 로도 스트리밍이 가능하지만, 여기서는 툴 호출을 UI 에 실시간으로
노출하고 라운드 수를 직접 제어하기 위해 루프를 직접 돌린다.)

`stream_reply` 는 UI 로 보낼 이벤트를 순서대로 yield 한다:
    {"type": "text",       "text": "..."}          - 응답 텍스트 조각
    {"type": "tool_use",   "name": ..., "input": {...}}
    {"type": "tool_result","name": ..., "is_error": bool}
    {"type": "done"}
    {"type": "error",      "message": "..."}
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from .config import get_settings
from .fallback import stream_fallback_reply
from .prompts import SYSTEM_PROMPT
from .tools import TOOL_SCHEMAS, run_tool

_client = None


def _get_client():
    """AsyncAnthropic 클라이언트를 지연 생성한다."""
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=get_settings().api_key)
    return _client


def _request_kwargs(messages: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        # 시스템 프롬프트 + 툴 정의를 함께 캐싱한다 (렌더 순서: tools -> system -> messages).
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": TOOL_SCHEMAS,
        # 챗봇은 지연이 중요하다. Opus 5 는 low/medium 에서도 품질이 충분히 좋다.
        "output_config": {"effort": settings.effort},
        "messages": messages,
    }


async def stream_reply(
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """대화 이력을 받아 응답을 스트리밍한다.

    `messages` 는 이 함수 안에서 assistant 응답과 tool_result 로 확장되므로,
    호출 측은 같은 리스트 객체를 세션 이력으로 계속 사용하면 된다.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        async for event in stream_fallback_reply(messages):
            yield event
        return

    client = _get_client()

    for _ in range(settings.max_tool_rounds):
        try:
            async with client.messages.stream(**_request_kwargs(messages)) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                    ):
                        yield {"type": "text", "text": event.delta.text}
                response = await stream.get_final_message()
        except Exception as exc:  # noqa: BLE001 - 사용자에게 오류를 안내하고 종료
            yield {"type": "error", "message": _friendly_error(exc)}
            return

        # 안전 분류기가 요청을 거절한 경우 content 를 읽기 전에 먼저 확인한다.
        if response.stop_reason == "refusal":
            yield {
                "type": "error",
                "message": "이 요청은 안전 정책상 답변할 수 없습니다. 다른 질문을 해주시거나 상담원 연결을 요청해 주세요.",
            }
            return

        # thinking 블록을 포함해 응답 content 를 그대로 이력에 추가한다 (변형 금지).
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            yield {"type": "done"}
            return

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_input = dict(block.input) if isinstance(block.input, dict) else {}
            yield {"type": "tool_use", "name": block.name, "input": tool_input}

            content, is_error = run_tool(block.name, tool_input)
            yield {"type": "tool_result", "name": block.name, "is_error": is_error}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )

        # 병렬 툴 호출 결과는 하나의 user 메시지에 모아서 되돌려준다.
        messages.append({"role": "user", "content": tool_results})

    yield {
        "type": "error",
        "message": "요청 처리가 예상보다 길어졌습니다. 질문을 조금 더 구체적으로 나눠서 다시 물어봐 주세요.",
    }


def _friendly_error(exc: Exception) -> str:
    """SDK 예외를 사용자에게 보여줄 문구로 바꾼다."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - 패키지가 없으면 원문 노출
        return f"오류가 발생했습니다: {exc}"

    if isinstance(exc, anthropic.RateLimitError):
        return "요청이 몰려 잠시 처리할 수 없습니다. 잠시 후 다시 시도해 주세요."
    if isinstance(exc, anthropic.AuthenticationError):
        return "서버 인증 설정에 문제가 있습니다. 관리자에게 문의해 주세요."
    if isinstance(exc, anthropic.APIConnectionError):
        return "네트워크 연결이 원활하지 않습니다. 잠시 후 다시 시도해 주세요."
    if isinstance(exc, anthropic.APIStatusError):
        return f"일시적인 오류가 발생했습니다. (코드 {exc.status_code}) 잠시 후 다시 시도해 주세요."
    return "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
