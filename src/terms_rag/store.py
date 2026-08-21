"""의존성 없는 로컬 벡터스토어 + 하이브리드(벡터 + BM25) 검색.

디스크 레이아웃::

    .store/
      vectors.npy    float32 [N, D], L2 정규화 완료
      chunks.jsonl   청크 N개 (vectors.npy 와 같은 순서)
      manifest.json  임베딩 제공자/모델/차원/문서 목록

약관 검색은 순수 벡터 검색만으로는 약합니다. "제12조", "청약철회" 처럼
질의에 조 번호나 법령 용어가 그대로 들어오는 경우가 많아서, 어휘 매칭(BM25)을
함께 쓰고 RRF(Reciprocal Rank Fusion)로 두 순위를 합칩니다.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .models import Chunk

RE_TOKEN = re.compile(r"[가-힣]+|[a-zA-Z]+|\d+")


def tokenize(text: str) -> list[str]:
    """한국어는 형태소 분석기 없이 2-gram, 영문/숫자는 단어 단위로 자른다."""
    tokens: list[str] = []
    for match in RE_TOKEN.findall(text):
        if re.fullmatch(r"[가-힣]+", match):
            tokens.append(match)
            if len(match) > 2:
                tokens.extend(match[i : i + 2] for i in range(len(match) - 1))
        else:
            tokens.append(match.lower())
    return tokens


@dataclass
class SearchHit:
    chunk: Chunk
    score: float
    vector_score: float = 0.0
    lexical_score: float = 0.0
    rank: int = 0


class _BM25:
    """작은 코퍼스용 BM25 (k1=1.5, b=0.75)."""

    def __init__(self, corpus: Sequence[str]) -> None:
        self.docs = [tokenize(text) for text in corpus]
        self.doc_len = np.array([len(d) or 1 for d in self.docs], dtype=np.float32)
        self.avg_len = float(self.doc_len.mean()) if len(self.doc_len) else 1.0
        self.freqs = [Counter(d) for d in self.docs]
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(set(doc))
        n = max(len(self.docs), 1)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, query: str, k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        scores = np.zeros(len(self.docs), dtype=np.float32)
        if not self.docs:
            return scores
        for token in tokenize(query):
            idf = self.idf.get(token)
            if idf is None:
                continue
            for idx, freq in enumerate(self.freqs):
                tf = freq.get(token, 0)
                if not tf:
                    continue
                denom = tf + k1 * (1 - b + b * self.doc_len[idx] / self.avg_len)
                scores[idx] += idf * tf * (k1 + 1) / denom
        return scores


class VectorStore:
    """청크 + 임베딩을 담는 로컬 인덱스."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.chunks: list[Chunk] = []
        self.vectors: np.ndarray = np.zeros((0, 0), dtype=np.float32)
        self.manifest: dict = {}
        self._bm25: _BM25 | None = None

    # -- 영속화 ------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        store = cls(path)
        chunks_file = store.path / "chunks.jsonl"
        vectors_file = store.path / "vectors.npy"
        manifest_file = store.path / "manifest.json"
        if not chunks_file.exists():
            return store
        store.chunks = [
            Chunk.from_dict(json.loads(line))
            for line in chunks_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if vectors_file.exists():
            store.vectors = np.load(vectors_file)
        if manifest_file.exists():
            store.manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if len(store.chunks) != len(store.vectors):
            raise ValueError(
                f"인덱스가 손상되었습니다: 청크 {len(store.chunks)}개 vs 벡터 {len(store.vectors)}개. "
                f"{store.path} 를 지우고 다시 ingest 하세요."
            )
        return store

    def save(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with (self.path / "chunks.jsonl").open("w", encoding="utf-8") as fh:
            for chunk in self.chunks:
                fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
        np.save(self.path / "vectors.npy", self.vectors)
        self.manifest["count"] = len(self.chunks)
        self.manifest["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.manifest["documents"] = self.documents()
        (self.path / "manifest.json").write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -- 색인 --------------------------------------------------------------

    def upsert(self, chunks: Sequence[Chunk], vectors: np.ndarray, *, provider: str, model: str) -> int:
        """같은 doc_id 의 기존 청크를 지우고 새로 넣는다(재수집 시 중복 방지)."""
        if len(chunks) != len(vectors):
            raise ValueError("청크 수와 벡터 수가 다릅니다.")
        vectors = _normalize(np.asarray(vectors, dtype=np.float32))

        stored_model = self.manifest.get("model")
        if stored_model and stored_model != model:
            raise ValueError(
                f"이 인덱스는 '{stored_model}' 로 만들어졌습니다. '{model}' 벡터를 섞을 수 없습니다. "
                "모델을 바꾸려면 인덱스를 새로 만드세요."
            )

        doc_ids = {c.doc_id for c in chunks}
        keep = [i for i, c in enumerate(self.chunks) if c.doc_id not in doc_ids]
        kept_chunks = [self.chunks[i] for i in keep]
        kept_vectors = self.vectors[keep] if len(self.vectors) else np.zeros((0, vectors.shape[1]), dtype=np.float32)

        self.chunks = kept_chunks + list(chunks)
        self.vectors = np.vstack([kept_vectors, vectors]) if len(kept_vectors) else vectors
        self.manifest["provider"] = provider
        self.manifest["model"] = model
        self.manifest["dim"] = int(self.vectors.shape[1])
        self._bm25 = None
        return len(chunks)

    def documents(self) -> list[dict]:
        seen: dict[str, dict] = {}
        for chunk in self.chunks:
            entry = seen.setdefault(
                chunk.doc_id,
                {
                    "doc_id": chunk.doc_id,
                    "title": chunk.doc_title,
                    "source": chunk.source,
                    "chunks": 0,
                    "insurer": chunk.insurer,
                    "product": chunk.product_name,
                    "product_code": chunk.product_code,
                    "effective": f"{chunk.effective_from}~{chunk.effective_to}".strip("~"),
                },
            )
            entry["chunks"] += 1
        return list(seen.values())

    def insurers(self) -> list[str]:
        """인덱스에 들어 있는 보험사 목록."""
        return sorted({c.insurer for c in self.chunks if c.insurer})

    # -- 검색 --------------------------------------------------------------

    def search(
        self,
        query_vector: np.ndarray | None,
        *,
        query_text: str = "",
        top_k: int = 5,
        doc_id: str | None = None,
        section: str | None = None,
        insurer: str | None = None,
        product_code: str | None = None,
        as_of: str | None = None,
        boost_insurer: str | None = None,
        boost: float = 0.5,
        alpha: float = 0.5,
        fusion: str = "score",
        rrf_k: int = 60,
    ) -> list[SearchHit]:
        """벡터 검색과 BM25 를 합쳐 상위 `top_k` 개를 돌려준다.

        fusion
          - ``"score"`` (기본): 각 점수를 후보군 안에서 0~1 로 정규화한 뒤
            ``alpha * 벡터 + (1-alpha) * BM25``. 점수 격차를 반영하므로
            "제12조", "청약철회" 같은 강한 어휘 매칭을 놓치지 않는다.
          - ``"rrf"``: 순위만 사용하는 Reciprocal Rank Fusion. 점수 분포가
            이상한 임베딩을 쓸 때 더 안정적이다.

        보험사 처리가 둘로 나뉜다.
          - ``insurer``: 하드 필터. 그 보험사 문서만 본다.
          - ``boost_insurer``: 소프트 가산점. 질문에 보험사명이 있으면 그 회사 자료를
            위로 올리되, 다른 회사 자료를 완전히 지우지는 않는다(비교 질문 대비).
        """
        if not self.chunks:
            return []
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha 는 0~1 사이여야 합니다.")

        mask = np.ones(len(self.chunks), dtype=bool)
        if doc_id:
            mask &= np.array([c.doc_id == doc_id for c in self.chunks])
        if section:
            mask &= np.array([c.section == section for c in self.chunks])
        if insurer:
            mask &= np.array([c.insurer == insurer for c in self.chunks])
        if product_code:
            code = product_code.upper()
            mask &= np.array([c.product_code.upper() == code for c in self.chunks])
        if as_of:
            mask &= np.array([_effective_on(c, as_of) for c in self.chunks])
        candidates = np.flatnonzero(mask)
        if candidates.size == 0:
            return []

        use_vector = query_vector is not None and len(self.vectors) > 0
        use_lexical = bool(query_text.strip())
        if not use_vector and not use_lexical:
            raise ValueError("질의 벡터와 질의 문자열 중 하나는 있어야 합니다.")

        vector_scores = np.zeros(len(self.chunks), dtype=np.float32)
        if use_vector:
            q = _normalize(np.asarray(query_vector, dtype=np.float32).reshape(1, -1))[0]
            vector_scores = self.vectors @ q

        lexical_scores = np.zeros(len(self.chunks), dtype=np.float32)
        if use_lexical:
            lexical_scores = self._lexical().score(query_text)

        # 한쪽만 쓸 때는 그쪽에 가중치를 몰아준다.
        weight_v = alpha if (use_vector and use_lexical) else (1.0 if use_vector else 0.0)
        weight_l = (1.0 - alpha) if (use_vector and use_lexical) else (1.0 if use_lexical else 0.0)

        if fusion == "rrf":
            ranks_v = _rank_map(vector_scores, candidates)
            ranks_l = _rank_map(lexical_scores, candidates)
            fused = [
                (
                    int(idx),
                    weight_v * (1.0 / (rrf_k + ranks_v[int(idx)]) if use_vector else 0.0)
                    + weight_l * (1.0 / (rrf_k + ranks_l[int(idx)]) if use_lexical else 0.0),
                )
                for idx in candidates
            ]
        elif fusion == "score":
            norm_v = _minmax(vector_scores[candidates])
            norm_l = _minmax(lexical_scores[candidates])
            fused = [
                (int(idx), float(weight_v * norm_v[i] + weight_l * norm_l[i]))
                for i, idx in enumerate(candidates)
            ]
        else:
            raise ValueError(f"알 수 없는 fusion: {fusion!r} (score | rrf)")

        if boost_insurer and boost:
            fused = [
                (idx, score + boost if self.chunks[idx].insurer == boost_insurer else score)
                for idx, score in fused
            ]

        fused.sort(key=lambda pair: (-pair[1], pair[0]))
        return [
            SearchHit(
                chunk=self.chunks[idx],
                score=float(score),
                vector_score=float(vector_scores[idx]),
                lexical_score=float(lexical_scores[idx]),
                rank=rank + 1,
            )
            for rank, (idx, score) in enumerate(fused[:top_k])
        ]

    def _lexical(self) -> _BM25:
        if self._bm25 is None:
            self._bm25 = _BM25([c.embed_text for c in self.chunks])
        return self._bm25

    def __len__(self) -> int:
        return len(self.chunks)


def _effective_on(chunk: Chunk, when: str) -> bool:
    """그 시점에 유효한 문서인가. 시행일 정보가 없으면 배제하지 않는다."""
    start, end = chunk.effective_from, chunk.effective_to
    if start and when < start:
        return False
    if end and when > end:
        return False
    return True


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


def _minmax(values: np.ndarray) -> np.ndarray:
    """후보군 안에서 0~1 로 정규화. 전부 같은 값이면 0으로 둔다(기여 없음)."""
    if values.size == 0:
        return values
    lo, hi = float(values.min()), float(values.max())
    if hi - lo < 1e-9:
        return np.zeros_like(values, dtype=np.float32)
    return ((values - lo) / (hi - lo)).astype(np.float32)


def _rank_map(scores: np.ndarray, candidates: np.ndarray) -> dict[int, int]:
    """후보들 사이의 1-based 순위표."""
    order = candidates[np.argsort(-scores[candidates], kind="stable")]
    return {int(idx): rank + 1 for rank, idx in enumerate(order)}


def iter_chunks(path: str | Path) -> Iterable[Chunk]:
    """저장된 chunks.jsonl 을 스트리밍으로 읽는다."""
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield Chunk.from_dict(json.loads(line))
