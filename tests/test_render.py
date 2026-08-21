"""LLM 컨텍스트용 렌더링 테스트."""

import json

import pytest

from conftest import SAMPLE_TERMS
from terms_rag.chunker import TermsChunker
from terms_rag.pdf_loader import load_text
from terms_rag.render import (
    count_tokens,
    estimate_tokens,
    filter_chunks,
    render,
    split_by_tokens,
)


@pytest.fixture
def chunks():
    return TermsChunker().chunk(load_text(SAMPLE_TERMS, title="차차 약관"))


class TestXml:
    def test_wraps_in_tags_with_numbered_sources(self, chunks):
        out = render(chunks, fmt="xml")
        assert "<약관 제목=\"차차 약관\"" in out
        assert out.rstrip().endswith("</약관>")
        assert '<조항 번호="1"' in out and '출처="' in out

    def test_includes_instructions_by_default(self, chunks):
        assert "추측하지" in render(chunks, fmt="xml")
        assert "추측하지" not in render(chunks, fmt="xml", instructions=False)

    def test_escapes_markup_in_attributes(self, chunks):
        out = render(chunks, fmt="xml")
        # 출처의 " > " 구분자가 태그로 오인되지 않아야 한다
        assert "&gt;" in out
        assert '출처="차차 약관 제2장 유료서비스 > ' not in out

    def test_article_and_section_attributes(self, chunks):
        out = render(chunks, fmt="xml")
        assert '조="제12조의2(정기결제의 중도 해지)"' in out
        assert '구분="부칙"' in out

    def test_body_text_survives_intact(self, chunks):
        out = render(chunks, fmt="xml")
        assert "① 회원은 결제일로부터 7일 이내에" in out
        assert "1. 회원의 책임 있는 사유로" in out


class TestOtherFormats:
    def test_markdown_has_numbered_headings(self, chunks):
        out = render(chunks, fmt="markdown")
        assert "## [1] " in out and "*출처: " in out

    def test_text_is_plain(self, chunks):
        out = render(chunks, fmt="text")
        assert "<" not in out.split("=" * 60)[1]
        assert "[1] " in out

    def test_jsonl_is_machine_readable(self, chunks):
        rows = [json.loads(line) for line in render(chunks, fmt="jsonl").splitlines()]
        assert len(rows) == len(chunks)
        assert rows[0]["chunk_id"]

    def test_unknown_format(self, chunks):
        with pytest.raises(ValueError):
            render(chunks, fmt="yaml")

    def test_empty_input(self):
        assert render([], fmt="xml") == ""


class TestFilter:
    def test_by_article(self, chunks):
        picked = filter_chunks(chunks, articles=["12", "12-2"])
        assert {c.article_no for c in picked} == {"12", "12-2"}

    def test_by_chapter(self, chunks):
        assert all(c.chapter_no == 1 for c in filter_chunks(chunks, chapter=1))

    def test_by_section(self, chunks):
        picked = filter_chunks(chunks, section="부칙")
        assert picked and all(c.section == "부칙" for c in picked)

    def test_no_filter_returns_everything(self, chunks):
        assert len(filter_chunks(chunks)) == len(chunks)


class TestTokens:
    def test_estimate_is_marked_inexact(self):
        count = estimate_tokens("환불 규정입니다.")
        assert count.tokens > 0 and count.exact is False
        assert "추정" in str(count)

    def test_count_falls_back_without_credentials(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1")  # 연결 실패 유도
        count = count_tokens("환불 규정입니다.", api_key="sk-invalid")
        assert count.tokens > 0 and count.exact is False


class TestSplit:
    def test_splits_into_batches_under_budget(self, chunks):
        batches = split_by_tokens(chunks, max_tokens=400, instructions=False)
        assert len(batches) > 1
        assert sum(len(b) for b in batches) == len(chunks)

    def test_keeps_articles_whole(self, chunks):
        for batch in split_by_tokens(chunks, max_tokens=400, instructions=False):
            assert all(isinstance(c.text, str) and c.text for c in batch)

    def test_single_batch_when_it_fits(self, chunks):
        assert len(split_by_tokens(chunks, max_tokens=100_000)) == 1

    def test_rejects_zero_budget(self, chunks):
        with pytest.raises(ValueError):
            split_by_tokens(chunks, max_tokens=0)
