"""임베딩 백엔드.

Anthropic 은 임베딩 엔드포인트를 제공하지 않습니다(Claude 는 답변 생성에만 사용).
그래서 임베딩은 별도 제공자를 씁니다.

- ``voyage`` : Voyage AI. 한국어를 포함한 다국어 검색 품질이 좋아 기본값.
- ``openai`` : text-embedding-3-*.
- ``hash``   : API 키 없이 도는 결정적 해싱 임베딩. **테스트/오프라인 데모 전용**이며
               의미 검색 품질은 낮습니다(어휘가 겹쳐야 잡힘).

모든 백엔드는 문서용/질의용 임베딩을 구분합니다. Voyage 의 ``input_type`` 처럼
비대칭 검색(짧은 질문 ↔ 긴 조항)에서 정확도를 눈에 띄게 올려 주는 옵션입니다.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, Sequence

import numpy as np

from .config import Settings
from .store import tokenize


class Embedder(Protocol):
    provider: str
    model: str

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class VoyageEmbedder:
    """Voyage AI 임베딩. `pip install voyageai`, VOYAGE_API_KEY 필요."""

    provider = "voyage"
    batch_size = 64

    def __init__(self, model: str = "voyage-3.5", api_key: str | None = None) -> None:
        try:
            import voyageai
        except ImportError as exc:  # pragma: no cover - 설치 안내용
            raise RuntimeError("voyageai 가 필요합니다: pip install voyageai") from exc
        self.model = model
        self._client = voyageai.Client(api_key=api_key) if api_key else voyageai.Client()

    def _embed(self, texts: Sequence[str], input_type: str) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            result = self._client.embed(batch, model=self.model, input_type=input_type)
            vectors.extend(result.embeddings)
        return np.asarray(vectors, dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "query")[0]


class OpenAIEmbedder:
    """OpenAI 임베딩. `pip install openai`, OPENAI_API_KEY 필요."""

    provider = "openai"
    batch_size = 128

    def __init__(self, model: str = "text-embedding-3-large", api_key: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - 설치 안내용
            raise RuntimeError("openai 가 필요합니다: pip install openai") from exc
        self.model = model
        self._client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def _embed(self, texts: Sequence[str]) -> np.ndarray:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start : start + self.batch_size])
            response = self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return np.asarray(vectors, dtype=np.float32)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text])[0]


class HashEmbedder:
    """결정적 해싱 임베딩 — 키 없이 파이프라인 전체를 돌려보기 위한 폴백.

    토큰(한글 2-gram 포함)을 고정 차원 버킷에 해싱한 뒤 L2 정규화한다.
    의미가 아니라 어휘를 보므로 **실서비스용이 아니다.**
    """

    provider = "hash"

    def __init__(self, dim: int = 512, model: str = "hash-v1") -> None:
        self.dim = dim
        self.model = f"{model}-{dim}"

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return np.vstack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


def get_embedder(settings: Settings) -> Embedder:
    provider = settings.embedding_provider
    if provider == "voyage":
        return VoyageEmbedder(model=settings.voyage_model, api_key=settings.voyage_api_key)
    if provider == "openai":
        return OpenAIEmbedder(model=settings.openai_model, api_key=settings.openai_api_key)
    if provider == "hash":
        return HashEmbedder()
    raise ValueError(f"알 수 없는 EMBEDDING_PROVIDER: {provider!r} (voyage | openai | hash)")
