#!/usr/bin/env python3
"""기사 URL을 받아 본문을 긁어 후보로 등록한다.

  python3 scripts/add_urls.py                        # seed/pinned_urls.json 전체
  python3 scripts/add_urls.py --only fa              # 그중 FA용만
  python3 scripts/add_urls.py --audience fa <url>... # 인자로 직접 지정
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collector import collect_url  # noqa: E402
from app.db import init_db  # noqa: E402

PINNED = Path(__file__).resolve().parent.parent / "seed" / "pinned_urls.json"
AUDIENCES = ("rep", "fa", "both")


def _take_option(args: list[str], name: str) -> str:
    if name not in args:
        return ""
    i = args.index(name)
    value = args[i + 1] if i + 1 < len(args) else ""
    del args[i:i + 2]
    return value


def load_pinned(only: str) -> list[tuple[str, str]]:
    if not PINNED.exists():
        print(f"{PINNED} 이 없습니다.", file=sys.stderr)
        return []
    data = json.loads(PINNED.read_text(encoding="utf-8"))
    items = [
        (a["url"], a.get("audience", "both"))
        for a in data.get("articles", [])
        if a.get("url")
    ]
    return [(u, aud) for u, aud in items if not only or aud == only]


def main() -> int:
    args = sys.argv[1:]
    audience = _take_option(args, "--audience") or "rep"
    only = _take_option(args, "--only")

    if only and only not in AUDIENCES:
        print(f"--only 는 {', '.join(AUDIENCES)} 중 하나여야 합니다.", file=sys.stderr)
        return 2
    if audience not in AUDIENCES:
        print(f"--audience 는 {', '.join(AUDIENCES)} 중 하나여야 합니다.", file=sys.stderr)
        return 2

    targets = [(u, audience) for u in args] if args else load_pinned(only)
    if not targets:
        print("등록할 URL이 없습니다.")
        return 0

    init_db()
    failures = 0
    for url, aud in targets:
        result = collect_url(url, audience=aud)
        if result.get("ok"):
            print(f"[{result['action']:7s}] ({aud}) {result['title']}")
        else:
            failures += 1
            print(f"[실패   ] ({aud}) {url} — {result.get('error')}")

    print(f"\n총 {len(targets)}건 · 실패 {failures}건")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
