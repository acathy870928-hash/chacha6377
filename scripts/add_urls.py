#!/usr/bin/env python3
"""기사 URL 목록을 받아 본문을 긁어 후보로 등록한다.

  python3 scripts/add_urls.py                      # seed/rep_urls.json 사용
  python3 scripts/add_urls.py <url> [<url> ...]    # 인자로 직접 지정
  python3 scripts/add_urls.py --audience fa <url>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collector import collect_url  # noqa: E402
from app.db import init_db  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "seed" / "rep_urls.json"


def main() -> int:
    args = sys.argv[1:]
    audience = "rep"
    if "--audience" in args:
        i = args.index("--audience")
        audience = args[i + 1]
        del args[i:i + 2]

    urls = args
    if not urls:
        data = json.loads(SEED.read_text(encoding="utf-8"))
        urls = data.get("urls", [])
        audience = data.get("audience", audience)

    init_db()
    failures = 0
    for url in urls:
        result = collect_url(url, audience=audience)
        if result.get("ok"):
            print(f"[{result['action']}] {result['title']}")
        else:
            failures += 1
            print(f"[실패] {url} — {result.get('error')}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
