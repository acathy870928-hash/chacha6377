"""FastAPI 진입점: SSE 스트리밍 채팅 API + 정적 웹 UI."""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chat import stream_reply
from .config import STATIC_DIR, get_settings
from .knowledge import load_products
from .sessions import store

app = FastAPI(title="보험 상담 챗봇", version="0.1.0")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)


class ResetRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "mode": "claude" if settings.llm_enabled else "fallback",
        "model": settings.model if settings.llm_enabled else None,
        "active_sessions": len(store),
    }


@app.get("/api/products")
async def products() -> dict:
    return {
        "products": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "summary": p["summary"],
            }
            for p in load_products()
        ]
    }


@app.post("/api/reset")
async def reset(request: ResetRequest) -> dict:
    store.reset(request.session_id)
    return {"status": "reset"}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    messages = store.get(request.session_id)
    messages.append({"role": "user", "content": request.message})

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in stream_reply(messages):
                yield _sse(event)
        except Exception:  # noqa: BLE001 - 스트림이 조용히 끊기지 않도록
            yield _sse(
                {
                    "type": "error",
                    "message": "응답 생성 중 문제가 발생했습니다. 다시 시도해 주세요.",
                }
            )
        finally:
            store.trim(request.session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 뒤에서도 버퍼링되지 않도록
        },
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
