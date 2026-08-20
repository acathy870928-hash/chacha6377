#!/usr/bin/env python3
"""샘플 기사를 넣어 화면을 바로 확인할 수 있게 한다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db, session  # noqa: E402
from app.store import upsert_article  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "seed" / "sample_articles.json"


def main() -> None:
    init_db()
    articles = json.loads(SEED.read_text(encoding="utf-8"))
    created = updated = 0
    with session() as conn:
        for item in articles:
            _, action = upsert_article(conn, item)
            created += action == "created"
            updated += action == "updated"
    print(f"샘플 투입 완료 · 신규 {created}건 / 갱신 {updated}건")


if __name__ == "__main__":
    main()
