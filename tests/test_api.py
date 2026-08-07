"""API 통합 테스트.

ANTHROPIC_API_KEY 없이 규칙 기반 폴백 모드로 전체 경로를 검증한다.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.sessions import store


@pytest.fixture(autouse=True)
def _force_fallback_mode(monkeypatch):
    """테스트는 실제 API 를 호출하지 않도록 폴백 모드로 고정한다."""
    settings = get_settings()
    monkeypatch.setattr(settings, "api_key", None)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def sse_events(response) -> list[dict]:
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def chat(client, message, session_id="test-session"):
    response = client.post(
        "/api/chat", json={"session_id": session_id, "message": message}
    )
    assert response.status_code == 200
    return sse_events(response)


def reply_text(events) -> str:
    return "".join(e["text"] for e in events if e["type"] == "text")


def test_health_reports_fallback_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["mode"] == "fallback"


def test_products_endpoint(client):
    products = client.get("/api/products").json()["products"]
    assert len(products) >= 6
    assert {"id", "name", "category", "summary"} <= set(products[0])


def test_index_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "상담 챗봇" in response.text


def test_chat_streams_text_and_done(client):
    events = chat(client, "안녕하세요")
    assert events[-1]["type"] == "done"
    assert "한화롭게보험" in reply_text(events)


def test_chat_answers_policy_question(client):
    events = chat(client, "실손보험 중복으로 가입해도 되나요?")
    text = reply_text(events)
    assert "비례" in text or "중복" in text


def test_chat_calculates_premium(client):
    events = chat(client, "40세 남성인데 암보험 3000만원 보험료 얼마인가요?")
    text = reply_text(events)
    assert "36,000원" in text


def test_chat_asks_for_missing_premium_info(client):
    events = chat(client, "보험료가 얼마인가요?")
    text = reply_text(events)
    assert "나이" in text and "성별" in text


def test_chat_returns_claim_guide(client):
    events = chat(client, "암 진단금 청구 서류 알려주세요")
    text = reply_text(events)
    assert "진단서" in text


def test_chat_requires_identity_for_contract_lookup(client):
    events = chat(client, "내 보험 계약 조회해주세요")
    text = reply_text(events)
    assert "생년월일" in text


def test_reset_clears_history(client):
    session_id = "reset-session"
    chat(client, "안녕하세요", session_id=session_id)
    assert len(store.get(session_id)) > 0

    assert client.post("/api/reset", json={"session_id": session_id}).status_code == 200
    assert store.get(session_id) == []


def test_rejects_empty_message(client):
    response = client.post("/api/chat", json={"session_id": "s", "message": ""})
    assert response.status_code == 422


def test_history_accumulates_across_turns(client):
    session_id = "multi-turn"
    store.reset(session_id)
    chat(client, "안녕하세요", session_id=session_id)
    chat(client, "암보험 알려주세요", session_id=session_id)
    # user 2건 + assistant 2건
    assert len(store.get(session_id)) == 4
