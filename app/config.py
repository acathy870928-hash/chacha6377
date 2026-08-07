"""애플리케이션 설정."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR.parent / "static"


class Settings:
    """환경 변수 기반 설정."""

    def __init__(self) -> None:
        self.api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
        self.model: str = os.getenv("CHATBOT_MODEL", "claude-opus-5")
        # 챗봇은 응답 속도가 중요하므로 낮은 effort 를 기본값으로 둔다.
        # low/medium 도 품질이 충분히 좋고 토큰·지연이 크게 줄어든다.
        self.effort: str = os.getenv("CHATBOT_EFFORT", "low")
        self.max_tokens: int = int(os.getenv("CHATBOT_MAX_TOKENS", "8000"))
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        # 한 턴에서 허용할 최대 툴 호출 라운드 수 (무한 루프 방지)
        self.max_tool_rounds: int = int(os.getenv("CHATBOT_MAX_TOOL_ROUNDS", "6"))

    @property
    def llm_enabled(self) -> bool:
        """API 키가 있으면 Claude 를 사용하고, 없으면 규칙 기반 폴백으로 동작한다."""
        return bool(self.api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
