"""명령줄 인터페이스.

    python -m terms_rag chunk  data/terms/약관.pdf --preview
    python -m terms_rag ingest data/terms
    python -m terms_rag export data/terms/약관.pdf > 약관.xml
    python -m terms_rag search "환불은 며칠 안에 되나요?"
    python -m terms_rag ask    "환불은 며칠 안에 되나요?"
    python -m terms_rag info
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Settings
from .pipeline import chunk_pdf, export_chunks, ingest
from .render import FORMATS, count_tokens, estimate_tokens, filter_chunks, render, split_by_tokens
from .search import answer as generate_answer
from .search import search as run_search
from .store import VectorStore

BAR = "─" * 72


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store", default=None, help="벡터스토어 경로 (기본: .store)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="terms_rag", description="약관 PDF 청킹 · 임베딩 · 검색 파이프라인")
    sub = parser.add_subparsers(dest="command", required=True)

    p_chunk = sub.add_parser("chunk", help="청킹만 수행하고 결과를 확인한다(임베딩 없음)")
    p_chunk.add_argument("pdf", help="약관 PDF 경로")
    p_chunk.add_argument("--out", default=None, help="JSONL 로 저장할 경로")
    p_chunk.add_argument("--preview", action="store_true", help="청크 본문을 화면에 출력")
    p_chunk.add_argument("--max-chars", type=int, default=None)

    p_ingest = sub.add_parser("ingest", help="PDF 를 청킹·임베딩해 인덱스에 넣는다")
    p_ingest.add_argument("inputs", nargs="*", default=["data/terms"], help="PDF 파일 또는 디렉터리")
    _add_common(p_ingest)

    p_search = sub.add_parser("search", help="관련 조항을 검색한다")
    p_search.add_argument("query")
    p_search.add_argument("-k", "--top-k", type=int, default=5)
    p_search.add_argument("--doc", default=None, help="특정 문서 ID 로 제한")
    p_search.add_argument("--section", default=None, choices=["본문", "부칙", "전문"])
    p_search.add_argument("--lexical-only", action="store_true", help="임베딩 없이 BM25 만 사용")
    p_search.add_argument("--full", action="store_true", help="청크 전문 출력")
    p_search.add_argument(
        "--format", default=None, choices=list(FORMATS), help="검색 결과를 LLM 에 붙일 형태로 출력"
    )
    _add_common(p_search)

    p_ask = sub.add_parser("ask", help="검색 결과를 근거로 Claude 가 답변한다")
    p_ask.add_argument("query")
    p_ask.add_argument("-k", "--top-k", type=int, default=5)
    p_ask.add_argument("--doc", default=None)
    _add_common(p_ask)

    p_export = sub.add_parser(
        "export",
        help="청크를 LLM 컨텍스트에 붙일 형태로 내보낸다 (XML/Markdown/텍스트/JSONL)",
    )
    p_export.add_argument("pdf", nargs="?", default=None, help="약관 PDF. 생략하면 인덱스에서 가져온다")
    p_export.add_argument("--format", default="xml", choices=list(FORMATS))
    p_export.add_argument("--out", default=None, help="저장 경로 (생략 시 표준출력)")
    p_export.add_argument("--query", default=None, help="관련 조항만 검색해서 내보낸다 (인덱스 필요)")
    p_export.add_argument("-k", "--top-k", type=int, default=8, help="--query 와 함께 쓸 조항 수")
    p_export.add_argument("--article", nargs="+", default=None, help='조 번호로 선택 (예: --article 12 12-2)')
    p_export.add_argument("--chapter", type=int, default=None, help="장 번호로 선택")
    p_export.add_argument("--section", default=None, choices=["본문", "부칙", "전문"])
    p_export.add_argument("--max-tokens", type=int, default=None, help="이 토큰 수에 맞춰 여러 개로 나눈다")
    p_export.add_argument("--no-instructions", action="store_true", help="상단 지시문 없이 원문만")
    p_export.add_argument("--exact-tokens", action="store_true", help="Claude API 로 토큰 수를 실측한다")
    _add_common(p_export)

    p_info = sub.add_parser("info", help="인덱스 상태를 본다")
    _add_common(p_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    store_path = getattr(args, "store", None) or settings.store_path

    try:
        if args.command == "chunk":
            return _cmd_chunk(args, settings)
        if args.command == "ingest":
            return _cmd_ingest(args, settings, store_path)
        if args.command == "search":
            return _cmd_search(args, settings, store_path)
        if args.command == "ask":
            return _cmd_ask(args, settings, store_path)
        if args.command == "export":
            return _cmd_export(args, settings, store_path)
        if args.command == "info":
            return _cmd_info(store_path)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_chunk(args, settings: Settings) -> int:
    config = settings.chunk
    if args.max_chars:
        config.max_chars = args.max_chars
    chunks = chunk_pdf(args.pdf, config)
    lengths = [c.char_len for c in chunks]
    print(f"청크 {len(chunks)}개 · 평균 {sum(lengths)/len(lengths):.0f}자 · 최대 {max(lengths)}자")

    if args.preview:
        for chunk in chunks:
            print(BAR)
            print(f"[{chunk.order}] {chunk.citation}  ({chunk.char_len}자)")
            print(chunk.text)
    else:
        for chunk in chunks:
            print(f"[{chunk.order:>4}] {chunk.char_len:>5}자  {chunk.citation}")

    if args.out:
        path = export_chunks(chunks, args.out)
        print(f"\n저장: {path}")
    return 0


def _cmd_ingest(args, settings: Settings, store_path: str) -> int:
    _, reports = ingest(args.inputs, settings=settings, store_path=store_path, progress=print)
    print(BAR)
    for report in reports:
        print(report)
    return 0


def _cmd_search(args, settings: Settings, store_path: str) -> int:
    store = VectorStore.load(store_path)
    hits = run_search(
        args.query,
        store=store,
        settings=settings,
        top_k=args.top_k,
        doc_id=args.doc,
        section=args.section,
        lexical_only=args.lexical_only,
    )
    if not hits:
        print("검색 결과가 없습니다.")
        return 0
    if args.format:
        print(render([hit.chunk for hit in hits], fmt=args.format))
        return 0
    for hit in hits:
        print(BAR)
        print(f"#{hit.rank}  {hit.chunk.citation}")
        print(f"     점수 {hit.score:.4f} (vector {hit.vector_score:.3f} / bm25 {hit.lexical_score:.2f})")
        body = hit.chunk.text if args.full else _shorten(hit.chunk.text, 240)
        print(_indent(body))
    return 0


def _cmd_ask(args, settings: Settings, store_path: str) -> int:
    store = VectorStore.load(store_path)
    hits = run_search(args.query, store=store, settings=settings, top_k=args.top_k, doc_id=args.doc)
    result = generate_answer(args.query, hits, settings=settings)
    print(result.text)
    if result.hits:
        print(f"\n{BAR}\n근거")
        for line in result.sources():
            print(f"  {line}")
    return 1 if result.refused else 0


def _cmd_export(args, settings: Settings, store_path: str) -> int:
    chunks = _export_source(args, settings, store_path)
    chunks = filter_chunks(chunks, articles=args.article, chapter=args.chapter, section=args.section)
    if not chunks:
        raise ValueError("내보낼 조항이 없습니다. 필터 조건을 확인하세요.")

    options = {"instructions": not args.no_instructions}
    batches = (
        split_by_tokens(chunks, max_tokens=args.max_tokens, fmt=args.format, **options)
        if args.max_tokens
        else [list(chunks)]
    )

    outputs = [render(batch, fmt=args.format, **options) for batch in batches]
    _report_export(outputs, batches, args, settings)

    if not args.out:
        for i, text in enumerate(outputs):
            if len(outputs) > 1:
                print(f"\n===== {i + 1}/{len(outputs)} =====", file=sys.stderr)
            print(text)
        return 0

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(outputs):
        path = target if len(outputs) == 1 else target.with_suffix(f".{i + 1}{target.suffix}")
        path.write_text(text, encoding="utf-8")
        print(f"저장: {path}", file=sys.stderr)
    return 0


def _export_source(args, settings: Settings, store_path: str):
    """PDF 에서 바로 뽑을지, 인덱스에서 가져올지 결정한다."""
    if args.pdf and args.query:
        raise ValueError("--query 는 인덱스에서 검색합니다. PDF 경로와 함께 쓸 수 없습니다.")
    if args.pdf:
        return chunk_pdf(args.pdf, settings.chunk)

    store = VectorStore.load(store_path)
    if not len(store):
        raise ValueError(
            f"{store_path} 가 비어 있습니다. PDF 경로를 직접 주거나 먼저 `ingest` 를 실행하세요."
        )
    if args.query:
        hits = run_search(args.query, store=store, settings=settings, top_k=args.top_k)
        return [hit.chunk for hit in hits]
    return store.chunks


def _report_export(outputs, batches, args, settings: Settings) -> None:
    """붙여넣기용 본문은 표준출력, 통계는 표준에러로 보낸다(파이프 오염 방지)."""
    total_chars = sum(len(text) for text in outputs)
    counter = (
        (lambda text: count_tokens(text, model=settings.answer_model, api_key=settings.anthropic_api_key))
        if args.exact_tokens
        else estimate_tokens
    )
    counts = [counter(text) for text in outputs]
    total = sum(c.tokens for c in counts)
    how = "실측" if counts and counts[0].exact else "추정"

    print(
        f"조항 {sum(len(b) for b in batches)}개 · {total_chars:,}자 · 약 {total:,} 토큰({how})"
        + (f" · {len(outputs)}개로 분할" if len(outputs) > 1 else ""),
        file=sys.stderr,
    )


def _cmd_info(store_path: str) -> int:
    store = VectorStore.load(store_path)
    path = Path(store_path)
    if not len(store):
        print(f"{path}: 비어 있습니다. `python -m terms_rag ingest` 를 먼저 실행하세요.")
        return 0
    manifest = store.manifest
    print(f"인덱스     : {path}")
    print(f"임베딩     : {manifest.get('provider')}/{manifest.get('model')} (dim={manifest.get('dim')})")
    print(f"청크 수    : {len(store)}")
    print(f"갱신 시각  : {manifest.get('updated_at')}")
    print("문서")
    for doc in store.documents():
        print(f"  - {doc['title']}  [{doc['doc_id']}]  청크 {doc['chunks']}개  ({doc['source']})")
    return 0


def _shorten(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + " …"


def _indent(text: str, prefix: str = "     ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
