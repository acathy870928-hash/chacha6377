"""PDF 로딩·정제 테스트. 실제 PDF 를 만들어 왕복시킨다."""

import subprocess
import sys
from pathlib import Path

import pytest

from terms_rag.chunker import TermsChunker
from terms_rag.pdf_loader import _normalize_line, _running_headers, load_pdf, load_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory):
    pytest.importorskip("reportlab", reason="샘플 PDF 생성에 reportlab 이 필요합니다")
    target = tmp_path_factory.mktemp("pdf") / "sample_terms.pdf"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_sample_terms_pdf.py"), str(target)],
        check=True,
        cwd=ROOT,
    )
    return target


class TestNormalization:
    def test_collapses_whitespace_and_dot_leaders(self):
        assert _normalize_line("  제1조   (목적) ........  3 ") == "제1조 (목적) 3"

    def test_strips_zero_width_characters(self):
        assert _normalize_line("환​불") == "환불"


class TestRunningHeaders:
    def test_detects_repeated_edge_lines(self):
        pages = [["차차 이용약관", f"본문 {i}", f"- {i} -"] for i in range(1, 6)]
        headers = _running_headers(pages)
        assert "차차 이용약관" in headers

    def test_ignores_short_documents(self):
        assert _running_headers([["머리말", "본문"], ["머리말", "본문"]]) == set()


class TestLoadPdf:
    def test_extracts_pages_and_text(self, sample_pdf):
        doc = load_pdf(sample_pdf)
        assert doc.page_count >= 2
        assert "청약철회" in doc.text
        assert doc.title.endswith("약관")

    def test_removes_running_header_and_page_numbers(self, sample_pdf):
        doc = load_pdf(sample_pdf)
        title_lines = [line for line in doc.lines if line.text == "차차 서비스 이용약관"]
        # 머리말은 모든 페이지에 찍히지만, 남는 건 1페이지 본문의 제목 한 줄뿐이어야 한다
        assert len(title_lines) <= 1
        assert all(line.page == 1 for line in title_lines)
        assert not any(line.text.strip("- ").isdigit() for line in doc.lines)

    def test_page_numbers_are_tracked(self, sample_pdf):
        chunks = TermsChunker().chunk(load_pdf(sample_pdf))
        assert {c.page_start for c in chunks} != {1}  # 여러 페이지에 걸쳐 있다
        assert all(1 <= c.page_start <= c.page_end for c in chunks)

    def test_chunks_cover_every_article(self, sample_pdf):
        chunks = TermsChunker().chunk(load_pdf(sample_pdf))
        found = {c.article_no for c in chunks}
        assert {"1", "2", "3", "4", "5", "12", "12-2", "13", "20", "21", "22"} <= found

    def test_missing_file(self, tmp_path):
        with pytest.raises(Exception):
            load_pdf(tmp_path / "없는파일.pdf")


class TestLoadText:
    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            load_text("   \n  ")

    def test_doc_id_is_stable(self):
        assert load_text("제1조(목적) 내용").doc_id == load_text("제1조(목적) 내용").doc_id


@pytest.fixture
def mixed_scan_pdf(tmp_path):
    """본문은 텍스트, 뒤쪽 두 페이지는 그림만 있는 PDF (실제 약관의 별표·부속서류 패턴)."""
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    path = tmp_path / "mixed.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("HYSMyeongJo-Medium", 11)
    pdf.drawString(60, 760, "제1조(목적)")
    pdf.drawString(60, 740, "이 약관은 보험계약에 관한 사항을 정합니다.")
    pdf.drawString(60, 720, "제2조(용어의 정의)")
    pdf.drawString(60, 700, "이 약관에서 사용하는 용어의 뜻은 다음과 같습니다.")
    pdf.showPage()
    for _ in range(2):  # 텍스트 없는 '스캔' 페이지
        pdf.rect(60, 600, 400, 150, fill=0)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def scan_only_pdf(tmp_path):
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for _ in range(3):
        pdf.rect(60, 600, 400, 150, fill=0)
        pdf.showPage()
    pdf.save()
    return path


class TestScanDetection:
    def test_full_scan_raises_with_ocr_guidance(self, scan_only_pdf):
        from terms_rag.pdf_loader import load_pdf

        with pytest.raises(ValueError, match="ocrmypdf"):
            load_pdf(scan_only_pdf)

    def test_partial_scan_is_reported_not_swallowed(self, mixed_scan_pdf):
        from terms_rag.pdf_loader import load_pdf, scan_warning

        doc = load_pdf(mixed_scan_pdf)
        assert doc.empty_pages == [2, 3]
        warning = scan_warning(doc)
        assert "3페이지 중 2페이지" in warning and "OCR" in warning

    def test_clean_pdf_has_no_warning(self, sample_pdf):
        from terms_rag.pdf_loader import load_pdf, scan_warning

        doc = load_pdf(sample_pdf)
        assert doc.empty_pages == []
        assert scan_warning(doc) == ""

    def test_ingest_surfaces_the_warning(self, mixed_scan_pdf, tmp_path, monkeypatch):
        from terms_rag.config import Settings
        from terms_rag.embedder import HashEmbedder
        from terms_rag.pipeline import ingest

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        settings = Settings.from_env(dotenv="/dev/null")
        messages: list[str] = []
        _store, reports = ingest(
            [mixed_scan_pdf],
            settings=settings,
            store_path=tmp_path / "store",
            embedder=HashEmbedder(),
            progress=messages.append,
        )
        assert any("[경고]" in m for m in messages)
        assert "스캔" in reports[0].warning
        assert "⚠" in str(reports[0])
