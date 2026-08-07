from app import sessions
from app.sessions import SessionStore


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _tool_result() -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "{}"}],
    }


def test_get_creates_and_reuses_session():
    store = SessionStore()
    messages = store.get("a")
    messages.append(_user("hi"))
    assert store.get("a") == [{"role": "user", "content": "hi"}]


def test_reset_removes_session():
    store = SessionStore()
    store.get("a").append(_user("hi"))
    store.reset("a")
    assert store.get("a") == []


def test_trim_keeps_short_history_untouched():
    store = SessionStore()
    messages = store.get("a")
    messages.extend([_user("q"), _assistant("a")])
    store.trim("a")
    assert len(store.get("a")) == 2


def test_trim_cuts_at_user_text_boundary():
    store = SessionStore()
    messages = store.get("a")
    for i in range(sessions.MAX_MESSAGES + 10):
        messages.append(_user(f"q{i}"))
        messages.append(_assistant(f"a{i}"))

    store.trim("a")
    trimmed = store.get("a")
    assert len(trimmed) <= sessions.MAX_MESSAGES
    assert trimmed[0]["role"] == "user"
    assert isinstance(trimmed[0]["content"], str)


def test_trim_never_starts_with_orphaned_tool_result():
    """tool_result 로 시작하는 이력은 API 가 400 을 반환하므로 발생하면 안 된다."""
    store = SessionStore()
    messages = store.get("a")
    for _ in range(sessions.MAX_MESSAGES):
        messages.append(_user("q"))
        messages.append(_assistant("uses tool"))
        messages.append(_tool_result())
        messages.append(_assistant("final"))

    store.trim("a")
    trimmed = store.get("a")
    if trimmed:
        first = trimmed[0]
        assert first["role"] == "user"
        assert isinstance(first["content"], str)


def test_overflow_evicts_oldest_sessions():
    store = SessionStore()
    for i in range(sessions.MAX_SESSIONS + 5):
        store.get(f"s{i}")
    assert len(store) <= sessions.MAX_SESSIONS


def test_expired_sessions_are_evicted(monkeypatch):
    store = SessionStore()
    store.get("old")
    # 저장된 타임스탬프를 TTL 이전으로 되돌린다.
    store._sessions["old"]["updated_at"] -= sessions.SESSION_TTL_SECONDS + 1
    store.get("new")
    assert "old" not in store._sessions
