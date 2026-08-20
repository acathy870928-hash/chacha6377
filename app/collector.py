"""RSS/Atom 수집기.

외부 의존성 없이 stdlib(urllib + ElementTree)만 쓴다.
피드 목록은 feeds.json 에서 읽고, 수집한 기사는 store.upsert_article 로 들어간다.
source_id(=원문 URL)로 중복을 막기 때문에 몇 번을 돌려도 안전하다.
"""
import gzip
import json
import re
import socket
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .config import BASE_DIR
from .db import session
from .store import upsert_article

FEEDS_PATH = BASE_DIR / "feeds.json"
USER_AGENT = "Mozilla/5.0 (compatible; SaeopdanNewsBot/1.0)"
TIMEOUT = 15

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


def load_feeds() -> list[dict[str, str]]:
    if not FEEDS_PATH.exists():
        return []
    return json.loads(FEEDS_PATH.read_text(encoding="utf-8"))


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw


_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def strip_html(html: str) -> str:
    text = _SCRIPT_RE.sub(" ", html or "")
    text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.I)
    text = _TAG_RE.sub(" ", text)
    text = unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None and el.text else ""


def parse_feed(raw: bytes) -> list[dict[str, str]]:
    """RSS 2.0 / Atom 둘 다 처리."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        # 앞뒤에 붙은 쓰레기 문자 때문에 실패하는 피드가 있다
        start = raw.find(b"<?xml")
        if start > 0:
            root = ET.fromstring(raw[start:])
        else:
            raise

    entries: list[dict[str, str]] = []

    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue

        title = _text(item.find("title")) or _text(item.find("atom:title", NS))

        link = _text(item.find("link"))
        if not link:
            link_el = item.find("atom:link", NS) or item.find("link")
            if link_el is not None:
                link = link_el.get("href", "").strip()

        body_html = (
            _text(item.find("content:encoded", NS))
            or _text(item.find("description"))
            or _text(item.find("atom:content", NS))
            or _text(item.find("atom:summary", NS))
        )

        published = (
            _text(item.find("pubDate"))
            or _text(item.find("dc:date", NS))
            or _text(item.find("atom:published", NS))
            or _text(item.find("atom:updated", NS))
        )

        if not title or not link:
            continue

        entries.append({
            "title": strip_html(title),
            "origin_url": link,
            "body": strip_html(body_html),
            "published_at": normalize_date(published),
        })

    return entries


_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def normalize_date(value: str) -> str:
    """RFC822(pubDate) / ISO8601 을 'YYYY-MM-DD HH:MM:SS' 로 통일."""
    value = (value or "").strip()
    if not value:
        return ""
    # RFC822: Wed, 20 Aug 2026 09:30:00 +0900
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})[\s,]+(\d{2}):(\d{2})(?::(\d{2}))?", value)
    if m:
        day, mon, year, hh, mm, ss = m.groups()
        month = _MONTHS.get(mon, 1)
        return f"{year}-{month:02d}-{int(day):02d} {hh}:{mm}:{ss or '00'}"
    # ISO8601
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[T ]?(\d{2})?:?(\d{2})?:?(\d{2})?", value)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        return f"{y}-{mo}-{d} {hh or '00'}:{mm or '00'}:{ss or '00'}"
    return ""


_ARTICLE_HINTS = [
    r'<div[^>]+id="article[^"]*"[^>]*>(.*?)</div>',
    r'<div[^>]+class="[^"]*article[^"]*"[^>]*>(.*?)</div>',
    r'<article[^>]*>(.*?)</article>',
]


def extract_body(html: str) -> str:
    """본문 영역을 대충 집어낸다.

    RSS description 이 요약 몇 줄만 주는 매체가 많아서, 원문에서 본문을 다시 뽑는다.
    매체별 정확한 셀렉터가 필요하면 feeds.json 의 body_selector 로 지정할 수 있다.
    """
    cleaned = _SCRIPT_RE.sub(" ", html or "")
    best = ""
    for pattern in _ARTICLE_HINTS:
        for m in re.finditer(pattern, cleaned, re.S | re.I):
            text = strip_html(m.group(1))
            if len(text) > len(best):
                best = text
    if len(best) >= 200:
        return best

    # 마지막 수단: <p> 태그를 모아 붙인다
    paragraphs = [strip_html(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", cleaned, re.S | re.I)]
    joined = "\n\n".join(p for p in paragraphs if len(p) > 40)
    return joined if len(joined) > len(best) else best


def collect_feed(feed: dict[str, str], fetch_body: bool = True, limit: int = 30) -> dict[str, Any]:
    """피드 하나를 수집. 결과 통계를 반환한다."""
    name = feed.get("name", "")
    url = feed.get("url", "")
    result = {"publisher": name, "url": url, "created": 0, "updated": 0, "failed": 0, "error": ""}

    try:
        entries = parse_feed(fetch(url))[:limit]
    except (urllib.error.URLError, socket.timeout, ET.ParseError, OSError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    with session() as conn:
        for entry in entries:
            body = entry["body"]
            if fetch_body and len(re.sub(r"\s", "", body)) < 300:
                try:
                    body = extract_body(fetch(entry["origin_url"]).decode("utf-8", "replace")) or body
                except (urllib.error.URLError, socket.timeout, OSError):
                    pass  # 본문 재수집 실패는 치명적이지 않다 — 요약만으로 저장

            try:
                _, action = upsert_article(conn, {
                    "source_id": entry["origin_url"],
                    "title": entry["title"],
                    "body": body,
                    "publisher": name,
                    "origin_url": entry["origin_url"],
                    "published_at": entry["published_at"],
                })
                result[action] += 1
            except (ValueError, Exception):
                result["failed"] += 1

    return result


def collect_all(fetch_body: bool = True, limit: int = 30) -> list[dict[str, Any]]:
    return [collect_feed(f, fetch_body, limit) for f in load_feeds() if f.get("url")]


PUBLISHER_BY_HOST = {
    "insnews.co.kr": "한국보험신문",
    "insjournal.co.kr": "보험저널",
    "fntimes.com": "보험매일",
    "insunet.co.kr": "인슈넷",
    "fins.co.kr": "한국금융신문",
    "yna.co.kr": "연합뉴스",
}


def guess_publisher(url: str, html: str = "") -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for domain, name in PUBLISHER_BY_HOST.items():
        if host.endswith(domain):
            return name
    m = re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return strip_html(m.group(1))
    return host


def extract_title(html: str) -> str:
    for pattern in (
        r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="title"[^>]+content="([^"]+)"',
        r"<h1[^>]*>(.*?)</h1>",
        r"<title[^>]*>(.*?)</title>",
    ):
        m = re.search(pattern, html, re.S | re.I)
        if m:
            title = strip_html(m.group(1))
            # "제목 - 한국보험신문" 같은 매체명 꼬리표를 떼어낸다
            title = re.split(r"\s+[-|·]\s+", title)[0].strip()
            if title:
                return title
    return ""


def extract_published(html: str) -> str:
    for pattern in (
        r'<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="date"[^>]+content="([^"]+)"',
        r"(\d{4}[-.]\d{2}[-.]\d{2}[ T]\d{2}:\d{2})",
    ):
        m = re.search(pattern, html, re.I)
        if m:
            normalized = normalize_date(m.group(1).replace(".", "-"))
            if normalized:
                return normalized
    return ""


def collect_url(url: str, audience: str = "both", publisher: str = "") -> dict[str, Any]:
    """기사 URL 하나를 받아 후보로 등록한다.

    대표가 카톡/메신저로 받은 링크를 어드민에 그대로 붙여넣는 흐름을 위한 것.
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "http(s) 로 시작하는 주소가 아닙니다", "url": url}

    try:
        html = fetch(url).decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return {"ok": False, "error": f"불러오기 실패: {exc}", "url": url}

    title = extract_title(html)
    if not title:
        return {"ok": False, "error": "제목을 찾지 못했습니다", "url": url}

    with session() as conn:
        article_id, action = upsert_article(conn, {
            "source_id": url,
            "title": title,
            "body": extract_body(html),
            "publisher": publisher or guess_publisher(url, html),
            "origin_url": url,
            "published_at": extract_published(html),
            "audience": audience,
        })

    return {"ok": True, "id": article_id, "action": action, "title": title, "url": url}
