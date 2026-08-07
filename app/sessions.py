"""인메모리 대화 세션 저장소.

데모용이므로 프로세스 메모리에만 저장한다. 실제 서비스에서는 Redis 등
외부 저장소로 바꾸고, 개인정보 보관 정책에 맞춰 TTL 을 적용해야 한다.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

MAX_SESSIONS = 500
SESSION_TTL_SECONDS = 60 * 60  # 1시간
MAX_MESSAGES = 60  # 세션당 보관할 최대 메시지 수


class SessionStore:
    def __init__(self) -> None:
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def get(self, session_id: str) -> list[dict[str, Any]]:
        self._evict_expired()
        entry = self._sessions.get(session_id)
        if entry is None:
            entry = {"messages": [], "updated_at": time.time()}
            self._sessions[session_id] = entry
            self._evict_overflow()
        entry["updated_at"] = time.time()
        self._sessions.move_to_end(session_id)
        return entry["messages"]

    def trim(self, session_id: str) -> None:
        """오래된 메시지를 잘라낸다.

        tool_use 블록과 그 tool_result 가 분리되면 API 가 400 을 반환하므로,
        자를 위치는 반드시 user 텍스트 메시지 경계여야 한다.
        """
        entry = self._sessions.get(session_id)
        if entry is None:
            return
        messages = entry["messages"]
        if len(messages) <= MAX_MESSAGES:
            return

        for index in range(len(messages) - MAX_MESSAGES, len(messages)):
            if _is_user_text_message(messages[index]):
                entry["messages"] = messages[index:]
                return
        # 안전한 경계를 못 찾으면 이력을 비운다 (깨진 이력을 보내는 것보다 낫다).
        entry["messages"] = []

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)

    def _evict_expired(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        expired = [
            key for key, entry in self._sessions.items() if entry["updated_at"] < cutoff
        ]
        for key in expired:
            del self._sessions[key]

    def _evict_overflow(self) -> None:
        while len(self._sessions) > MAX_SESSIONS:
            self._sessions.popitem(last=False)


def _is_user_text_message(message: dict[str, Any]) -> bool:
    """tool_result 가 아닌 순수 사용자 발화인지 확인한다."""
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


store = SessionStore()
