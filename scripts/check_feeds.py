#!/usr/bin/env python3
"""feeds.json 의 RSS 주소를 점검하고, 틀렸으면 홈페이지에서 찾아준다.

  python3 scripts/check_feeds.py          # 점검만
  python3 scripts/check_feeds.py --fix    # 찾은 주소를 feeds.json 에 써넣는다

각 매체마다 이렇게 확인한다.
  1. url 이 있으면 실제로 받아서 기사가 몇 건 나오는지 본다
  2. 실패하면 homepage 의 <link rel=alternate type=...rss+xml> 을 뒤진다
  3. 그래도 없으면 흔히 쓰는 주소 몇 개를 직접 찔러본다
"""
import json
import re
import socket
import sys
import urllib.error
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collector import FEEDS_PATH, fetch, parse_feed  # noqa: E402

# 국내 언론사 CMS 가 흔히 쓰는 경로들
COMMON_PATHS = [
    "/rss/allArticle.xml",
    "/rss/S1N1.xml",
    "/rss/clickTop.xml",
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed/",
    "/index.rss",
    "/board/rss",
]

LINK_RE = re.compile(
    r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', re.I)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
ANCHOR_RE = re.compile(r'href=["\']([^"\']*(?:rss|feed)[^"\']*)["\']', re.I)


def try_feed(url: str) -> tuple[bool, str]:
    """주소 하나를 실제로 받아 기사가 나오는지 본다."""
    try:
        entries = parse_feed(fetch(url))
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        return False, f"접속 실패 ({exc})"
    except Exception as exc:  # XML 이 아니거나 깨진 경우
        return False, f"RSS 형식 아님 ({type(exc).__name__})"
    if not entries:
        return False, "기사 0건"
    return True, f"기사 {len(entries)}건 · 예: {entries[0]['title'][:34]}"


def discover(homepage: str) -> list[str]:
    """홈페이지 HTML 에서 RSS 주소 후보를 뽑는다."""
    if not homepage:
        return []
    try:
        html = fetch(homepage).decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, OSError):
        return []

    found: list[str] = []
    for tag in LINK_RE.findall(html):
        m = HREF_RE.search(tag)
        if m:
            found.append(urljoin(homepage, unescape(m.group(1))))
    for href in ANCHOR_RE.findall(html):
        url = urljoin(homepage, unescape(href))
        if url not in found:
            found.append(url)

    # 중복 제거 (순서 유지)
    return list(dict.fromkeys(found))[:12]


def check(feed: dict) -> tuple[str, str, str]:
    """(상태, 쓸 주소, 설명) 을 돌려준다."""
    name = feed.get("name", "?")
    url = feed.get("url", "")
    homepage = feed.get("homepage", "")

    if url:
        ok, detail = try_feed(url)
        if ok:
            return "OK", url, detail
        print(f"    적어둔 주소 실패: {detail}")

    print(f"    {homepage} 에서 RSS 주소를 찾는 중…")
    for candidate in discover(homepage):
        ok, detail = try_feed(candidate)
        if ok:
            return "FOUND", candidate, detail

    if homepage:
        print("    흔히 쓰는 주소를 찔러보는 중…")
        for path in COMMON_PATHS:
            candidate = urljoin(homepage, path)
            ok, detail = try_feed(candidate)
            if ok:
                return "FOUND", candidate, detail

    return "FAIL", url, "찾지 못했습니다"


def main() -> int:
    fix = "--fix" in sys.argv
    feeds = json.loads(FEEDS_PATH.read_text(encoding="utf-8"))

    changed = False
    bad: list[str] = []

    for feed in feeds:
        name = feed.get("name", "?")
        print(f"\n[{name}]")
        status, url, detail = check(feed)

        if status == "OK":
            print(f"  ✓ {detail}")
            feed["verified"] = True
        elif status == "FOUND":
            print(f"  ✓ 찾았습니다: {url}")
            print(f"    {detail}")
            feed["url"] = url
            feed["verified"] = True
            changed = True
        else:
            print("  ✗ RSS 주소를 찾지 못했습니다.")
            print(f"    {feed.get('homepage', '')} 에 직접 들어가 RSS 링크를 확인해 주세요.")
            feed["verified"] = False
            bad.append(name)

    if fix and changed:
        FEEDS_PATH.write_text(
            json.dumps(feeds, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nfeeds.json 을 갱신했습니다.")
    elif changed:
        print("\n찾은 주소를 저장하려면 --fix 를 붙여 다시 실행하세요.")

    total = len(feeds)
    print(f"\n{'─' * 46}")
    print(f"전체 {total}개 · 정상 {total - len(bad)}개 · 실패 {len(bad)}개")
    if bad:
        print(f"실패: {', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
