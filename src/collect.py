"""1단계 — 기사 수집.

RSS 피드와 규제기관 목록 페이지를 훑어 기사를 모으고,
자동 분류기를 태워 검수 큐(data/articles.json)에 넣는다.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from .classifier import Classifier
from .models import Article, make_id, normalize_url
from .store import ArticleStore

DEFAULT_SOURCE_CONFIG = Path("config/sources.yaml")

# 기사 본문이 들어 있을 만한 컨테이너 (한국 언론사 CMS 공통 패턴)
_BODY_SELECTORS = (
    "#article-view-content-div",
    "#articleBody",
    "#news_body_area",
    "div.article-body",
    "div.article_body",
    "div.news-article-body",
    "div.view-con",
    "div.cont_view",
    "article",
)

_STRIP_TAGS = ("script", "style", "figure", "figcaption", "iframe", "table", "aside", "nav")

# 본문 끝에 붙는 기자 서명·저작권 문구
_TAIL_PATTERNS = (
    re.compile(r"저작권자.*무단.*금지.*$", re.S),
    re.compile(r"[가-힣]{2,4}\s*기자\s*[\w.\-]+@[\w.\-]+.*$", re.S),
    re.compile(r"Copyright.*$", re.S | re.I),
)


@dataclass
class CollectResult:
    new: int = 0
    updated: int = 0
    skipped: int = 0
    dropped: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total_seen(self) -> int:
        return self.new + self.updated + self.skipped + self.dropped


def load_source_config(path: str | Path = DEFAULT_SOURCE_CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def _parse_date(value) -> str:
    """feedparser 의 struct_time 또는 문자열을 ISO8601 로."""
    if not value:
        return ""
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc).astimezone().isoformat(timespec="seconds")
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).astimezone().isoformat(timespec="seconds")
        except ValueError:
            continue
    return ""


def _too_old(published_at: str, max_age_days: int) -> bool:
    if not published_at or max_age_days <= 0:
        return False
    try:
        dt = datetime.fromisoformat(published_at)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt < datetime.now(dt.tzinfo) - timedelta(days=max_age_days)


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_body(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    node = None
    for selector in _BODY_SELECTORS:
        node = soup.select_one(selector)
        if node and len(node.get_text(strip=True)) > 200:
            break
        node = None
    text = clean_text(str(node) if node else str(soup.body or soup))
    for pattern in _TAIL_PATTERNS:
        text = pattern.sub("", text).strip()
    return text


def summarize(text: str, max_chars: int = 260) -> str:
    """앞부분 문장을 잘라 초벌 요약을 만든다. 담당자가 검수 화면에서 고칠 수 있다."""
    body = re.sub(r"\s+", " ", (text or "").strip())
    if not body:
        return ""
    if len(body) <= max_chars:
        return body
    cut = body[:max_chars]
    for mark in (". ", "다. ", "다.", "? ", "! "):
        idx = cut.rfind(mark)
        if idx > max_chars * 0.5:
            return cut[: idx + len(mark)].strip()
    return cut.rstrip() + "…"


def fetch_article_body(session: requests.Session, url: str, timeout: int) -> str:
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        if resp.encoding in (None, "ISO-8859-1"):
            resp.encoding = resp.apparent_encoding or "utf-8"
        return extract_body(resp.text)
    except requests.RequestException:
        return ""


# ── 소스별 수집 ───────────────────────────────────────────────────
def collect_rss(source: dict, defaults: dict, session: requests.Session) -> list[Article]:
    limit = int(source.get("max_items") or defaults.get("max_items_per_source", 40))
    timeout = int(defaults.get("timeout", 15))
    resp = session.get(source["url"], timeout=timeout)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)

    out: list[Article] = []
    for entry in feed.entries[:limit]:
        link = (entry.get("link") or "").strip()
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        published = _parse_date(entry.get("published_parsed") or entry.get("updated_parsed"))
        if not published:
            published = _parse_date(entry.get("published") or entry.get("updated"))
        raw_summary = entry.get("summary") or entry.get("description") or ""
        out.append(
            Article(
                id=make_id(link),
                url=normalize_url(link),
                title=title,
                source=source["name"],
                published_at=published,
                summary=summarize(clean_text(raw_summary)),
                content=clean_text(raw_summary),
            )
        )
    return out


def collect_html(source: dict, defaults: dict, session: requests.Session) -> list[Article]:
    limit = int(source.get("max_items") or defaults.get("max_items_per_source", 40))
    timeout = int(defaults.get("timeout", 15))
    resp = session.get(source["url"], timeout=timeout)
    resp.raise_for_status()
    if resp.encoding in (None, "ISO-8859-1"):
        resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    base = source.get("base_url") or source["url"]
    seen: set[str] = set()
    out: list[Article] = []

    for selector in [s.strip() for s in source.get("list_selector", "a").split(",")]:
        for anchor in soup.select(selector):
            href = (anchor.get("href") or "").strip()
            title = anchor.get_text(strip=True)
            if not href or href.startswith(("#", "javascript:")) or len(title) < 8:
                continue
            link = normalize_url(urljoin(base, href))
            if link in seen:
                continue
            seen.add(link)
            out.append(
                Article(
                    id=make_id(link),
                    url=link,
                    title=title,
                    source=source["name"],
                )
            )
            if len(out) >= limit:
                return out
    return out


def collect(
    store: ArticleStore,
    classifier: Classifier,
    config: dict,
    *,
    only_source: str | None = None,
    fetch_body: bool = True,
    verbose: bool = True,
) -> CollectResult:
    defaults = config.get("defaults", {}) or {}
    session = _session(defaults.get("user_agent", "insurance-news-pipeline/1.0"))
    timeout = int(defaults.get("timeout", 15))
    max_age = int(defaults.get("max_age_days", 30))
    result = CollectResult()

    for source in config.get("sources", []) or []:
        if not source.get("enabled", True):
            continue
        if only_source and source["name"] != only_source:
            continue

        try:
            if source.get("type") == "html":
                articles = collect_html(source, defaults, session)
            else:
                articles = collect_rss(source, defaults, session)
        except Exception as exc:  # 한 소스가 죽어도 나머지는 계속
            msg = f"[{source['name']}] 수집 실패: {exc}"
            result.errors.append(msg)
            if verbose:
                print("  !", msg)
            continue

        kept = 0
        for article in articles:
            if _too_old(article.published_at, max_age):
                result.dropped += 1
                continue
            # 이미 검수가 끝난 기사는 본문을 다시 받지 않는다.
            existing = store.get(article.id)
            if fetch_body and not (existing and existing.is_decided):
                if len(article.content) < 400:
                    body = fetch_article_body(session, article.url, timeout)
                    if body:
                        article.content = body
                        article.summary = summarize(body)

            verdict = classifier.apply(
                article,
                source_weight=float(source.get("weight", 1.0)),
                always_review=bool(source.get("always_review", False)),
            )
            if verdict.dropped:
                result.dropped += 1
                continue

            action = store.upsert(article)
            setattr(result, action, getattr(result, action) + 1)
            kept += 1

        if verbose:
            print(f"  · {source['name']}: {len(articles)}건 조회 → {kept}건 반영")

    store.save()
    return result
