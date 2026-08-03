"""파이프라인 3단계 회귀 테스트. 네트워크 없이 돈다.

    .venv/bin/python -m tests.test_pipeline
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.classifier import Classifier  # noqa: E402
from src.collect import clean_text, extract_body, summarize  # noqa: E402
from src.export_md import export, render_article  # noqa: E402
from src.models import (  # noqa: E402
    Article,
    STATUS_APPROVED,
    STATUS_AUTO_PROMO,
    STATUS_PENDING,
    make_id,
    normalize_url,
)
from src.review_app import create_app  # noqa: E402
from src.store import ArticleStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ✓ {name}")
    else:
        FAILED.append(f"{name} — {detail}")
        print(f"  ✗ {name} — {detail}")


def make(title: str, content: str = "", url: str = "https://ex.com/a", **kw) -> Article:
    return Article(id=make_id(url), url=url, title=title, content=content, source="테스트", **kw)


# ── 1. URL 정규화 / 중복 제거 ─────────────────────────────────────
def test_url_normalization():
    print("\n[URL 정규화]")
    a = normalize_url("http://m.insweek.co.kr/news/view?idxno=1&utm_source=naver")
    b = normalize_url("https://www.insweek.co.kr/news/view?idxno=1")
    check("추적 파라미터·모바일 도메인 제거 후 동일 URL", a == b, f"{a} != {b}")
    check("같은 기사면 같은 id", make_id(a) == make_id(b))


# ── 2. 본문 추출 / 요약 ───────────────────────────────────────────
def test_extraction():
    print("\n[본문 추출]")
    html = """
    <html><body>
      <nav>메뉴</nav>
      <div id="article-view-content-div">
        <p>금융위원회는 보험업법 시행령 개정안을 입법예고했다.</p>
        <script>var x = 1;</script>
        <p>%s</p>
        <p>저작권자 © 무단전재 및 재배포 금지</p>
      </div>
    </body></html>
    """ % ("개정안은 5세대 실손보험 상품설계기준을 규정한다. " * 12)
    body = extract_body(html)
    check("본문 컨테이너에서 텍스트 추출", "보험업법 시행령" in body)
    check("script 태그 제거", "var x" not in body)
    check("저작권 문구 제거", "무단전재" not in body, body[-60:])
    check("요약 길이 제한", len(summarize(body, 120)) <= 130, str(len(summarize(body, 120))))
    check("빈 입력에도 안 죽음", clean_text("") == "" and summarize("") == "")


# ── 3. 자동 분류 ──────────────────────────────────────────────────
def test_classifier():
    print("\n[자동 분류]")
    clf = Classifier.from_file(ROOT / "config" / "filters.yaml")

    promo = make(
        "○○생명, 신상품 출시…가입 시 경품 증정 이벤트",
        "가입하면 사은품을 증정하는 프로모션을 진행한다.",
    )
    clf.apply(promo)
    check("상품 홍보 기사 자동 제외", promo.status == STATUS_AUTO_PROMO, promo.auto_reason)

    policy = make(
        "금융위, 보험업법 시행령 개정안 입법예고",
        "금융위원회는 보험업감독규정 개정안을 규정변경예고했다. 5세대 실손 상품설계기준과 "
        "기본자본 지급여력비율을 도입한다.",
    )
    clf.apply(policy)
    check("제도 기사 검수 대기", policy.status == STATUS_PENDING, policy.auto_reason)
    check("제도 점수 > 홍보 점수", policy.policy_score > policy.promo_score)

    noise = make("배우 ○○○, 신작 영화 촬영 시작", "영화 촬영이 시작됐다.")
    clf.apply(noise)
    check("무관한 기사 자동 제외", noise.status == "auto_lowrel", noise.auto_reason)

    # 홍보 문구가 섞여도 제도 내용이 우세하면 살아남아야 한다
    mixed = make(
        "◇◇생명, 표준약관 개정 반영해 실손 전환 안내",
        "보험업감독규정과 표준약관 개정에 따라 5세대 실손 전환 절차가 바뀐다. "
        "금융위원회가 예고한 상품설계기준이 적용된다. 회사는 이벤트를 진행한다.",
    )
    clf.apply(mixed)
    check("제도 내용 우세 시 홍보 문구 있어도 통과", mixed.status == STATUS_PENDING, mixed.auto_reason)

    dropped = clf.classify(make("[특징주] ○○보험 주가 급등"))
    check("시황 기사는 수집 단계에서 폐기", dropped.dropped is True)

    check("분류 태그 자동 부여", policy.category != "미분류", policy.category)


# ── 4. 저장소: 담당자 판단 보존 ───────────────────────────────────
def test_store_preserves_review():
    print("\n[담당자 판단 보존]")
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "articles.json"
        store = ArticleStore(db)
        a = make("금융위 시행령 개정", "본문", url="https://ex.com/1")
        store.upsert(a)
        store.update_review(
            a.id, status=STATUS_APPROVED, reviewer="김담당", reviewer_note="중요", category="실손의료보험"
        )
        store.save()

        # 재수집 시뮬레이션 — 같은 기사를 자동 분류 결과와 함께 다시 넣는다
        again = make("금융위 시행령 개정", "본문 " * 200, url="https://ex.com/1")
        again.status = STATUS_PENDING
        again.category = "미분류"
        store2 = ArticleStore(db)
        store2.upsert(again)
        store2.save()

        reloaded = ArticleStore(db).get(a.id)
        check("승인 상태 유지", reloaded.status == STATUS_APPROVED, reloaded.status)
        check("담당자 메모 유지", reloaded.reviewer_note == "중요")
        check("담당자가 고른 분류 유지", reloaded.category == "실손의료보험", reloaded.category)
        check("본문은 더 긴 쪽으로 보강", len(reloaded.content) > 10)
        check("중복 저장 안 됨", len(ArticleStore(db)) == 1)
    finally:
        shutil.rmtree(tmp)


# ── 5. MD 변환 ────────────────────────────────────────────────────
def test_export():
    print("\n[MD 변환]")
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "articles.json"
        out = tmp / "output"
        store = ArticleStore(db)

        ok = make("금융위, 시행령 개정안 입법예고", "본문입니다.\n\n두 번째 문단.", url="https://ex.com/ok")
        ok.status = STATUS_APPROVED
        ok.category = "실손의료보험"
        ok.effective_date = "2026-07-01"
        ok.reviewer = "김담당"
        ok.reviewer_note = "시행일 주의"
        ok.published_at = "2026-07-01T09:00:00+09:00"
        store.upsert(ok)

        no = make("○○생명 신상품 출시", "홍보 본문", url="https://ex.com/no")
        no.status = STATUS_AUTO_PROMO
        store.upsert(no)
        store.save()

        result = export(store, out, verbose=False)
        check("승인 건만 변환", result["count"] == 1, str(result["count"]))

        md = Path(result["files"][0]).read_text(encoding="utf-8")
        check("front matter 로 시작", md.startswith("---\n"))
        check("category 메타 포함", 'category: "실손의료보험"' in md)
        check("시행일 메타 포함", 'effective_date: "2026-07-01"' in md)
        check("담당자 메모 포함", "시행일 주의" in md)
        check("원문 링크 포함", "https://ex.com/ok" in md)
        check("홍보 기사 미포함", "신상품 출시" not in md)

        index = Path(result["index"]).read_text(encoding="utf-8")
        check("목차에 분류별 묶임", "## 실손의료보험" in index)
        bundle = Path(result["bundle"]).read_text(encoding="utf-8")
        check("통합본 생성", "보험 제도 변경 뉴스 통합본" in bundle and "입법예고" in bundle)

        # 승인을 취소하면 기존 MD 가 사라져야 한다
        store.update_review(ok.id, status="rejected")
        store.save()
        result2 = export(store, out, verbose=False)
        check("승인 취소 시 MD 제거", result2["count"] == 0 and not list((out / "articles").glob("*.md")))

        # 파일명에 경로 구분자가 새지 않는지
        weird = make("제도/변경: \"실손\" *주의*", "본문", url="https://ex.com/weird")
        weird.status = STATUS_APPROVED
        store.upsert(weird)
        store.save()
        r3 = export(store, out, verbose=False)
        check("특수문자 제목도 안전한 파일명", Path(r3["files"][0]).exists())
    finally:
        shutil.rmtree(tmp)


def test_render_no_body():
    print("\n[예외 입력]")
    a = make("본문 없는 기사", "", url="https://ex.com/empty")
    a.status = STATUS_APPROVED
    md = render_article(a)
    check("본문 없어도 MD 생성", md.startswith("---") and "본문 없는 기사" in md)


# ── 6. 검수 웹 UI ─────────────────────────────────────────────────
def test_review_app():
    print("\n[검수 웹 UI]")
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "articles.json"
        out = tmp / "output"
        store = ArticleStore(db)
        a = make("금융위, 보험업법 시행령 개정안 입법예고", "본문", url="https://ex.com/w1")
        b = make("○○생명 신상품 출시", "홍보", url="https://ex.com/w2")
        b.status = STATUS_AUTO_PROMO
        store.upsert(a)
        store.upsert(b)
        store.save()

        app = create_app(db, out)
        app.config["TESTING"] = True
        client = app.test_client()

        r = client.get("/")
        check("목록 페이지 응답", r.status_code == 200, str(r.status_code))
        html = r.get_data(as_text=True)
        check("검수 대기 기사 노출", "입법예고" in html)
        check("자동제외 기사는 기본 탭에 없음", "신상품 출시" not in html)

        r = client.get("/?status=auto_promo")
        check("자동제외 탭에서 조회 가능", "신상품 출시" in r.get_data(as_text=True))

        r = client.get(f"/article/{a.id}")
        check("상세 페이지 응답", r.status_code == 200 and "본문" in r.get_data(as_text=True))

        r = client.post(f"/decide/{a.id}/approve", data={"reviewer": "김담당"})
        check("승인 처리", r.status_code == 302 and ArticleStore(db).get(a.id).status == STATUS_APPROVED)
        check("담당자 이름 기록", ArticleStore(db).get(a.id).reviewer == "김담당")

        r = client.post(
            f"/article/{a.id}/save",
            data={
                "status": STATUS_APPROVED,
                "category": "실손의료보험",
                "tags": "실손, 금융위",
                "effective_date": "2026-07-01",
                "edited_summary": "담당자가 다듬은 요약",
                "reviewer_note": "메모",
                "reviewer": "김담당",
            },
        )
        saved = ArticleStore(db).get(a.id)
        check("상세 저장 반영", saved.category == "실손의료보험" and saved.tags == ["실손", "금융위"])
        check("수정 요약 반영", saved.display_summary == "담당자가 다듬은 요약")

        r = client.post("/bulk", data={"ids": [b.id], "action": "approve", "reviewer": "김담당"})
        check("일괄 승인", ArticleStore(db).get(b.id).status == STATUS_APPROVED)

        r = client.post("/export")
        check("웹에서 MD 변환 실행", r.status_code == 302)
        files = list((out / "articles").glob("*.md"))
        check("MD 파일 생성됨", len(files) == 2, str(len(files)))
        md = files[0].read_text(encoding="utf-8")
        check("변환 결과에 front matter", md.startswith("---"))

        r = client.get("/article/없는아이디")
        check("없는 기사 요청 시 리다이렉트", r.status_code == 302)
    finally:
        shutil.rmtree(tmp)


# ── 7. 시드 데이터 전 구간 ────────────────────────────────────────
def test_seed_end_to_end():
    print("\n[시드 데이터 전 구간]")
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "articles.json"
        clf = Classifier.from_file(ROOT / "config" / "filters.yaml")
        store = ArticleStore(db)
        payload = json.loads((ROOT / "data" / "seed_articles.json").read_text(encoding="utf-8"))
        for item in payload["articles"]:
            art = Article.from_dict(item)
            art.summary = summarize(art.content)
            clf.apply(art, source_weight=float(item.get("source_weight", 1.0)))
            store.upsert(art)
        store.save()

        counts = store.counts()
        check("시드 10건 적재", len(store) == 10, str(len(store)))
        check("홍보 3건 자동 제외", counts.get(STATUS_AUTO_PROMO) == 3, str(counts))
        check("제도 7건 검수 대기", counts.get(STATUS_PENDING) == 7, str(counts))

        promo_titles = [a.title for a in store.by_status(STATUS_AUTO_PROMO)]
        check("경품·수상·신상품 기사가 걸러짐", all("demo.example" in a.url for a in store.by_status(STATUS_AUTO_PROMO)), str(promo_titles))
    finally:
        shutil.rmtree(tmp)


def main() -> int:
    print("보험 제도 뉴스 파이프라인 테스트")
    for fn in (
        test_url_normalization,
        test_extraction,
        test_classifier,
        test_store_preserves_review,
        test_export,
        test_render_no_body,
        test_review_app,
        test_seed_end_to_end,
    ):
        fn()
    print(f"\n{'─' * 52}")
    print(f"통과 {len(PASSED)}건 · 실패 {len(FAILED)}건")
    for f in FAILED:
        print(f"  ✗ {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
