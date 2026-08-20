"""사업단 뉴스 셀렉 · 공유 서버.

흐름:
  수집기(RSS/URL) → 우선 검토 후보 → 대표가 어드민에서 선택 → 브리핑 링크 생성
  → 카톡 단톡방에 링크 하나 → FA가 눌러서 제목 + 기사 확인
"""
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import collector, store
from .config import BASE_DIR, INGEST_API_KEY, ORG_NAME, PUBLIC_BASE_URL, SESSION_COOKIE
from .db import init_db, now_kst, session
from .security import check_password, make_token, verify_token

app = FastAPI(title="사업단 뉴스 브리핑", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

AUDIENCE_LABEL = {"rep": "사업단 대표용", "fa": "FA용", "both": "공통"}


@app.on_event("startup")
def _startup() -> None:
    init_db()


# ------------------------------------------------------------------ 인증

def require_admin(request: Request) -> bool:
    if not verify_token(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=307, headers={"Location": "/admin/login"})
    return True


@app.exception_handler(HTTPException)
async def _redirect_on_auth(request: Request, exc: HTTPException):
    if exc.status_code == 307 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    if exc.status_code == 404:
        return templates.TemplateResponse(request, "404.html", {"org": ORG_NAME}, status_code=404
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/admin/login", response_class=HTMLResponse)
def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(request, "login.html", {"error": error, "org": ORG_NAME}
    )


@app.post("/admin/login")
def login(password: str = Form("")):
    if not check_password(password):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    response = RedirectResponse("/admin", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, make_token(), httponly=True, samesite="lax", max_age=60 * 60 * 24 * 14
    )
    return response


@app.get("/admin/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ------------------------------------------------------------------ 어드민

@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_home(
    request: Request,
    audience: str = "rep",
    status: str = "candidate",
    publisher: str = "",
    q: str = "",
    notice: str = "",
    _: bool = Depends(require_admin),
):
    if audience not in ("rep", "fa", "all"):
        audience = "rep"
    articles = store.list_candidates(
        status=status,
        publisher=publisher,
        query=q,
        audience="" if audience == "all" else audience,
    )
    counts = store.view_counts([a["id"] for a in articles])
    for a in articles:
        a["views"] = counts.get(a["id"], 0)

    today = now_kst().strftime("%-m/%-d")
    default_title = f"{today} {ORG_NAME} 뉴스 브리핑"

    return templates.TemplateResponse(request, "admin.html", {"articles": articles,
        "publishers": store.publishers(),
        "audience": audience,
        "status": status,
        "publisher": publisher,
        "q": q,
        "notice": notice,
        "default_title": default_title,
        "briefings": store.list_briefings(limit=8),
        "org": ORG_NAME,
        "audience_label": AUDIENCE_LABEL,
    })


@app.post("/admin/add-url")
def admin_add_url(
    url: str = Form(""),
    audience: str = Form("rep"),
    _: bool = Depends(require_admin),
):
    """대표가 기사 링크를 그대로 붙여넣어 후보에 추가한다."""
    result = collector.collect_url(url, audience=audience)
    if result.get("ok"):
        notice = f"추가됨: {result['title']}"
    else:
        notice = f"실패: {result.get('error', '알 수 없는 오류')}"
    return RedirectResponse(f"/admin?audience={audience}&notice={notice}", status_code=303)


@app.post("/admin/collect")
def admin_collect(_: bool = Depends(require_admin), audience: str = Form("rep")):
    """RSS 피드를 지금 한 번 수집한다."""
    results = collector.collect_all()
    created = sum(r["created"] for r in results)
    updated = sum(r["updated"] for r in results)
    errors = [f"{r['publisher']}({r['error'].split(':')[0]})" for r in results if r["error"]]
    notice = f"수집 완료 · 신규 {created}건 / 갱신 {updated}건"
    if errors:
        notice += f" · 실패: {', '.join(errors)}"
    return RedirectResponse(f"/admin?audience={audience}&notice={notice}", status_code=303)


def _ids(raw: list[str]) -> list[int]:
    out = []
    for value in raw:
        try:
            out.append(int(value))
        except (TypeError, ValueError):
            continue
    return out


@app.post("/admin/reject")
def admin_reject(
    article_ids: list[str] = Form(default=[]),
    audience: str = Form("rep"),
    _: bool = Depends(require_admin),
):
    n = store.set_status(_ids(article_ids), "rejected")
    return RedirectResponse(f"/admin?audience={audience}&notice={n}건 제외함", status_code=303)


@app.post("/admin/audience")
def admin_audience(
    article_ids: list[str] = Form(default=[]),
    target: str = Form("rep"),
    audience: str = Form("rep"),
    _: bool = Depends(require_admin),
):
    n = store.set_audience(_ids(article_ids), target)
    label = AUDIENCE_LABEL.get(target, target)
    return RedirectResponse(
        f"/admin?audience={audience}&notice={n}건을 {label}으로 옮김", status_code=303
    )


@app.post("/admin/fa-point")
def admin_fa_point(
    article_id: int = Form(...),
    fa_point: str = Form(""),
    audience: str = Form("rep"),
    _: bool = Depends(require_admin),
):
    store.set_fa_point(article_id, fa_point)
    return RedirectResponse(f"/admin?audience={audience}&notice=코멘트 저장됨", status_code=303)


@app.post("/admin/briefing")
def admin_create_briefing(
    article_ids: list[str] = Form(default=[]),
    title: str = Form(""),
    intro: str = Form(""),
    audience: str = Form("rep"),
    _: bool = Depends(require_admin),
):
    ids = _ids(article_ids)
    if not ids:
        return RedirectResponse(
            f"/admin?audience={audience}&notice=기사를 하나 이상 선택하세요", status_code=303
        )
    target = audience if audience in ("rep", "fa") else "both"
    briefing = store.create_briefing(title or "뉴스 브리핑", intro, ids, audience=target)
    return RedirectResponse(f"/admin/share/{briefing['code']}", status_code=303)


@app.get("/admin/share/{code}", response_class=HTMLResponse)
def admin_share(request: Request, code: str, _: bool = Depends(require_admin)):
    briefing = store.get_briefing(code)
    if not briefing:
        raise HTTPException(status_code=404, detail="브리핑을 찾을 수 없습니다")

    link = f"{PUBLIC_BASE_URL}/b/{code}"
    lines = [f"📌 {briefing['title']}"]
    if briefing["intro"]:
        lines.append(briefing["intro"])
    lines.append("")
    for i, a in enumerate(briefing["articles"], start=1):
        lines.append(f"{i}. {a['title']}")
        if a["fa_point"]:
            lines.append(f"   └ {a['fa_point']}")
    lines += ["", f"👉 전문 보기: {link}"]

    return templates.TemplateResponse(request, "share.html", {"briefing": briefing,
        "link": link,
        "kakao_text": "\n".join(lines),
        "base_url": PUBLIC_BASE_URL,
        "org": ORG_NAME,
        "audience_label": AUDIENCE_LABEL,
    })


@app.get("/admin/briefings", response_class=HTMLResponse)
def admin_briefings(request: Request, _: bool = Depends(require_admin)):
    return templates.TemplateResponse(request, "briefings.html", {"briefings": store.list_briefings(limit=100),
        "base_url": PUBLIC_BASE_URL,
        "org": ORG_NAME,
        "audience_label": AUDIENCE_LABEL,
    })


# ------------------------------------------------------- 공개 페이지 (카톡에서 열림)

@app.get("/b/{code}", response_class=HTMLResponse)
def public_briefing(request: Request, code: str):
    briefing = store.get_briefing(code)
    if not briefing:
        raise HTTPException(status_code=404, detail="브리핑을 찾을 수 없습니다")
    store.log_view(None, briefing["id"])
    return templates.TemplateResponse(request, "briefing.html", {"briefing": briefing,
        "base_url": PUBLIC_BASE_URL,
        "org": ORG_NAME,
    })


@app.get("/a/{slug}", response_class=HTMLResponse)
def public_article(request: Request, slug: str, b: str = ""):
    """제목과 본문만 보여주는 기사 페이지."""
    article = store.get_article_by_slug(slug)
    if not article:
        raise HTTPException(status_code=404, detail="기사를 찾을 수 없습니다")

    briefing = store.get_briefing(b) if b else None
    store.log_view(article["id"], briefing["id"] if briefing else None)

    paragraphs = [p.strip() for p in article["body"].split("\n") if p.strip()]

    return templates.TemplateResponse(request, "article.html", {"article": article,
        "paragraphs": paragraphs,
        "briefing": briefing,
        "base_url": PUBLIC_BASE_URL,
        "org": ORG_NAME,
    })


# ------------------------------------------------------------------ 수집기 연동 API

@app.post("/api/ingest")
async def api_ingest(request: Request, x_api_key: str = Header(default="")):
    """기존 수집기가 기사를 밀어 넣는 곳.

    body: {"articles": [{title, body, publisher, origin_url, published_at, signal?, audience?}, ...]}
    """
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="잘못된 API 키")

    payload: Any = await request.json()
    items = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="articles 배열이 필요합니다")

    created = updated = failed = 0
    errors: list[str] = []
    with session() as conn:
        for item in items:
            try:
                _, action = store.upsert_article(conn, item)
                created += action == "created"
                updated += action == "updated"
            except (ValueError, TypeError) as exc:
                failed += 1
                if len(errors) < 5:
                    errors.append(str(exc))

    return {"created": created, "updated": updated, "failed": failed, "errors": errors}


@app.post("/api/collect")
def api_collect(x_api_key: str = Header(default="")):
    """RSS 수집을 외부(크론 등)에서 돌릴 때."""
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="잘못된 API 키")
    return {"results": collector.collect_all()}


@app.get("/healthz")
def healthz():
    return {"ok": True, "time": datetime.now().isoformat(timespec="seconds")}
