"""HTML / DOCX / 텍스트 로더와 형식 디스패처 테스트."""

import pytest

from terms_rag.chunker import ChunkConfig
from terms_rag.doc_chunker import DocumentChunker, chunk_document, detect_kind
from terms_rag.docx_loader import load_docx
from terms_rag.html_loader import load_html, parse_html
from terms_rag.loaders import load_document

REPORT_HTML = """<!doctype html>
<html lang="ko"><head><title>서비스 품질 피드백 보고서</title>
<style>body { color: red; }</style>
<script>console.log("무시되어야 함");</script>
</head><body>
<h1>서비스 품질 피드백 보고서</h1>
<p>본 보고서는 테스트 결과를 정리한 문서입니다.</p>
<h2>1. 핵심 문제점</h2>
<h3>1-1. 출처 우선순위</h3>
<p>보험사명을 질문 앞에 두어도 타 보험사 자료가 먼저 노출되었습니다.</p>
<ul><li>회사명 필터링 미적용</li><li>출처 랭킹 불안정</li></ul>
<h2>2. 비교표</h2>
<table>
  <tr><th>항목</th><th>실제</th><th>기대</th></tr>
  <tr><td>원칙 설명</td><td>없음</td><td>표준약관 기준 설명</td></tr>
</table>
<p>&lt;주의&gt; 특수문자도 그대로 살아야 합니다.</p>
</body></html>
"""

TERMS_HTML = """<html><head><title>이용약관</title></head><body>
<h1>이용약관</h1>
<p>제1조(목적) 이 약관은 서비스 이용조건을 정합니다.</p>
<p>제2조(정의) ① "회원"이란 가입한 자를 말합니다.</p>
<p>제3조(해지) 회원은 언제든지 해지할 수 있습니다.</p>
</body></html>
"""


class TestHtmlLoader:
    def test_title_from_tag(self):
        assert parse_html(REPORT_HTML).title == "서비스 품질 피드백 보고서"

    def test_headings_carry_levels(self):
        doc = parse_html(REPORT_HTML)
        levels = {line.text: line.heading_level for line in doc.lines if line.heading_level}
        assert levels["1. 핵심 문제점"] == 2
        assert levels["1-1. 출처 우선순위"] == 3

    def test_script_and_style_are_dropped(self):
        text = parse_html(REPORT_HTML).text
        assert "console.log" not in text and "color: red" not in text

    def test_list_items_are_marked(self):
        assert "- 회사명 필터링 미적용" in parse_html(REPORT_HTML).text

    def test_table_rows_are_flattened(self):
        text = parse_html(REPORT_HTML).text
        assert "항목 | 실제 | 기대" in text
        assert "원칙 설명 | 없음 | 표준약관 기준 설명" in text

    def test_entities_are_unescaped(self):
        assert "<주의> 특수문자도" in parse_html(REPORT_HTML).text

    def test_empty_markup_rejected(self):
        with pytest.raises(ValueError):
            parse_html("<html><body></body></html>")

    def test_reads_from_disk(self, tmp_path):
        path = tmp_path / "report.html"
        path.write_text(REPORT_HTML, encoding="utf-8")
        assert load_html(path).title == "서비스 품질 피드백 보고서"


@pytest.fixture
def sample_docx(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("밸루가 품질 피드백 보고서")
    document.add_heading("1. 개요", level=1)
    document.add_paragraph("테스트 결과를 정리했습니다.")
    document.add_heading("2. 문제점", level=1)
    document.add_heading("2-1. 편향 참조", level=2)
    document.add_paragraph("단일 상품 약관만 근거로 제시했습니다.")
    document.add_paragraph("선택 기준이 불투명함", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "항목"
    table.cell(0, 1).text = "결과"
    table.cell(1, 0).text = "원칙 설명"
    table.cell(1, 1).text = "없음"
    path = tmp_path / "report.docx"
    document.save(str(path))
    return path


class TestDocxLoader:
    def test_heading_levels(self, sample_docx):
        doc = load_docx(sample_docx)
        levels = {line.text: line.heading_level for line in doc.lines if line.heading_level}
        assert levels["1. 개요"] == 1
        assert levels["2-1. 편향 참조"] == 2

    def test_cover_line_becomes_title(self, sample_docx):
        assert load_docx(sample_docx).title == "밸루가 품질 피드백 보고서"

    def test_list_and_table(self, sample_docx):
        text = load_docx(sample_docx).text
        assert "- 선택 기준이 불투명함" in text
        assert "항목 | 결과" in text
        assert "원칙 설명 | 없음" in text


class TestDispatcher:
    def test_routes_by_suffix(self, tmp_path, sample_docx):
        html = tmp_path / "a.html"
        html.write_text(REPORT_HTML, encoding="utf-8")
        text = tmp_path / "b.md"
        text.write_text("제1조(목적) 목적을 정합니다.", encoding="utf-8")
        assert load_document(html).title == "서비스 품질 피드백 보고서"
        assert load_document(sample_docx).lines
        assert load_document(text).lines

    def test_hwp_and_doc_give_actionable_errors(self, tmp_path):
        for name, hint in (("x.hwp", "PDF"), ("x.doc", ".docx")):
            path = tmp_path / name
            path.write_bytes(b"0")
            with pytest.raises(ValueError, match=hint):
                load_document(path)

    def test_unknown_suffix(self, tmp_path):
        path = tmp_path / "x.rtf"
        path.write_bytes(b"0")
        with pytest.raises(ValueError, match="지원하지 않는"):
            load_document(path)


class TestKindDetection:
    def test_report_is_document(self):
        assert detect_kind(parse_html(REPORT_HTML)) == "문서"

    def test_html_terms_still_use_article_path(self):
        doc = parse_html(TERMS_HTML)
        assert detect_kind(doc) == "약관"
        chunks = chunk_document(doc)
        assert {c.article_no for c in chunks} == {"1", "2", "3"}

    def test_dispatch_picks_the_right_chunker(self):
        """약관은 원본 조문 청킹기가, 문서는 문서 청킹기가 처리한다."""
        terms = chunk_document(parse_html(TERMS_HTML))
        report = chunk_document(parse_html(REPORT_HTML))
        assert all(c.doc_kind == "약관" and c.article_no for c in terms)
        assert all(c.doc_kind == "문서" and not c.article_no for c in report)

    def test_explicit_kind_wins(self):
        doc = parse_html(TERMS_HTML)
        doc.kind = "문서"
        assert detect_kind(doc) == "문서"


class TestDocumentChunking:
    @pytest.fixture
    def chunks(self):
        return DocumentChunker(ChunkConfig(max_chars=400, min_chars=20)).chunk(parse_html(REPORT_HTML))

    def test_headings_become_breadcrumbs(self, chunks):
        headings = [c.heading for c in chunks]
        assert "1. 핵심 문제점 > 1-1. 출처 우선순위" in headings
        assert "2. 비교표" in headings

    def test_document_title_is_not_repeated_in_heading(self, chunks):
        assert all(not c.heading.startswith("서비스 품질 피드백 보고서") for c in chunks)

    def test_chunks_are_marked_as_documents(self, chunks):
        assert all(c.doc_kind == "문서" for c in chunks)
        assert all(c.article_no == "" for c in chunks)

    def test_heading_only_section_is_folded_into_its_subsection(self, chunks):
        # "1. 핵심 문제점" 은 본문이 없다 → 독립 청크로 남으면 안 된다
        assert "1. 핵심 문제점" not in [c.heading for c in chunks]

    def test_table_and_list_survive_chunking(self, chunks):
        joined = "\n".join(c.text for c in chunks)
        assert "항목 | 실제 | 기대" in joined
        assert "- 출처 랭킹 불안정" in joined

    def test_no_runt_chunks(self, chunks):
        assert all(c.char_len >= 30 for c in chunks)
