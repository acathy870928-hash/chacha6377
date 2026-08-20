#!/usr/bin/env python3
"""RSS 수집을 한 번 돌린다. 크론에 걸어두면 된다.

  */30 * * * * cd /srv/news && python3 scripts/collect.py >> logs/collect.log 2>&1
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.collector import collect_all  # noqa: E402
from app.db import init_db, now_iso  # noqa: E402


def main() -> None:
    init_db()
    print(f"--- {now_iso()} 수집 시작")
    for r in collect_all():
        if r["error"]:
            print(f"  {r['publisher']:10s} 실패: {r['error']}")
        else:
            print(f"  {r['publisher']:10s} 신규 {r['created']} / 갱신 {r['updated']}")


if __name__ == "__main__":
    main()
