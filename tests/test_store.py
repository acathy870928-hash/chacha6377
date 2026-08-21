"""벡터스토어 + 하이브리드 검색 테스트."""

import numpy as np
import pytest

from conftest import SAMPLE_TERMS
from terms_rag.chunker import TermsChunker
from terms_rag.embedder import HashEmbedder
from terms_rag.pdf_loader import load_text
from terms_rag.store import VectorStore, tokenize


@pytest.fixture
def chunks():
    return TermsChunker().chunk(load_text(SAMPLE_TERMS, title="차차 약관"))


@pytest.fixture
def store(tmp_path, chunks):
    embedder = HashEmbedder()
    store = VectorStore(tmp_path / "store")
    store.upsert(
        chunks,
        embedder.embed_documents([c.embed_text for c in chunks]),
        provider=embedder.provider,
        model=embedder.model,
    )
    return store


class TestTokenizer:
    def test_korean_bigrams_and_latin_words(self):
        tokens = tokenize("환불 정책 API v2")
        assert "환불" in tokens and "api" in tokens and "2" in tokens

    def test_long_korean_word_yields_bigrams(self):
        assert "청약" in tokenize("청약철회")


class TestPersistence:
    def test_roundtrip(self, store, chunks):
        store.save()
        reloaded = VectorStore.load(store.path)
        assert len(reloaded) == len(chunks)
        assert reloaded.chunks[0].heading == chunks[0].heading
        assert np.allclose(reloaded.vectors, store.vectors)
        assert reloaded.manifest["provider"] == "hash"

    def test_load_missing_store_is_empty(self, tmp_path):
        assert len(VectorStore.load(tmp_path / "nope")) == 0

    def test_detects_corrupted_index(self, store, tmp_path):
        store.save()
        (store.path / "vectors.npy").unlink()
        np.save(store.path / "vectors.npy", store.vectors[:-1])
        with pytest.raises(ValueError, match="손상"):
            VectorStore.load(store.path)


class TestUpsert:
    def test_reingest_replaces_instead_of_duplicating(self, store, chunks):
        before = len(store)
        embedder = HashEmbedder()
        store.upsert(
            chunks,
            embedder.embed_documents([c.embed_text for c in chunks]),
            provider="hash",
            model=embedder.model,
        )
        assert len(store) == before

    def test_rejects_mixing_embedding_models(self, store, chunks):
        with pytest.raises(ValueError, match="인덱스"):
            store.upsert(chunks, np.zeros((len(chunks), 512), dtype=np.float32), provider="hash", model="다른모델")

    def test_vectors_are_normalized(self, store):
        norms = np.linalg.norm(store.vectors, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

    def test_length_mismatch_rejected(self, store, chunks):
        with pytest.raises(ValueError):
            store.upsert(chunks, np.zeros((2, 512), dtype=np.float32), provider="hash", model="hash-v1-512")


class TestSearch:
    def test_lexical_match_wins(self, store):
        hits = store.search(None, query_text="청약철회 환불", top_k=3)
        assert hits[0].chunk.article_no == "12"

    def test_hybrid_finds_the_refund_article(self, store):
        embedder = HashEmbedder()
        hits = store.search(embedder.embed_query("환불 기한"), query_text="환불 기한", top_k=3)
        assert "12" in [h.chunk.article_no for h in hits]

    def test_rrf_fusion_also_works(self, store):
        embedder = HashEmbedder()
        hits = store.search(embedder.embed_query("환불"), query_text="환불", top_k=3, fusion="rrf")
        assert hits and hits[0].rank == 1

    def test_section_filter(self, store):
        hits = store.search(None, query_text="시행", top_k=5, section="부칙")
        assert hits and all(h.chunk.section == "부칙" for h in hits)

    def test_doc_filter_excludes_everything_else(self, store):
        assert store.search(None, query_text="환불", doc_id="없는문서") == []

    def test_top_k_is_respected(self, store):
        assert len(store.search(None, query_text="회원", top_k=2)) == 2

    def test_requires_a_query(self, store):
        with pytest.raises(ValueError):
            store.search(None, query_text="  ")

    def test_rejects_bad_alpha(self, store):
        with pytest.raises(ValueError):
            store.search(None, query_text="환불", alpha=1.5)

    def test_empty_store_returns_nothing(self, tmp_path):
        assert VectorStore(tmp_path / "empty").search(None, query_text="환불") == []


class TestHashEmbedder:
    def test_deterministic(self):
        embedder = HashEmbedder()
        assert np.allclose(embedder.embed_query("환불"), embedder.embed_query("환불"))

    def test_shape_and_norm(self):
        vectors = HashEmbedder().embed_documents(["환불 규정", "면책 조항"])
        assert vectors.shape == (2, 512)
        assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)

    def test_empty_input(self):
        assert HashEmbedder().embed_documents([]).shape == (0, 512)
