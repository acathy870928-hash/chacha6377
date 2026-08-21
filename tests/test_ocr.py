"""OCR 모듈 테스트.

이 환경에는 ocrmypdf/tesseract 가 없으므로 외부 명령 실행부는 대역으로 갈아끼우고,
그 위의 로직(대상 페이지 선정, 기존 텍스트 재사용, 페이지 표지 보존, 청킹 연결)을 검증한다.
"""

import pytest

from terms_rag import ocr as ocr_module
from terms_rag.chunker import TermsChunker
from terms_rag.loaders import load_document
from terms_rag.ocr import (
    OCR_SUFFIX,
    available_backends,
    load_ocr_text,
    needs_ocr,
    parse_pages,
    resolve_backend,
    run_ocr,
    write_ocr_text,
)

TERMS_PAGE_1 = [
    "제1조(목적)",
    "이 약관은 보험계약에 관한 사항을 정합니다.",
]
SCANNED_PAGE_TEXT = "\n".join(
    [
        "제2조(보험금의 지급사유)",
        "① 회사는 피보험자에게 다음 각 호의 사유가 발생한 때 보험금을 지급합니다.",
        "1. 보험기간 중 사망한 경우",
        "2. 장해분류표에서 정한 장해지급률에 해당하는 장해상태가 된 경우",
    ]
)
SCANNED_PAGE_2_TEXT = "\n".join(
    [
        "제3조(보험금을 지급하지 않는 사유)",
        "① 회사는 다음 각 호의 어느 하나로 보험금 지급사유가 발생한 때에는 지급하지 않습니다.",
        "1. 피보험자가 고의로 자신을 해친 경우",
    ]
)


def _scanned_text(page_no: int) -> str:
    return SCANNED_PAGE_TEXT if page_no == 2 else SCANNED_PAGE_2_TEXT


def _build_pdf(path, *, text_pages, blank_pages):
    """앞쪽은 텍스트, 뒤쪽은 그림만 있는 PDF (실제 약관의 별표·부속서류 패턴)."""
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for lines in text_pages:
        pdf.setFont("HYSMyeongJo-Medium", 11)
        y = 760
        for line in lines:
            pdf.drawString(60, y, line)
            y -= 18
        pdf.showPage()
    for _ in range(blank_pages):
        pdf.rect(60, 600, 400, 150, fill=0)
        pdf.showPage()
    pdf.save()
    return path


@pytest.fixture
def mixed_pdf(tmp_path):
    return _build_pdf(tmp_path / "약관.pdf", text_pages=[TERMS_PAGE_1], blank_pages=2)


@pytest.fixture
def clean_pdf(tmp_path):
    return _build_pdf(tmp_path / "clean.pdf", text_pages=[TERMS_PAGE_1], blank_pages=0)


@pytest.fixture
def fake_ocr(monkeypatch):
    """tesseract 백엔드를 대역으로 갈아끼운다. 요청된 페이지만 인식한 척한다."""
    calls: dict[str, list[int]] = {}

    def _fake(path, *, lang, pages, dpi, progress):
        calls["pages"] = list(pages)
        calls["lang"] = lang
        return {no: _scanned_text(no) for no in pages}

    monkeypatch.setattr(ocr_module, "_run_tesseract", _fake)
    monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["tesseract"])
    return calls


class TestPageRange:
    @pytest.mark.parametrize(
        "spec, expected",
        [
            (None, [1, 2, 3, 4, 5]),
            ("2", [2]),
            ("1-3", [1, 2, 3]),
            ("1-2,5", [1, 2, 5]),
            ("3-3", [3]),
            ("4-99", [4, 5]),  # 문서 밖은 잘라낸다
            ("2,2,1", [1, 2]),  # 중복 제거 + 정렬
        ],
    )
    def test_parses(self, spec, expected):
        assert parse_pages(spec, 5) == expected

    @pytest.mark.parametrize("spec", ["5-1", "가-나", "abc", "99"])
    def test_rejects_bad_specs(self, spec):
        with pytest.raises(ValueError):
            parse_pages(spec, 5)


class TestNeedsOcr:
    def test_clean_pdf_needs_nothing(self, clean_pdf):
        need = needs_ocr(clean_pdf)
        assert need.needed is False and need.empty_pages == []
        assert "OCR 불필요" in str(need)

    def test_mixed_pdf_lists_scanned_pages(self, mixed_pdf):
        need = needs_ocr(mixed_pdf)
        assert need.empty_pages == [2, 3]
        assert need.fully_scanned is False
        assert need.ratio == pytest.approx(2 / 3)
        assert "일부만 스캔" in str(need)

    def test_fully_scanned(self, tmp_path):
        path = _build_pdf(tmp_path / "scan.pdf", text_pages=[], blank_pages=3)
        need = needs_ocr(path)
        assert need.fully_scanned is True
        assert "전체가 스캔" in str(need)


class TestBackendResolution:
    def test_lists_what_exists(self, monkeypatch):
        monkeypatch.setattr(ocr_module.shutil, "which", lambda name: "/usr/bin/" + name)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert available_backends() == ["ocrmypdf", "tesseract"]

    def test_claude_needs_only_a_key(self, monkeypatch):
        monkeypatch.setattr(ocr_module.shutil, "which", lambda name: None)
        assert available_backends(api_key="sk-test") == ["claude"]

    def test_auto_prefers_ocrmypdf(self, monkeypatch):
        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["ocrmypdf", "tesseract"])
        assert resolve_backend("auto") == "ocrmypdf"

    def test_explicit_missing_backend_gives_install_hint(self, monkeypatch):
        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["claude"])
        with pytest.raises(RuntimeError, match="apt install"):
            resolve_backend("ocrmypdf")

    def test_unknown_backend(self):
        with pytest.raises(ValueError):
            resolve_backend("abbyy")

    def test_no_backend_at_all(self, monkeypatch):
        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: [])
        with pytest.raises(RuntimeError, match="쓸 수 있는 OCR 백엔드가 없습니다"):
            resolve_backend("auto")


class TestTextFormat:
    def test_roundtrip_preserves_page_numbers(self, tmp_path):
        path = write_ocr_text(tmp_path / f"약관{OCR_SUFFIX}", {1: "제1조(목적)\n본문", 4: "제2조(정의)\n본문"})
        doc = load_ocr_text(path)
        assert [(line.text, line.page) for line in doc.lines][0] == ("제1조(목적)", 1)
        assert doc.lines[-1].page == 4
        assert doc.page_count == 4

    def test_empty_ocr_text_is_rejected(self, tmp_path):
        path = tmp_path / f"빈{OCR_SUFFIX}"
        path.write_text("<<<PAGE 1>>>\n\n", encoding="utf-8")
        with pytest.raises(ValueError, match="비어"):
            load_ocr_text(path)

    def test_loader_routes_ocr_text_by_name(self, tmp_path):
        path = write_ocr_text(tmp_path / f"약관{OCR_SUFFIX}", {7: "제3조(해지) 본문입니다."})
        assert load_document(path).lines[0].page == 7  # 일반 .txt 로 읽으면 1 이 된다

    def test_page_marks_are_split(self):
        text = "<<<PAGE 5>>>\n다섯째 장\n<<<PAGE 6>>>\n여섯째 장"
        assert ocr_module._split_page_marks(text, [5, 6]) == {5: "다섯째 장", 6: "여섯째 장"}

    def test_missing_page_marks_fall_back_to_first_page(self):
        assert ocr_module._split_page_marks("표지 없이 온 텍스트", [9]) == {9: "표지 없이 온 텍스트"}


class TestRunOcr:
    def test_only_scanned_pages_are_sent_to_the_backend(self, mixed_pdf, fake_ocr, tmp_path):
        run_ocr(mixed_pdf, backend="tesseract", out_dir=tmp_path / "out")
        assert fake_ocr["pages"] == [2, 3]  # 1페이지는 텍스트가 있으므로 건드리지 않는다

    def test_existing_text_is_kept(self, mixed_pdf, fake_ocr, tmp_path):
        result = run_ocr(mixed_pdf, backend="tesseract", out_dir=tmp_path / "out")
        assert result.pages == 3
        assert "제1조(목적)" in result.page_texts[1]  # 원래 텍스트 레이어
        assert "제2조(보험금의 지급사유)" in result.page_texts[2]  # OCR 결과

    def test_page_range_limits_the_output(self, mixed_pdf, fake_ocr, tmp_path):
        result = run_ocr(mixed_pdf, backend="tesseract", pages="1-2", out_dir=tmp_path / "out")
        assert sorted(result.page_texts) == [1, 2]
        assert fake_ocr["pages"] == [2]

    def test_writes_text_file_next_to_source_by_default(self, mixed_pdf, fake_ocr):
        result = run_ocr(mixed_pdf, backend="tesseract")
        assert result.text_path == mixed_pdf.parent / f"{mixed_pdf.stem}{OCR_SUFFIX}"
        assert result.text_path.exists()
        assert "OCR 완료 [tesseract]" in str(result)

    def test_refuses_when_nothing_needs_ocr(self, clean_pdf, fake_ocr, tmp_path):
        with pytest.raises(ValueError, match="OCR 이 필요 없습니다"):
            run_ocr(clean_pdf, backend="tesseract", out_dir=tmp_path)

    def test_missing_file(self, tmp_path, fake_ocr):
        with pytest.raises(FileNotFoundError):
            run_ocr(tmp_path / "없다.pdf", backend="tesseract")

    def test_empty_result_is_an_error(self, mixed_pdf, monkeypatch, tmp_path):
        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["tesseract"])
        monkeypatch.setattr(
            ocr_module, "_run_tesseract", lambda path, **kw: {no: "   " for no in kw["pages"]}
        )
        # 1페이지 텍스트는 남으므로 전부 비우려면 텍스트 페이지까지 대상으로 잡아야 한다
        monkeypatch.setattr(ocr_module, "_extract_page", lambda path, no: "")
        with pytest.raises(RuntimeError, match="비어 있습니다"):
            run_ocr(mixed_pdf, backend="tesseract", out_dir=tmp_path / "out")


class TestClaudeBackend:
    def test_transcribes_batches_and_keeps_page_numbers(self, mixed_pdf, monkeypatch, tmp_path):
        pytest.importorskip("anthropic")
        seen: list[int] = []

        class Block:
            type = "text"

            def __init__(self, text):
                self.text = text

        class Message:
            stop_reason = "end_turn"

            def __init__(self, text):
                self.content = [Block(text)]

        def fake_transcribe(client, *, model, payload, first_page):
            seen.append(first_page)
            return Message(f"<<<PAGE {first_page}>>>\n{_scanned_text(first_page)}")

        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["claude"])
        monkeypatch.setattr(ocr_module, "_transcribe", fake_transcribe)
        monkeypatch.setattr(
            __import__("anthropic"), "Anthropic", lambda **kw: object()
        )

        result = run_ocr(
            mixed_pdf, backend="claude", api_key="sk-test", batch_pages=1, out_dir=tmp_path / "out"
        )
        assert seen == [2, 3]
        assert "제3조" in result.page_texts[3]

    def test_refusal_is_raised(self, mixed_pdf, monkeypatch, tmp_path):
        pytest.importorskip("anthropic")

        class Refused:
            stop_reason = "refusal"
            content = []

        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: ["claude"])
        monkeypatch.setattr(ocr_module, "_transcribe", lambda *a, **k: Refused())
        monkeypatch.setattr(__import__("anthropic"), "Anthropic", lambda **kw: object())
        with pytest.raises(RuntimeError, match="거절"):
            run_ocr(mixed_pdf, backend="claude", api_key="sk-test", out_dir=tmp_path / "out")


class TestOcrToChunking:
    """OCR → 청킹까지 이어지는지. 쪽번호가 인용에 살아남아야 한다."""

    def test_chunks_carry_the_original_page_numbers(self, mixed_pdf, fake_ocr, tmp_path):
        result = run_ocr(mixed_pdf, backend="tesseract", out_dir=tmp_path / "out")
        document = load_document(result.text_path)
        chunks = TermsChunker().chunk(document)

        by_article = {c.article_no: c for c in chunks}
        assert by_article["1"].page_start == 1
        assert by_article["2"].page_start == 2  # 스캔이었던 페이지
        assert "p.2" in by_article["2"].citation

    def test_article_structure_survives_ocr(self, mixed_pdf, fake_ocr, tmp_path):
        result = run_ocr(mixed_pdf, backend="tesseract", out_dir=tmp_path / "out")
        chunks = TermsChunker().chunk(load_document(result.text_path))
        target = next(c for c in chunks if c.article_no == "2")
        assert target.article_title == "보험금의 지급사유"
        assert "1. 보험기간 중 사망한 경우" in target.text
        assert target.paragraph_nos == [1]


class TestOcrCli:
    def test_check_reports_without_running(self, mixed_pdf, capsys, monkeypatch):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        assert main(["ocr", str(mixed_pdf), "--check"]) == 0
        out = capsys.readouterr().out
        assert "일부만 스캔" in out and "사용 가능한 백엔드" in out
        assert not (mixed_pdf.parent / f"{mixed_pdf.stem}{OCR_SUFFIX}").exists()

    def test_clean_pdf_short_circuits(self, clean_pdf, capsys, monkeypatch):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        assert main(["ocr", str(clean_pdf)]) == 0
        assert "OCR 없이 바로 청킹" in capsys.readouterr().out

    def test_runs_and_chunks(self, mixed_pdf, fake_ocr, capsys, monkeypatch, tmp_path):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        code = main(
            ["ocr", str(mixed_pdf), "--backend", "tesseract", "--out-dir", str(tmp_path / "o"), "--chunk"]
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "OCR 완료 [tesseract]" in out
        assert "제2조(보험금의 지급사유)" in out

    def test_no_backend_is_a_clean_error(self, mixed_pdf, monkeypatch, capsys):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        monkeypatch.setattr(ocr_module, "available_backends", lambda **kw: [])
        assert main(["ocr", str(mixed_pdf)]) == 1
        assert "쓸 수 있는 OCR 백엔드가 없습니다" in capsys.readouterr().err

    def test_ingest_auto_ocr(self, mixed_pdf, fake_ocr, tmp_path, monkeypatch, capsys):
        from terms_rag.cli import main

        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        code = main(["ingest", str(mixed_pdf), "--ocr", "auto", "--store", str(tmp_path / "store")])
        out = capsys.readouterr().out
        assert code == 0
        assert "[OCR 필요]" in out and "OCR 완료" in out

        from terms_rag.store import VectorStore

        store = VectorStore.load(tmp_path / "store")
        assert {c.article_no for c in store.chunks} >= {"1", "2", "3"}
