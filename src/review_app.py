"""2단계 — 담당자 확인 웹 UI (Flask).

    python -m src.cli review     →  http://127.0.0.1:5000

검수 대기 목록에서 승인/반려를 누르면 곧바로 data/articles.json 에 반영되고,
'MD 변환' 버튼을 누르면 승인 건만 output/ 에 마크다운으로 떨어진다.
"""

from __future__ import annotations

from pathlib import Path

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from .classifier import DEFAULT_FILTER_CONFIG
from .export_md import DEFAULT_OUTPUT, export
from .models import (
    ALL_STATUSES,
    CATEGORIES,
    STATUS_APPROVED,
    STATUS_LABELS,
    STATUS_PENDING,
    STATUS_REJECTED,
)
from .store import ArticleStore

BASE_DIR = Path(__file__).resolve().parent.parent


def _reviewer_from(req) -> str:
    return (req.form.get("reviewer") or req.cookies.get("reviewer") or "").strip()


def create_app(db_path: str | Path, output_dir: str | Path = DEFAULT_OUTPUT) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.secret_key = "insurance-news-review"  # 로컬 검수 도구라 세션 암호는 고정
    app.config["DB_PATH"] = str(db_path)
    app.config["OUTPUT_DIR"] = str(output_dir)

    def store() -> ArticleStore:
        # 요청마다 새로 읽어 CLI 수집과 동시에 써도 어긋나지 않게 한다.
        return ArticleStore(app.config["DB_PATH"])

    @app.context_processor
    def inject_globals():
        return {
            "STATUS_LABELS": STATUS_LABELS,
            "ALL_STATUSES": ALL_STATUSES,
            "CATEGORIES": CATEGORIES,
            "FILTER_CONFIG": str(DEFAULT_FILTER_CONFIG),
        }

    # ── 목록 ──────────────────────────────────────────────────────
    @app.route("/")
    def index():
        st = store()
        status = request.args.get("status", STATUS_PENDING)
        query = (request.args.get("q") or "").strip()
        source = (request.args.get("source") or "").strip()

        items = st.all() if status == "all" else st.by_status(status)
        if query:
            low = query.lower()
            items = [
                a
                for a in items
                if low in a.title.lower()
                or low in a.summary.lower()
                or low in a.content.lower()
            ]
        if source:
            items = [a for a in items if a.source == source]

        return render_template(
            "list.html",
            articles=items,
            counts=st.counts(),
            total=len(st),
            status=status,
            query=query,
            source=source,
            sources=sorted({a.source for a in st.all()}),
            reviewer=request.cookies.get("reviewer", ""),
        )

    # ── 상세/수정 ─────────────────────────────────────────────────
    @app.route("/article/<article_id>")
    def detail(article_id: str):
        article = store().get(article_id)
        if article is None:
            flash("기사를 찾을 수 없습니다.", "error")
            return redirect(url_for("index"))
        return render_template(
            "detail.html",
            a=article,
            reviewer=request.cookies.get("reviewer", ""),
            back=request.args.get("back") or url_for("index"),
        )

    @app.route("/article/<article_id>/save", methods=["POST"])
    def save(article_id: str):
        st = store()
        tags = [t.strip() for t in (request.form.get("tags") or "").split(",") if t.strip()]
        status = request.form.get("status") or STATUS_PENDING
        if status not in ALL_STATUSES:
            status = STATUS_PENDING
        updated = st.update_review(
            article_id,
            status=status,
            category=request.form.get("category"),
            tags=tags,
            effective_date=(request.form.get("effective_date") or "").strip(),
            reviewer=_reviewer_from(request),
            reviewer_note=request.form.get("reviewer_note") or "",
            edited_title=request.form.get("edited_title") or "",
            edited_summary=request.form.get("edited_summary") or "",
        )
        if updated is None:
            flash("기사를 찾을 수 없습니다.", "error")
            return redirect(url_for("index"))
        st.save()
        flash(f"'{updated.display_title[:30]}…' 저장 완료 ({STATUS_LABELS[updated.status]})", "ok")

        resp = redirect(request.form.get("back") or url_for("index"))
        if _reviewer_from(request):
            resp.set_cookie("reviewer", _reviewer_from(request), max_age=60 * 60 * 24 * 90)
        return resp

    # ── 목록에서 바로 판단 ────────────────────────────────────────
    @app.route("/decide/<article_id>/<decision>", methods=["POST"])
    def decide(article_id: str, decision: str):
        mapping = {"approve": STATUS_APPROVED, "reject": STATUS_REJECTED, "reset": STATUS_PENDING}
        if decision not in mapping:
            flash("알 수 없는 요청입니다.", "error")
            return redirect(url_for("index"))
        st = store()
        updated = st.update_review(
            article_id, status=mapping[decision], reviewer=_reviewer_from(request)
        )
        if updated is None:
            flash("기사를 찾을 수 없습니다.", "error")
        else:
            st.save()
        resp = redirect(request.form.get("back") or url_for("index"))
        if _reviewer_from(request):
            resp.set_cookie("reviewer", _reviewer_from(request), max_age=60 * 60 * 24 * 90)
        return resp

    @app.route("/bulk", methods=["POST"])
    def bulk():
        ids = request.form.getlist("ids")
        action = request.form.get("action")
        mapping = {"approve": STATUS_APPROVED, "reject": STATUS_REJECTED, "reset": STATUS_PENDING}
        if action not in mapping or not ids:
            flash("선택된 기사가 없습니다.", "error")
            return redirect(request.form.get("back") or url_for("index"))
        st = store()
        for article_id in ids:
            st.update_review(article_id, status=mapping[action], reviewer=_reviewer_from(request))
        st.save()
        flash(f"{len(ids)}건을 '{STATUS_LABELS[mapping[action]]}' 처리했습니다.", "ok")
        resp = redirect(request.form.get("back") or url_for("index"))
        if _reviewer_from(request):
            resp.set_cookie("reviewer", _reviewer_from(request), max_age=60 * 60 * 24 * 90)
        return resp

    # ── MD 변환 ───────────────────────────────────────────────────
    @app.route("/export", methods=["POST"])
    def do_export():
        st = store()
        result = export(st, app.config["OUTPUT_DIR"], verbose=False)
        if result["count"] == 0:
            flash("승인된 기사가 없어 변환할 내용이 없습니다.", "error")
        else:
            flash(
                f"승인 {result['count']}건을 마크다운으로 변환했습니다 → {result['articles_dir']}",
                "ok",
            )
        return redirect(request.form.get("back") or url_for("index", status=STATUS_APPROVED))

    return app
