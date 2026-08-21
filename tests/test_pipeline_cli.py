"""수집 파이프라인과 CLI 통합 테스트 (임베딩은 오프라인 hash 백엔드 사용)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from terms_rag.cli import main
from terms_rag.config import Settings, load_dotenv
from terms_rag.embedder import HashEmbedder, get_embedder
from terms_rag.pipeline import chunk_pdf, collect_pdfs, export_chunks, ingest
from terms_rag.search import build_context, search
from terms_rag.store import VectorStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory):
    pytest.importorskip("reportlab", reason="샘플 PDF 생성에 reportlab 이 필요합니다")
    target = tmp_path_factory.mktemp("terms") / "sample_terms.pdf"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_sample_terms_pdf.py"), str(target)],
        check=True,
        cwd=ROOT,
    )
    return target


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    return Settings.from_env(dotenv="/dev/null")


class TestSettings:
    def test_defaults(self, settings):
        assert settings.embedding_provider == "hash"
        assert settings.chunk.max_chars == 1200

    def test_env_overrides_chunk_size(self, monkeypatch):
        monkeypatch.setenv("CHUNK_MAX_CHARS", "800")
        assert Settings.from_env(dotenv="/dev/null").chunk.max_chars == 800

    def test_bad_int_env(self, monkeypatch):
        monkeypatch.setenv("CHUNK_MAX_CHARS", "여덟백")
        with pytest.raises(ValueError):
            Settings.from_env(dotenv="/dev/null")

    def test_dotenv_does_not_override_existing_env(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("EMBEDDING_PROVIDER=openai\n", encoding="utf-8")
        monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
        load_dotenv(env_file)
        assert Settings.from_env(dotenv=env_file).embedding_provider == "hash"

    def test_unknown_provider(self, settings):
        settings.embedding_provider = "없는제공자"
        with pytest.raises(ValueError):
            get_embedder(settings)


class TestCollect:
    def test_directory_scan(self, sample_pdf):
        assert collect_pdfs([sample_pdf.parent]) == [sample_pdf]

    def test_missing_path(self):
        with pytest.raises(FileNotFoundError):
            collect_pdfs(["없는경로"])


class TestIngest:
    def test_ingest_then_search(self, sample_pdf, tmp_path, settings):
        store, reports = ingest(
            [sample_pdf], settings=settings, store_path=tmp_path / "store", embedder=HashEmbedder()
        )
        assert len(reports) == 1
        assert reports[0].chunks == len(store)
        assert (tmp_path / "store" / "chunks.jsonl").exists()

        hits = search("청약철회와 환불", store=store, embedder=HashEmbedder(), settings=settings, top_k=3)
        assert hits[0].chunk.article_no == "12"
        assert "제12조" in build_context(hits)

    def test_reingest_is_idempotent(self, sample_pdf, tmp_path, settings):
        path = tmp_path / "store"
        first, _ = ingest([sample_pdf], settings=settings, store_path=path, embedder=HashEmbedder())
        second, _ = ingest([sample_pdf], settings=settings, store_path=path, embedder=HashEmbedder())
        assert len(second) == len(first)

    def test_search_rejects_model_mismatch(self, sample_pdf, tmp_path, settings):
        store, _ = ingest([sample_pdf], settings=settings, store_path=tmp_path / "s", embedder=HashEmbedder())
        with pytest.raises(ValueError, match="인덱스"):
            search("환불", store=store, embedder=HashEmbedder(dim=64), settings=settings)

    def test_search_on_empty_store(self, tmp_path, settings):
        with pytest.raises(ValueError, match="비어"):
            search("환불", store=VectorStore(tmp_path / "empty"), settings=settings)

    def test_no_pdf_found(self, tmp_path, settings):
        with pytest.raises(ValueError):
            ingest([tmp_path], settings=settings, store_path=tmp_path / "s", embedder=HashEmbedder())


class TestExport:
    def test_jsonl_roundtrip(self, sample_pdf, tmp_path):
        chunks = chunk_pdf(sample_pdf)
        out = export_chunks(chunks, tmp_path / "chunks.jsonl")
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == len(chunks)
        assert rows[0]["heading"] and rows[0]["page_start"] >= 1


class TestCli:
    def test_chunk_command(self, sample_pdf, tmp_path, capsys, settings):
        assert main(["chunk", str(sample_pdf), "--out", str(tmp_path / "c.jsonl")]) == 0
        assert "청크" in capsys.readouterr().out
        assert (tmp_path / "c.jsonl").exists()

    def test_ingest_search_info_flow(self, sample_pdf, tmp_path, capsys, settings):
        store = str(tmp_path / "store")
        assert main(["ingest", str(sample_pdf), "--store", store]) == 0
        assert main(["info", "--store", store]) == 0
        assert "hash" in capsys.readouterr().out

        assert main(["search", "환불 기한", "--store", store, "-k", "3"]) == 0
        assert "제12조" in capsys.readouterr().out

    def test_lexical_only_search_needs_no_embedder(self, sample_pdf, tmp_path, capsys, settings):
        store = str(tmp_path / "store")
        main(["ingest", str(sample_pdf), "--store", store])
        capsys.readouterr()
        assert main(["search", "청약철회", "--store", store, "--lexical-only", "--full"]) == 0
        assert "제12조" in capsys.readouterr().out

    def test_info_on_empty_store(self, tmp_path, capsys, settings):
        assert main(["info", "--store", str(tmp_path / "none")]) == 0
        assert "비어" in capsys.readouterr().out

    def test_errors_are_reported_not_raised(self, tmp_path, capsys, settings):
        assert main(["chunk", str(tmp_path / "없다.pdf")]) == 1
        assert "오류" in capsys.readouterr().err


class TestAnswer:
    """답변 생성은 실제 API 호출 없이 메시지 계약만 검증한다."""

    def _fake_message(self, stop_reason="end_turn", text="환불은 3영업일 이내입니다. [1]"):
        class Block:
            type = "text"

            def __init__(self, text):
                self.text = text

        class Message:
            def __init__(self):
                self.stop_reason = stop_reason
                self.content = [Block(text)]

        return Message()

    def test_builds_numbered_context(self, sample_pdf, tmp_path, settings):
        store, _ = ingest([sample_pdf], settings=settings, store_path=tmp_path / "s", embedder=HashEmbedder())
        hits = search("환불", store=store, embedder=HashEmbedder(), settings=settings, top_k=2)
        context = build_context(hits)
        assert context.startswith("[1] 출처:")
        assert "[2] 출처:" in context

    def test_no_hits_short_circuits(self, settings):
        pytest.importorskip("anthropic")
        from terms_rag.search import answer

        result = answer("환불", [], settings=settings)
        assert result.hits == [] and "찾지 못했" in result.text

    def test_refusal_is_surfaced(self, monkeypatch, sample_pdf, tmp_path, settings):
        pytest.importorskip("anthropic")
        import terms_rag.search as search_module

        store, _ = ingest([sample_pdf], settings=settings, store_path=tmp_path / "s", embedder=HashEmbedder())
        hits = search("환불", store=store, embedder=HashEmbedder(), settings=settings, top_k=1)

        monkeypatch.setattr(__import__("anthropic"), "Anthropic", lambda **kw: object())
        monkeypatch.setattr(search_module, "_create_message", lambda *a, **k: self._fake_message("refusal"))
        result = search_module.answer("환불", hits, settings=settings)
        assert result.refused is True

    def test_answer_text_and_sources(self, monkeypatch, sample_pdf, tmp_path, settings):
        pytest.importorskip("anthropic")
        import terms_rag.search as search_module

        store, _ = ingest([sample_pdf], settings=settings, store_path=tmp_path / "s", embedder=HashEmbedder())
        hits = search("환불", store=store, embedder=HashEmbedder(), settings=settings, top_k=2)

        monkeypatch.setattr(__import__("anthropic"), "Anthropic", lambda **kw: object())
        monkeypatch.setattr(search_module, "_create_message", lambda *a, **k: self._fake_message())
        result = search_module.answer("환불", hits, settings=settings)
        assert "3영업일" in result.text
        assert result.sources()[0].startswith("[1] ")


class TestExportCli:
    def test_export_from_pdf_to_stdout(self, sample_pdf, capsys, settings):
        assert main(["export", str(sample_pdf)]) == 0
        captured = capsys.readouterr()
        assert captured.out.strip().endswith("</약관>")
        assert "토큰" in captured.err  # 통계는 stderr 로 (파이프 오염 방지)

    def test_export_filters_by_article(self, sample_pdf, capsys, settings):
        assert main(["export", str(sample_pdf), "--article", "12", "--no-instructions"]) == 0
        out = capsys.readouterr().out
        assert "제12조(청약철회 및 환불)" in out
        assert "제1조(목적)" not in out
        assert "추측하지" not in out

    def test_export_to_file(self, sample_pdf, tmp_path, settings):
        target = tmp_path / "context.md"
        assert main(["export", str(sample_pdf), "--format", "markdown", "--out", str(target)]) == 0
        assert "## [1] " in target.read_text(encoding="utf-8")

    def test_export_splits_by_token_budget(self, sample_pdf, tmp_path, settings):
        target = tmp_path / "ctx.xml"
        assert main(["export", str(sample_pdf), "--max-tokens", "800", "--out", str(target)]) == 0
        parts = sorted(tmp_path.glob("ctx.*.xml"))
        assert len(parts) > 1
        assert all(p.read_text(encoding="utf-8").rstrip().endswith("</약관>") for p in parts)

    def test_export_from_index_with_query(self, sample_pdf, tmp_path, capsys, settings):
        store = str(tmp_path / "store")
        main(["ingest", str(sample_pdf), "--store", store])
        capsys.readouterr()
        assert main(["export", "--query", "청약철회", "-k", "2", "--store", store, "--format", "text"]) == 0
        assert "제12조" in capsys.readouterr().out

    def test_query_with_pdf_is_rejected(self, sample_pdf, capsys, settings):
        assert main(["export", str(sample_pdf), "--query", "환불"]) == 1
        assert "오류" in capsys.readouterr().err

    def test_export_without_index_or_pdf(self, tmp_path, capsys, settings):
        assert main(["export", "--store", str(tmp_path / "none")]) == 1
        assert "비어" in capsys.readouterr().err

    def test_empty_filter_is_an_error(self, sample_pdf, capsys, settings):
        assert main(["export", str(sample_pdf), "--article", "999"]) == 1
        assert "내보낼 조항이 없습니다" in capsys.readouterr().err

    def test_search_can_emit_llm_format(self, sample_pdf, tmp_path, capsys, settings):
        store = str(tmp_path / "store")
        main(["ingest", str(sample_pdf), "--store", store])
        capsys.readouterr()
        assert main(["search", "면책", "--store", store, "-k", "1", "--format", "xml"]) == 0
        assert "<조항 번호=\"1\"" in capsys.readouterr().out
