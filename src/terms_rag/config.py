"""환경변수 기반 설정. 별도 의존성 없이 .env 를 읽는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .chunker import ChunkConfig

_ENV_LOADED = False


def load_dotenv(path: str | Path = ".env") -> None:
    """아주 단순한 .env 로더 (KEY=VALUE, # 주석). 이미 설정된 환경변수는 덮어쓰지 않는다."""
    global _ENV_LOADED
    file = Path(path)
    if _ENV_LOADED or not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    _ENV_LOADED = True


def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} 값이 정수가 아닙니다: {raw!r}") from exc


@dataclass
class Settings:
    embedding_provider: str = "voyage"
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3.5"
    openai_api_key: str | None = None
    openai_model: str = "text-embedding-3-large"
    anthropic_api_key: str | None = None
    answer_model: str = "claude-opus-5"
    store_path: str = ".store"
    chunk: ChunkConfig = None  # type: ignore[assignment]

    @classmethod
    def from_env(cls, *, dotenv: str | Path = ".env") -> "Settings":
        load_dotenv(dotenv)
        return cls(
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "voyage").strip().lower(),
            voyage_api_key=os.getenv("VOYAGE_API_KEY") or None,
            voyage_model=os.getenv("VOYAGE_MODEL", "voyage-3.5"),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
            answer_model=os.getenv("ANSWER_MODEL", "claude-opus-5"),
            store_path=os.getenv("STORE_PATH", ".store"),
            chunk=ChunkConfig(
                max_chars=_int_env("CHUNK_MAX_CHARS", 1200),
                min_chars=_int_env("CHUNK_MIN_CHARS", 200),
                overlap_chars=_int_env("CHUNK_OVERLAP_CHARS", 120),
            ),
        )
