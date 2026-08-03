"""3단계 — 승인된 기사를 마크다운으로 변환.

챗봇 인덱싱을 염두에 두고 세 가지를 만든다.
  output/articles/<날짜>-<제목>.md  기사 1건 = 파일 1개 (RAG 청크 단위)
  output/index.md                   전체 목록 (사람이 훑어보는 용도)
  output/bundle/insurance-policy-news.md  단일 파일 통합본 (통째로 넣을 때)
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .models import Article, STATUS_APPROVED, slugify
from .store import ArticleStore

DEFAULT_OUTPUT = Path("output")


def _yaml_escape(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _date_only(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except ValueError:
        return value[:10]


def _clean_body(text: str) -> str:
    """본문을 문단 단위로 정리한다."""
    text = re.sub(r"\r\n?", "\n", text or "")
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n")]
    return "\n\n".join(p for p in paragraphs if p)


def article_filename(article: Article) -> str:
    date = _date_only(article.published_at or article.collected_at) or "undated"
    return f"{date}-{slugify(article.display_title)}-{article.id[:6]}.md"


def render_article(article: Article) -> str:
    """front matter + 본문. 챗봇이 메타데이터로 필터링할 수 있게 구조화한다."""
    tags = list(article.tags)
    if article.category and article.category not in tags:
        tags.insert(0, article.category)

    lines = ["---"]
    lines.append(f"title: {_yaml_escape(article.display_title)}")
    lines.append(f"doc_id: {article.id}")
    lines.append(f"source: {_yaml_escape(article.source)}")
    lines.append(f"url: {_yaml_escape(article.url)}")
    lines.append(f"published_at: {_yaml_escape(_date_only(article.published_at))}")
    if article.effective_date:
        lines.append(f"effective_date: {_yaml_escape(article.effective_date)}")
    lines.append(f"category: {_yaml_escape(article.category)}")
    lines.append("tags: [" + ", ".join(_yaml_escape(t) for t in tags) + "]")
    lines.append("doc_type: 보험제도변경뉴스")
    lines.append(f"reviewed_by: {_yaml_escape(article.reviewer)}")
    lines.append(f"reviewed_at: {_yaml_escape(_date_only(article.reviewed_at))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {article.display_title}")
    lines.append("")

    meta_row = [f"**출처** {article.source}"]
    if article.published_at:
        meta_row.append(f"**보도일** {_date_only(article.published_at)}")
    if article.effective_date:
        meta_row.append(f"**시행일** {article.effective_date}")
    meta_row.append(f"**분류** {article.category}")
    lines.append(" · ".join(meta_row))
    lines.append("")

    if article.display_summary:
        lines.append("## 요약")
        lines.append("")
        lines.append(article.display_summary)
        lines.append("")

    if article.reviewer_note:
        lines.append("## 담당자 메모")
        lines.append("")
        lines.append(article.reviewer_note)
        lines.append("")

    body = _clean_body(article.content)
    if body:
        lines.append("## 본문")
        lines.append("")
        lines.append(body)
        lines.append("")

    lines.append("## 원문")
    lines.append("")
    lines.append(f"<{article.url}>")
    lines.append("")
    return "\n".join(lines)


def render_index(articles: list[Article]) -> str:
    grouped: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        grouped[a.category or "미분류"].append(a)

    lines = [
        "# 보험 제도 변경 뉴스 아카이브",
        "",
        f"- 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 승인 기사: {len(articles)}건",
        f"- 분류: {len(grouped)}개",
        "",
        "> 담당자 검수를 통과한 제도 변경 기사만 담겨 있습니다. "
        "상품 홍보·기업 소식 기사는 제외됩니다.",
        "",
    ]
    for category in sorted(grouped):
        items = sorted(
            grouped[category],
            key=lambda a: a.published_at or a.collected_at,
            reverse=True,
        )
        lines.append(f"## {category} ({len(items)}건)")
        lines.append("")
        for a in items:
            date = _date_only(a.published_at) or "-"
            eff = f" · 시행 {a.effective_date}" if a.effective_date else ""
            # 제목에 %, ( 등이 섞이면 마크다운 링크가 깨지므로 경로를 인코딩한다.
            href = quote(f"articles/{article_filename(a)}")
            label = a.display_title.replace("[", "〔").replace("]", "〕")
            lines.append(f"- `{date}` [{label}]({href}) — {a.source}{eff}")
        lines.append("")
    return "\n".join(lines)


def render_bundle(articles: list[Article]) -> str:
    lines = [
        "# 보험 제도 변경 뉴스 통합본",
        "",
        f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 총 {len(articles)}건",
        "",
        "이 문서는 담당자 검수를 통과한 보험 제도·정책 변경 기사만 모은 것입니다.",
        "",
        "---",
        "",
    ]
    for a in articles:
        lines.append(f"## {a.display_title}")
        lines.append("")
        meta = [f"출처: {a.source}"]
        if a.published_at:
            meta.append(f"보도일: {_date_only(a.published_at)}")
        if a.effective_date:
            meta.append(f"시행일: {a.effective_date}")
        meta.append(f"분류: {a.category}")
        lines.append(" | ".join(meta))
        lines.append("")
        if a.display_summary:
            lines.append(f"**요약** {a.display_summary}")
            lines.append("")
        body = _clean_body(a.content)
        if body:
            lines.append(body)
            lines.append("")
        lines.append(f"원문: <{a.url}>")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def export(
    store: ArticleStore,
    output_dir: str | Path = DEFAULT_OUTPUT,
    *,
    clean: bool = True,
    verbose: bool = True,
) -> dict:
    out = Path(output_dir)
    articles_dir = out / "articles"
    bundle_dir = out / "bundle"
    articles_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    approved = [a for a in store.all() if a.status == STATUS_APPROVED]

    if clean:
        # 승인이 취소된 기사의 MD 가 남지 않도록 기존 산출물을 비운다.
        for stale in articles_dir.glob("*.md"):
            stale.unlink()

    written: list[str] = []
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    for article in approved:
        path = articles_dir / article_filename(article)
        path.write_text(render_article(article), encoding="utf-8")
        article.exported_at = stamp
        article.exported_path = str(path)
        written.append(str(path))

    (out / "index.md").write_text(render_index(approved), encoding="utf-8")
    bundle_path = bundle_dir / "insurance-policy-news.md"
    bundle_path.write_text(render_bundle(approved), encoding="utf-8")
    store.save()

    if verbose:
        print(f"  · 기사 MD {len(written)}건 → {articles_dir}")
        print(f"  · 목차       → {out / 'index.md'}")
        print(f"  · 통합본     → {bundle_path}")

    return {
        "count": len(written),
        "articles_dir": str(articles_dir),
        "index": str(out / "index.md"),
        "bundle": str(bundle_path),
        "files": written,
    }
