"""DOCX(Word) → 정제된 라인 목록.

``python-docx`` 로 본문을 순서대로 훑으면서

- 제목 스타일(Heading 1~6 / 제목 1~6)은 제목 줄로 표시하고,
- 목록 문단은 ``- `` 를 붙이고,
- 표는 행 단위로 ``셀 | 셀 | 셀`` 로 펼친다.

머리말/꼬리말(header1.xml, footer1.xml)은 본문이 아니므로 읽지 않는다.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import Line, TermsDocument
from .pdf_loader import _normalize_line

RE_HEADING = re.compile(r"^(?:heading|제목)\s*(\d)$", re.I)
RE_HEADING_ID = re.compile(r"^heading(\d)$", re.I)


def _heading_level(paragraph) -> int | None:
    style = paragraph.style
    if style is None:
        return None
    for candidate in (style.name or "", getattr(style, "style_id", "") or ""):
        match = RE_HEADING.match(candidate.strip()) or RE_HEADING_ID.match(candidate.strip())
        if match:
            level = int(match.group(1))
            return level if 1 <= level <= 6 else None
    return None


def _is_list(paragraph) -> bool:
    name = (paragraph.style.name or "") if paragraph.style else ""
    if "list" in name.lower() or "목록" in name:
        return True
    return paragraph._p.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr") is not None


def load_docx(path: str | Path, *, title: str | None = None) -> TermsDocument:
    """DOCX 파일을 TermsDocument 로 변환한다."""
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover - 설치 안내용
        raise RuntimeError("python-docx 가 필요합니다: pip install python-docx") from exc

    path = Path(path)
    document = docx.Document(str(path))
    body = document.element.body

    lines: list[Line] = []
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = _normalize_line(paragraph.text)
            if not text:
                continue
            level = _heading_level(paragraph)
            prefix = "- " if level is None and _is_list(paragraph) else ""
            lines.append(Line(text=f"{prefix}{text}", page=1, heading_level=level))
        elif tag == "tbl":
            table = Table(child, document)
            lines.extend(_table_lines(table))

    if not lines:
        raise ValueError(f"{path} 에서 본문 텍스트를 찾지 못했습니다.")

    doc_title = title or _core_title(document) or _cover_title(lines) or _first_heading(lines) or path.stem
    return TermsDocument(
        doc_id=_doc_id(path),
        title=doc_title,
        source=str(path),
        lines=lines,
        page_count=1,
    )


def _table_lines(table) -> list[Line]:
    lines: list[Line] = []
    for row in table.rows:
        cells = [_normalize_line(cell.text) for cell in row.cells]
        # 병합된 셀은 같은 텍스트가 반복되므로 연속 중복을 접는다
        collapsed: list[str] = []
        for cell in cells:
            if not collapsed or collapsed[-1] != cell:
                collapsed.append(cell)
        text = " | ".join(c for c in collapsed if c)
        if text:
            lines.append(Line(text=text, page=1))
    return lines


def _core_title(document) -> str:
    try:
        return _normalize_line(document.core_properties.title or "")
    except Exception:  # pragma: no cover - 손상된 메타데이터 방어
        return ""


def _cover_title(lines: list[Line]) -> str:
    """제목 스타일이 없는 표지 문서: 첫 제목 줄 앞의 짧은 첫 줄을 제목으로 본다."""
    for line in lines[:3]:
        if line.heading_level:
            return ""
        if len(line.text) <= 60:
            return line.text
    return ""


def _first_heading(lines: list[Line]) -> str:
    for line in lines[:10]:
        if line.heading_level:
            return line.text
    return ""


def _doc_id(path: Path) -> str:
    stem = re.sub(r"[^\w가-힣-]+", "-", path.stem).strip("-") or "doc"
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:8]
    return f"{stem[:40]}-{digest}"
