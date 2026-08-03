"""보험 제도 뉴스 파이프라인 CLI.

    python -m src.cli collect     1단계 · 기사 수집 + 자동 1차 분류
    python -m src.cli review      2단계 · 담당자 확인 웹 UI 실행
    python -m src.cli export      3단계 · 승인 기사 → 마크다운
    python -m src.cli stats       현재 큐 상태
    python -m src.cli seed        샘플 데이터 적재 (네트워크 없이 시연)
    python -m src.cli doctor      소스 URL 유효성 점검
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .classifier import Classifier, DEFAULT_FILTER_CONFIG
from .collect import DEFAULT_SOURCE_CONFIG, collect, load_source_config
from .export_md import DEFAULT_OUTPUT, export
from .models import Article, STATUS_LABELS
from .store import DEFAULT_DB, ArticleStore


def _bar(count: int, total: int, width: int = 24) -> str:
    filled = 0 if total == 0 else round(width * count / total)
    return "█" * filled + "·" * (width - filled)


def cmd_collect(args) -> int:
    config = load_source_config(args.sources)
    classifier = Classifier.from_file(args.filters)
    store = ArticleStore(args.db)

    print("1단계 · 기사 수집")
    before = len(store)
    result = collect(
        store, classifier, config, only_source=args.source, fetch_body=not args.no_body
    )
    print(
        f"\n  신규 {result.new} · 갱신 {result.updated} · 유지 {result.skipped} · 제외 {result.dropped}"
    )
    print(f"  저장소: {before} → {len(store)}건")
    if result.errors:
        print("\n  수집 실패한 소스:")
        for err in result.errors:
            print(f"    - {err}")
    print(f"\n  다음: python -m src.cli review   ({store.counts().get('pending', 0)}건 검수 대기)")
    return 0


def cmd_review(args) -> int:
    from .review_app import create_app

    store = ArticleStore(args.db)
    pending = store.counts().get("pending", 0)
    print("2단계 · 담당자 확인")
    print(f"  검수 대기 {pending}건 · 전체 {len(store)}건")
    print(f"  → http://{args.host}:{args.port}\n")
    app = create_app(args.db, args.output)
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
    return 0


def cmd_export(args) -> int:
    store = ArticleStore(args.db)
    approved = store.counts().get("approved", 0)
    print("3단계 · 마크다운 변환")
    if approved == 0:
        print("  승인된 기사가 없습니다. 검수(python -m src.cli review)를 먼저 진행하세요.")
        return 1
    export(store, args.output, clean=not args.keep_stale)
    return 0


def cmd_stats(args) -> int:
    store = ArticleStore(args.db)
    counts = store.counts()
    total = len(store)
    print(f"저장소: {args.db} · 총 {total}건\n")
    for status, label in STATUS_LABELS.items():
        n = counts.get(status, 0)
        print(f"  {label:<16} {n:>4}건  {_bar(n, total)}")

    by_source: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for a in store.all():
        by_source[a.source] = by_source.get(a.source, 0) + 1
        if a.status == "approved":
            by_category[a.category] = by_category.get(a.category, 0) + 1

    if by_source:
        print("\n매체별")
        for name, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<22} {n:>4}건")
    if by_category:
        print("\n승인 기사 분류별")
        for name, n in sorted(by_category.items(), key=lambda kv: -kv[1]):
            print(f"  {name:<22} {n:>4}건")
    return 0


def cmd_seed(args) -> int:
    """네트워크 없이 파이프라인을 시연하기 위한 샘플 적재."""
    path = Path(args.file)
    if not path.exists():
        print(f"샘플 파일이 없습니다: {path}")
        return 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    classifier = Classifier.from_file(args.filters)
    store = ArticleStore(args.db)

    added = 0
    for item in payload.get("articles", []):
        article = Article.from_dict(item)
        if not article.id:
            from .models import make_id

            article.id = make_id(article.url)
        if not article.summary:
            from .collect import summarize

            article.summary = summarize(article.content)
        classifier.apply(article, source_weight=float(item.get("source_weight", 1.0)))
        if store.upsert(article) == "new":
            added += 1
    store.save()
    counts = store.counts()
    print(f"샘플 {added}건 적재 완료 (총 {len(store)}건)")
    for status, label in STATUS_LABELS.items():
        if counts.get(status):
            print(f"  {label}: {counts[status]}건")
    print("\n  다음: python -m src.cli review")
    return 0


def cmd_doctor(args) -> int:
    """소스 URL 이 살아 있는지, 파싱이 되는지 점검한다."""
    import requests
    import feedparser

    config = load_source_config(args.sources)
    defaults = config.get("defaults", {}) or {}
    headers = {"User-Agent": defaults.get("user_agent", "insurance-news-pipeline/1.0")}
    timeout = int(defaults.get("timeout", 15))

    print("소스 점검\n")
    problems = 0
    for source in config.get("sources", []) or []:
        name = source["name"]
        if not source.get("enabled", True):
            print(f"  ○ {name:<22} 비활성")
            continue
        try:
            resp = requests.get(source["url"], headers=headers, timeout=timeout)
            resp.raise_for_status()
            if source.get("type") == "html":
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(resp.text, "html.parser")
                found = sum(
                    len(soup.select(s.strip())) for s in source.get("list_selector", "a").split(",")
                )
                status = f"링크 {found}개" if found else "선택자 불일치 — list_selector 확인 필요"
                if not found:
                    problems += 1
                print(f"  {'✓' if found else '✗'} {name:<22} {status}")
            else:
                feed = feedparser.parse(resp.content)
                n = len(feed.entries)
                if not n:
                    problems += 1
                print(f"  {'✓' if n else '✗'} {name:<22} 기사 {n}건")
        except Exception as exc:
            problems += 1
            print(f"  ✗ {name:<22} {type(exc).__name__}: {exc}")

    print(f"\n문제 있는 소스: {problems}개")
    return 0 if problems == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="보험 제도 변경 뉴스 수집 → 담당자 확인 → 마크다운 변환 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="기사 저장소 경로")
    parser.add_argument("--filters", default=str(DEFAULT_FILTER_CONFIG), help="분류 규칙 파일")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("collect", help="1단계 · 기사 수집")
    p.add_argument("--sources", default=str(DEFAULT_SOURCE_CONFIG))
    p.add_argument("--source", help="특정 소스만 수집")
    p.add_argument("--no-body", action="store_true", help="본문 원문을 받지 않고 요약만 사용")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("review", help="2단계 · 담당자 확인 웹 UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--debug", action="store_true")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("export", help="3단계 · 승인 기사 마크다운 변환")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--keep-stale", action="store_true", help="기존 MD 를 지우지 않음")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("stats", help="큐 현황")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("seed", help="샘플 데이터 적재")
    p.add_argument("--file", default="data/seed_articles.json")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("doctor", help="소스 URL 점검")
    p.add_argument("--sources", default=str(DEFAULT_SOURCE_CONFIG))
    p.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
