"""청킹 규칙 테스트 — 이 파일이 약관 청킹의 '계약서'다."""

import pytest

from conftest import SAMPLE_TERMS
from terms_rag.chunker import ChunkConfig, TermsChunker, _match_article
from terms_rag.pdf_loader import load_text


def chunk(text=SAMPLE_TERMS, **config):
    return TermsChunker(ChunkConfig(**config)).chunk(load_text(text, title="차차 약관"))


def by_article(chunks, article_no):
    return [c for c in chunks if c.article_no == article_no]


class TestArticleHeader:
    @pytest.mark.parametrize(
        "line, expected_no, expected_title",
        [
            ("제1조(목적)", "1", "목적"),
            ("제 12 조 (청약철회)", "12", "청약철회"),
            ("제12조의2(중도 해지)", "12-2", "중도 해지"),
            ("제3조 【약관의 개정】", "3", "약관의 개정"),
            ("제5조 회원정보의 변경", "5", "회원정보의 변경"),
        ],
    )
    def test_parses_variants(self, line, expected_no, expected_title):
        parsed = _match_article(line)
        assert parsed is not None
        no, title, _rest = parsed
        assert (no, title) == (expected_no, expected_title)

    def test_rejects_non_article_lines(self):
        assert _match_article("① 회원은 제12조에 따라 청약을 철회할 수 있습니다.") is None
        assert _match_article("제2장 총칙") is None

    def test_inline_body_after_header_is_kept(self):
        chunks = chunk("제7조(통지) 회사는 회원에게 전자우편으로 통지합니다.")
        assert len(chunks) == 1
        assert "전자우편으로 통지합니다" in chunks[0].text


class TestArticleGranularity:
    def test_one_chunk_per_article_when_short_enough(self):
        chunks = chunk()
        numbers = [c.article_no for c in chunks if c.section == "본문"]
        assert numbers == ["1", "2", "12", "12-2"]

    def test_article_body_is_not_split_across_chunks(self):
        chunks = by_article(chunk(), "2")
        assert len(chunks) == 1
        text = chunks[0].text
        assert "① 이 약관에서" in text and "② 제1항에서" in text

    def test_items_stay_with_their_paragraph(self):
        text = by_article(chunk(), "12")[0].text
        assert '1. 회원의 책임 있는 사유로' in text
        assert "① 회원은 결제일로부터" in text

    def test_chapter_and_heading_metadata(self):
        target = by_article(chunk(), "12")[0]
        assert target.chapter_no == 2
        assert target.chapter_title == "유료서비스"
        assert target.heading == "제2장 유료서비스 > 제12조(청약철회 및 환불)"
        assert target.article_title == "청약철회 및 환불"

    def test_article_with_sub_number(self):
        target = by_article(chunk(), "12-2")[0]
        assert target.heading.endswith("제12조의2(정기결제의 중도 해지)")


class TestSplitting:
    def test_long_article_splits_on_paragraph_boundaries(self):
        parts = by_article(chunk(max_chars=140, min_chars=40), "12")
        assert len(parts) > 1
        assert all(p.part_count == len(parts) for p in parts)
        # 항 표지가 청크 중간에서 잘리지 않았는지
        for part in parts:
            assert part.text.count("①") <= 1

    def test_each_split_repeats_the_article_heading(self):
        parts = by_article(chunk(max_chars=140, min_chars=40), "12")
        assert all(p.text.startswith("제12조(청약철회 및 환불)") for p in parts)

    def test_respects_max_chars(self):
        limit = 160
        for c in chunk(max_chars=limit, min_chars=40):
            assert c.char_len <= limit + len("제12조(청약철회 및 환불)") + 1

    def test_single_huge_paragraph_falls_back_to_sentences(self):
        body = " ".join(f"이것은 {i}번째 문장입니다." for i in range(60))
        parts = chunk(f"제9조(장문)\n① {body}", max_chars=200, min_chars=50)
        assert len(parts) > 1
        assert all(p.char_len <= 200 + 20 for p in parts)
        # 문장 중간에서 잘리지 않는다
        assert all(p.text.rstrip().endswith(("다.", "요.", ".")) for p in parts)

    def test_no_split_when_article_fits(self):
        assert all(c.part_count == 1 for c in chunk(max_chars=2000))


class TestSections:
    def test_addendum_is_its_own_section(self):
        addenda = [c for c in chunk() if c.section == "부칙"]
        assert len(addenda) == 1
        assert "2026년 1월 1일부터 시행" in addenda[0].text
        assert addenda[0].chapter_no is None  # 부칙은 앞 장을 물려받지 않는다

    def test_table_of_contents_is_dropped(self):
        text = "목 차\n제1조(목적) ......... 1\n제2조(정의) ......... 1\n\n" + SAMPLE_TERMS
        chunks = chunk(text)
        assert not any(c.text.strip().startswith("제1조(목적) .........") for c in chunks)
        assert by_article(chunks, "1")

    def test_stub_lines_are_dropped(self):
        chunks = chunk()
        assert all(c.article_no or c.char_len >= 30 for c in chunks)


class TestMerging:
    def test_short_articles_are_not_merged_by_default(self):
        chunks = chunk(min_chars=400)
        headings = [c.heading for c in chunks]
        assert len(headings) == len(set(headings))

    def test_merge_short_articles_when_enabled(self):
        default = chunk(min_chars=400)
        merged = chunk(min_chars=400, merge_short_articles=True)
        assert len(merged) < len(default)


class TestChunkMetadata:
    def test_ids_are_unique_and_ordered(self):
        chunks = chunk()
        assert [c.order for c in chunks] == list(range(len(chunks)))
        assert len({c.chunk_id for c in chunks}) == len(chunks)

    def test_embed_text_carries_context(self):
        target = by_article(chunk(), "12")[0]
        assert "차차 약관" in target.embed_text
        assert "제12조" in target.embed_text

    def test_citation_is_human_readable(self):
        target = by_article(chunk(), "12")[0]
        assert "제12조(청약철회 및 환불)" in target.citation
        assert "p.1" in target.citation


class TestConfigValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_chars": 50},
            {"max_chars": 300, "min_chars": 300},
            {"max_chars": 300, "overlap_chars": 400},
        ],
    )
    def test_rejects_bad_config(self, kwargs):
        with pytest.raises(ValueError):
            ChunkConfig(**kwargs)
