"""문서 메타데이터(보험사·상품·시행일)와 그걸 이용한 필터링 테스트."""

import json

import pytest

from terms_rag.doc_chunker import chunk_document
from terms_rag.embedder import HashEmbedder
from terms_rag.metadata import (
    DocumentMeta,
    apply_to_chunks,
    canonical_insurer,
    detect_insurers,
    extract_code,
    normalize_product_name,
    parse_filename,
    read_meta,
)
from terms_rag.pdf_loader import load_text
from terms_rag.search import search
from terms_rag.store import VectorStore

REAL_NAME = "20090801_20091001_현대해상_약관_무배당 하이라이프퍼펙트종합보험(Hi0908)_S367.pdf"

TERMS_BODY = """무배당 하이라이프퍼펙트종합보험 약관

제1조(목적)
이 약관은 회사가 판매하는 보험계약에 관한 사항을 정합니다.

제12조(청약의 철회)
① 계약자는 청약을 한 날부터 15일 이내에 그 청약을 철회할 수 있습니다.
② 회사는 청약의 철회를 접수한 날부터 3영업일 이내에 보험료를 돌려드립니다.

제13조(보험금을 지급하지 않는 사유)
① 회사는 피보험자가 고의로 자신을 해친 경우 보험금을 지급하지 않습니다.
"""


class TestFilenameParsing:
    def test_real_filename_matches_expected_schema(self):
        meta = parse_filename(REAL_NAME)
        assert meta.insurer == "현대해상"
        assert meta.product_name_raw == "무배당 하이라이프퍼펙트종합보험(Hi0908)"
        assert meta.product_name_standard == "하이라이프퍼펙트종합보험"
        assert meta.product_code == "HI0908"
        assert meta.document_type == "보험약관"
        assert meta.effective_from == "2009-08-01"
        assert meta.effective_to == "2009-10-01"
        assert meta.serial == "S367"

    def test_label_for_citations(self):
        assert parse_filename(REAL_NAME).label == "현대해상 하이라이프퍼펙트종합보험(HI0908)"

    def test_partial_filename_leaves_unknowns_empty(self):
        meta = parse_filename("그냥_약관.pdf")
        assert meta.insurer is None and meta.effective_from is None
        assert meta.source_file == "그냥_약관.pdf"

    def test_unknown_insurer_is_not_guessed(self):
        meta = parse_filename("20240101_20241231_없는보험_약관_어떤상품(XX1)_S1.pdf")
        assert meta.insurer is None
        # 보험사로 소비되지 않았으므로 상품명 쪽으로 흘러간다
        assert meta.product_name_raw and "없는보험" in meta.product_name_raw

    def test_single_date_is_treated_as_start(self):
        meta = parse_filename("20240101_흥국화재_약관_무배당 흥Good 종합보험(HG1)_S2.pdf")
        assert meta.effective_from == "2024-01-01" and meta.effective_to is None

    def test_invalid_date_is_ignored(self):
        assert parse_filename("20241340_20241231_현대해상_약관_상품(A1)_S1.pdf").effective_from is None

    def test_ocr_derived_name_falls_back_to_the_original(self):
        meta = parse_filename(REAL_NAME.replace(".pdf", ".ocr.txt"))
        assert meta.insurer == "현대해상" and meta.product_code == "HI0908"


class TestNormalization:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("무배당 하이라이프퍼펙트종합보험(Hi0908)", "하이라이프퍼펙트종합보험"),
            ("무배당 흥Good 더플러스 종합보험(26.03)", "흥Good 더플러스 종합보험"),
            ("(무)삼성종합보장보험", "삼성종합보장보험"),
            ("갱신형 실손의료보험", "실손의료보험"),
            ("메리츠 The가벼운 간편355건강보험", "메리츠 The가벼운 간편355건강보험"),
        ],
    )
    def test_strips_prefixes_and_codes(self, raw, expected):
        assert normalize_product_name(raw) == expected

    def test_never_returns_empty(self):
        assert normalize_product_name("무배당") == "무배당"

    @pytest.mark.parametrize(
        "raw, code",
        [("상품명(Hi0908)", "HI0908"), ("상품명[HG2401]", "HG2401"), ("상품명", None)],
    )
    def test_extracts_product_code(self, raw, code):
        assert extract_code(raw) == code


class TestInsurerRecognition:
    @pytest.mark.parametrize(
        "text, expected",
        [("현대해상화재보험", "현대해상"), ("현대해상", "현대해상"), ("동부화재", "DB손해보험"), ("없는회사", None)],
    )
    def test_canonical_names(self, text, expected):
        assert canonical_insurer(text) == expected

    def test_detects_insurer_in_a_question(self):
        assert detect_insurers("흥국화재 암보험 가입했었어요, 호스피스 보험금 있나요?") == ["흥국화재"]

    def test_detects_multiple_for_comparison_questions(self):
        found = detect_insurers("현대해상이랑 삼성생명 중 어디가 유리한가요?")
        assert set(found) == {"현대해상", "삼성생명"}

    def test_no_insurer_mentioned(self):
        assert detect_insurers("청약철회는 며칠 안에 해야 하나요?") == []


class TestSidecar:
    def test_overrides_filename_parsing(self, tmp_path):
        pdf = tmp_path / REAL_NAME
        pdf.write_bytes(b"%PDF-1.4")
        (tmp_path / f"{REAL_NAME}.meta.json").write_text(
            json.dumps({"document": {"product_name_standard": "손으로 고친 상품명"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        meta = read_meta(pdf)
        assert meta.product_name_standard == "손으로 고친 상품명"
        assert meta.insurer == "현대해상"  # 나머지는 파일명에서 그대로

    def test_accepts_flat_json_too(self, tmp_path):
        pdf = tmp_path / "약관.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        (tmp_path / "약관.pdf.meta.json").write_text(
            json.dumps({"insurer": "흥국화재"}, ensure_ascii=False), encoding="utf-8"
        )
        assert read_meta(pdf).insurer == "흥국화재"

    def test_broken_json_is_reported(self, tmp_path):
        pdf = tmp_path / "약관.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        (tmp_path / "약관.pdf.meta.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON"):
            read_meta(pdf)


class TestEffectiveDates:
    @pytest.mark.parametrize(
        "when, expected",
        [("2009-09-01", True), ("2009-08-01", True), ("2009-10-01", True), ("2009-07-31", False), ("2010-01-01", False)],
    )
    def test_effective_on(self, when, expected):
        assert parse_filename(REAL_NAME).effective_on(when) is expected

    def test_missing_dates_never_exclude(self):
        assert DocumentMeta(insurer="현대해상").effective_on("1999-01-01") is True


class TestChunkStamping:
    def test_chunks_carry_document_identity(self):
        doc = load_text(TERMS_BODY, title="약관", source=REAL_NAME)
        doc.meta = parse_filename(REAL_NAME).to_dict()
        chunks = chunk_document(doc)
        target = next(c for c in chunks if c.article_no == "12")
        assert target.insurer == "현대해상"
        assert target.product_code == "HI0908"
        assert target.effective_from == "2009-08-01"

    def test_citation_leads_with_insurer_and_product(self):
        doc = load_text(TERMS_BODY, title="약관", source=REAL_NAME)
        doc.meta = parse_filename(REAL_NAME).to_dict()
        target = next(c for c in chunk_document(doc) if c.article_no == "12")
        assert target.citation.startswith("현대해상 하이라이프퍼펙트종합보험(HI0908) 제12조")

    def test_embed_text_includes_identity(self):
        doc = load_text(TERMS_BODY, title="약관", source=REAL_NAME)
        doc.meta = parse_filename(REAL_NAME).to_dict()
        target = next(c for c in chunk_document(doc) if c.article_no == "12")
        assert "현대해상" in target.embed_text

    def test_without_metadata_nothing_changes(self):
        chunks = chunk_document(load_text(TERMS_BODY, title="약관"))
        assert all(c.insurer == "" for c in chunks)
        assert chunks[0].citation.startswith("약관 ")


@pytest.fixture
def multi_store(tmp_path):
    """보험사 3곳의 같은 조항을 담은 인덱스."""
    embedder = HashEmbedder()
    store = VectorStore(tmp_path / "store")
    specs = [
        ("현대해상", "하이라이프퍼펙트종합보험", "HI0908", "2009-08-01", "2009-10-01"),
        ("흥국화재", "흥Good 더플러스 종합보험", "HG2401", "2024-01-01", "2024-12-31"),
        ("삼성생명", "삼성종합보장보험", "SS2401", "2024-01-01", "2024-12-31"),
    ]
    chunks = []
    for insurer, product, code, start, end in specs:
        doc = load_text(TERMS_BODY, title=f"{product} 약관", source=f"{insurer}.pdf")
        made = chunk_document(doc)
        apply_to_chunks(
            made,
            DocumentMeta(
                insurer=insurer,
                product_name_standard=product,
                product_code=code,
                effective_from=start,
                effective_to=end,
            ),
        )
        for order, chunk in enumerate(made):
            chunk.chunk_id = f"{code}#{order}"
            chunk.doc_id = code
        chunks.extend(made)
    store.upsert(
        chunks,
        embedder.embed_documents([c.embed_text for c in chunks]),
        provider="hash",
        model=embedder.model,
    )
    return store


class TestFiltering:
    def test_insurer_hard_filter(self, multi_store):
        hits = multi_store.search(None, query_text="청약철회", top_k=5, insurer="흥국화재")
        assert hits and all(h.chunk.insurer == "흥국화재" for h in hits)

    def test_product_code_filter_is_case_insensitive(self, multi_store):
        hits = multi_store.search(None, query_text="청약철회", top_k=5, product_code="hi0908")
        assert hits and all(h.chunk.product_code == "HI0908" for h in hits)

    def test_as_of_keeps_only_documents_in_force(self, multi_store):
        hits = multi_store.search(None, query_text="청약철회", top_k=5, as_of="2009-09-01")
        assert hits and all(h.chunk.insurer == "현대해상" for h in hits)

    def test_as_of_excludes_everything_when_nothing_applies(self, multi_store):
        assert multi_store.search(None, query_text="청약철회", as_of="1999-01-01") == []

    def test_boost_lifts_one_insurer_without_erasing_others(self, multi_store):
        hits = multi_store.search(None, query_text="청약철회", top_k=9, boost_insurer="삼성생명")
        assert hits[0].chunk.insurer == "삼성생명"
        assert {h.chunk.insurer for h in hits} == {"현대해상", "흥국화재", "삼성생명"}


class TestAutoInsurerPriority:
    """피드백 문서의 1순위 문제: 질문에 보험사명이 있으면 그 회사 자료가 먼저 나와야 한다."""

    def _search(self, store, query, **kw):
        return search(query, store=store, embedder=HashEmbedder(), settings=None, top_k=3, **kw)

    def test_named_insurer_comes_first(self, multi_store, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        hits = self._search(multi_store, "흥국화재 청약철회하면 보험료 언제 돌려받나요?")
        assert hits[0].chunk.insurer == "흥국화재"

    def test_boost_fills_the_top_with_the_named_insurer(self, multi_store, monkeypatch):
        """가산점이 붙으면 상위가 그 회사 자료로 채워진다. 끄면 회사가 뒤섞인다."""
        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        boosted = self._search(multi_store, "삼성생명 청약철회 기한")
        plain = self._search(multi_store, "삼성생명 청약철회 기한", auto_insurer=False)
        assert {h.chunk.insurer for h in boosted} == {"삼성생명"}
        assert len({h.chunk.insurer for h in plain}) > 1

    def test_comparison_questions_do_not_boost_either_side(self, multi_store, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        both = self._search(multi_store, "현대해상이랑 삼성생명 청약철회 비교")
        plain = self._search(multi_store, "현대해상이랑 삼성생명 청약철회 비교", auto_insurer=False)
        assert [h.chunk.chunk_id for h in both] == [h.chunk.chunk_id for h in plain]


class TestMetaCli:
    def test_prints_parsed_metadata(self, tmp_path, capsys, monkeypatch):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        pdf = tmp_path / REAL_NAME
        pdf.write_bytes(b"%PDF-1.4")
        assert main(["meta", str(pdf)]) == 0
        out = capsys.readouterr().out
        assert "현대해상" in out and "HI0908" in out and "2009-08-01" in out

    def test_json_output_matches_the_schema(self, tmp_path, capsys, monkeypatch):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        pdf = tmp_path / REAL_NAME
        pdf.write_bytes(b"%PDF-1.4")
        main(["meta", str(pdf), "--json"])
        payload = json.loads(capsys.readouterr().out)["document"]
        assert payload["insurer"] == "현대해상"
        assert payload["product_name_standard"] == "하이라이프퍼펙트종합보험"
        assert payload["effective_to"] == "2009-10-01"
