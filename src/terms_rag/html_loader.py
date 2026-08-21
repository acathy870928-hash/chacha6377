"""HTML → 정제된 라인 목록.

표준 라이브러리 ``html.parser`` 만 쓴다(BeautifulSoup 등 의존성 없음).

- ``h1``~``h6`` 는 제목 줄로 표시해서 청킹기가 절 경계로 쓸 수 있게 한다.
- ``li`` 는 ``- `` 를 붙이고, 표는 행 단위로 ``셀 | 셀 | 셀`` 로 펼친다.
- ``script``/``style``/``nav`` 등 본문이 아닌 요소는 버린다.

약관을 HTML 로 받은 경우(홈페이지 게시 약관)와, 조문 구조가 없는 일반 문서
(보고서·가이드) 모두 이 로더를 탄다. 어느 쪽인지는 청킹기가 판단한다.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

from .models import Line, TermsDocument
from .pdf_loader import _normalize_line

BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer", "main", "blockquote",
    "dt", "dd", "figcaption", "pre", "address", "details", "summary",
}
HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}
SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "nav", "template", "iframe"}
VOID_BREAKS = {"br", "hr"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[Line] = []
        self.title = ""
        self._buffer: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._heading: int | None = None
        self._list_depth = 0
        self._cells: list[str] | None = None
        self._row: list[str] | None = None

    # -- 내부 --------------------------------------------------------------

    def _flush(self, *, heading: int | None = None) -> None:
        text = _normalize_line(" ".join(self._buffer))
        self._buffer.clear()
        if not text:
            return
        if self._row is not None:
            self._row.append(text)
            return
        prefix = "- " if self._list_depth and heading is None else ""
        self.lines.append(Line(text=f"{prefix}{text}", page=1, heading_level=heading))

    # -- 태그 --------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
            return
        if tag in VOID_BREAKS:
            self._flush()
            return
        if tag in HEADING_TAGS:
            self._flush()
            self._heading = HEADING_TAGS[tag]
            return
        if tag in {"ul", "ol"}:
            self._flush()
            self._list_depth += 1
            return
        if tag == "li":
            self._flush()
            return
        if tag == "tr":
            self._flush()
            self._row = []
            return
        if tag in {"td", "th"}:
            self._flush()
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "title":
            self.title = _normalize_line(" ".join(self._buffer))
            self._buffer.clear()
            self._in_title = False
            return
        if tag in HEADING_TAGS:
            self._flush(heading=self._heading)
            self._heading = None
            return
        if tag in {"td", "th"}:
            self._flush()
            return
        if tag == "tr":
            self._flush()
            row, self._row = self._row, None
            if row:
                self.lines.append(Line(text=" | ".join(row), page=1))
            return
        if tag in {"ul", "ol"}:
            self._flush()
            self._list_depth = max(0, self._list_depth - 1)
            return
        if tag in BLOCK_TAGS or tag == "li":
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data.strip():
            return
        self._buffer.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush(heading=self._heading)


def load_html(path: str | Path, *, title: str | None = None) -> TermsDocument:
    """HTML 파일을 TermsDocument 로 변환한다."""
    path = Path(path)
    return parse_html(path.read_text(encoding="utf-8", errors="replace"), title=title, source=str(path))


def parse_html(markup: str, *, title: str | None = None, source: str = "<html>") -> TermsDocument:
    parser = _Extractor()
    parser.feed(markup)
    parser.close()

    lines = _dedupe_blank(parser.lines)
    if not lines:
        raise ValueError(f"{source} 에서 본문 텍스트를 찾지 못했습니다.")

    doc_title = title or parser.title or _first_heading(lines) or Path(source).stem
    return TermsDocument(
        doc_id=_doc_id(source, markup),
        title=doc_title,
        source=source,
        lines=lines,
        page_count=1,
    )


def _first_heading(lines: list[Line]) -> str:
    for line in lines[:10]:
        if line.heading_level:
            return line.text
    return ""


def _dedupe_blank(lines: list[Line]) -> list[Line]:
    """빈 줄과 바로 이어지는 완전 중복 줄을 정리한다."""
    cleaned: list[Line] = []
    for line in lines:
        if not line.text.strip():
            continue
        if cleaned and cleaned[-1].text == line.text and cleaned[-1].heading_level == line.heading_level:
            continue
        cleaned.append(line)
    return cleaned


def _doc_id(source: str, payload: str) -> str:
    stem = re.sub(r"[^\w가-힣-]+", "-", Path(source).stem).strip("-") or "doc"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]
    return f"{stem[:40]}-{digest}"
