"""수집 파이프라인: PDF → 청킹 → 임베딩 → 벡터스토어."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .chunker import ChunkConfig
from .doc_chunker import chunk_document
from .concepts import extract_definitions, index_entries
from .config import Settings
from .embedder import Embedder, get_embedder
from .models import Chunk
from .loaders import SUFFIXES, load_document
from .ocr import needs_ocr, run_ocr
from .pdf_loader import load_text, scan_warning
from .store import VectorStore


@dataclass
class IngestReport:
    doc_id: str
    title: str
    source: str
    pages: int
    chunks: int
    avg_chars: float
    max_chars: int
    kind: str = "약관"
    warning: str = ""

    def __str__(self) -> str:
        return (
            f"{self.title}  ({Path(self.source).name})\n"
            f"  문서 ID : {self.doc_id}  [{self.kind}]\n"
            f"  페이지  : {self.pages}\n"
            f"  청크    : {self.chunks}개 (평균 {self.avg_chars:.0f}자, 최대 {self.max_chars}자)"
            + (f"\n  ⚠ {self.warning}" if self.warning else "")
        )


def collect_documents(inputs: Sequence[str | Path]) -> list[Path]:
    """파일/디렉터리 목록에서 처리 가능한 문서 경로를 모은다(PDF/HTML/DOCX/텍스트)."""
    paths: list[Path] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            paths.extend(
                sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUFFIXES)
            )
        elif path.is_file():
            paths.append(path)
        else:
            raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")
    return paths


# 이전 이름 유지 (PDF 전용이던 시절의 호출부 호환)
collect_pdfs = collect_documents


def chunk_file(path: str | Path, config: ChunkConfig | None = None, *, title: str | None = None) -> list[Chunk]:
    """임베딩 없이 청킹만 수행한다(청킹 결과 검수용). PDF/HTML/DOCX/텍스트 모두 지원."""
    document = load_document(path, title=title)
    return chunk_document(document, config)


chunk_pdf = chunk_file


def chunk_plain_text(text: str, config: ChunkConfig | None = None, *, title: str = "약관") -> list[Chunk]:
    return chunk_document(load_text(text, title=title), config)


def ingest(
    inputs: Sequence[str | Path],
    *,
    settings: Settings | None = None,
    store_path: str | Path | None = None,
    embedder: Embedder | None = None,
    ocr: str = "off",
    ocr_backend: str = "auto",
    ocr_lang: str = "kor+eng",
    progress: Callable[[str], None] = lambda _msg: None,
) -> tuple[VectorStore, list[IngestReport]]:
    """PDF 들을 청킹·임베딩해 벡터스토어에 넣는다. 같은 문서를 다시 넣으면 교체된다."""
    settings = settings or Settings.from_env()
    embedder = embedder or get_embedder(settings)
    store = VectorStore.load(store_path or settings.store_path)

    documents = collect_documents(inputs)
    if not documents:
        raise ValueError(
            "처리할 문서가 없습니다. data/terms/ 에 PDF·HTML·DOCX 를 넣어 주세요."
        )

    reports: list[IngestReport] = []

    for path in documents:
        progress(f"[읽는 중] {path}")
        if ocr == "auto" and path.suffix.lower() == ".pdf":
            path = _maybe_ocr(path, backend=ocr_backend, lang=ocr_lang, settings=settings, progress=progress)
        document = load_document(path)
        warning = scan_warning(document)
        if warning:
            progress(f"[경고] {warning}")
        chunks = chunk_document(document, settings.chunk)
        if not chunks:
            progress(f"[건너뜀] {path}: 청크가 생성되지 않았습니다.")
            continue

        progress(f"[임베딩] {document.title}: 청크 {len(chunks)}개 → {embedder.provider}/{embedder.model}")
        vectors = embedder.embed_documents([c.embed_text for c in chunks])
        store.upsert(chunks, vectors, provider=embedder.provider, model=embedder.model)
        store.add_concepts(index_entries(extract_definitions(chunks)), doc_id=document.doc_id)

        lengths = [c.char_len for c in chunks]
        reports.append(
            IngestReport(
                doc_id=document.doc_id,
                title=document.title,
                source=str(path),
                pages=document.page_count,
                chunks=len(chunks),
                kind=chunks[0].doc_kind,
                warning=warning,
                avg_chars=sum(lengths) / len(lengths),
                max_chars=max(lengths),
            )
        )

    store.save()
    progress(f"[저장] {store.path} (총 청크 {len(store)}개)")
    return store, reports


def _maybe_ocr(path: Path, *, backend: str, lang: str, settings: Settings, progress) -> Path:
    """스캔 페이지가 있으면 OCR 해서 그 결과 경로를 돌려준다. 아니면 원본 그대로."""
    need = needs_ocr(path)
    if not need.needed:
        return path
    progress(f"[OCR 필요] {need}")
    result = run_ocr(
        path,
        backend=backend,
        lang=lang,
        api_key=settings.anthropic_api_key,
        model=settings.answer_model,
        progress=progress,
    )
    progress(f"[OCR] {result}")
    return result.text_path


def export_chunks(chunks: Iterable[Chunk], path: str | Path) -> Path:
    """청크를 JSONL 로 내보낸다."""
    import json

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    return out
