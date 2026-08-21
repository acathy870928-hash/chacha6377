"""PDF → 정제된 라인 목록.

pypdf 로 페이지별 텍스트를 뽑은 뒤
  1) 페이지마다 반복되는 머리말/꼬리말/쪽번호 제거
  2) 공백·특수문자 정규화
  3) 빈 줄 정리
까지만 한다. 줄 병합(문장 잇기)은 구조를 아는 chunker 가 담당한다.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .models import Line, TermsDocument

# PDF 에서 자주 섞여 들어오는 잡문자
_SOFT_HYPHEN = "­"
_ZERO_WIDTH = re.compile(r"[​-‏﻿]")
_MULTISPACE = re.compile(r"[ \t 　]+")
_DOT_LEADER = re.compile(r"\.{4,}")  # 목차의 "제1조 ......... 3"
_PAGE_ONLY = re.compile(r"^[\-–—(\[]?\s*(?:page\s*)?\d{1,4}\s*(?:/\s*\d{1,4})?\s*[)\]\-–—]?$", re.I)
_DIGITS = re.compile(r"\d+")


def _normalize_line(raw: str) -> str:
    text = unicodedata.normalize("NFC", raw)
    text = text.replace(_SOFT_HYPHEN, "")
    text = _ZERO_WIDTH.sub("", text)
    text = _DOT_LEADER.sub(" ", text)
    text = _MULTISPACE.sub(" ", text)
    return text.strip()


def _fingerprint(text: str) -> str:
    """머리말/꼬리말 판정용 지문. 쪽번호처럼 페이지마다 바뀌는 숫자는 마스킹한다."""
    return _DIGITS.sub("#", text)


def _running_headers(pages: list[list[str]], *, edge: int = 2, ratio: float = 0.6) -> set[str]:
    """페이지 위/아래 `edge` 줄 중 여러 페이지에 반복 등장하는 줄의 지문을 모은다."""
    if len(pages) < 3:
        return set()

    counter: Counter[str] = Counter()
    for lines in pages:
        candidates = lines[:edge] + lines[-edge:]
        for text in set(candidates):
            if len(text) <= 80:
                counter[_fingerprint(text)] += 1

    threshold = max(3, int(len(pages) * ratio))
    return {fp for fp, count in counter.items() if count >= threshold}


def _strip_boilerplate(pages: list[list[str]]) -> list[list[str]]:
    headers = _running_headers(pages)
    cleaned: list[list[str]] = []
    for lines in pages:
        kept = []
        for idx, text in enumerate(lines):
            near_edge = idx < 2 or idx >= len(lines) - 2
            if _PAGE_ONLY.match(text):
                continue
            if near_edge and _fingerprint(text) in headers:
                continue
            kept.append(text)
        cleaned.append(kept)
    return cleaned


def _doc_id(source: Path | str, payload: bytes) -> str:
    stem = Path(source).stem or "doc"
    digest = hashlib.sha1(payload).hexdigest()[:8]
    return f"{stem}-{digest}"


def load_pdf(path: str | Path, *, title: str | None = None) -> TermsDocument:
    """약관 PDF 를 읽어 TermsDocument 로 변환한다."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - 설치 안내용
        raise RuntimeError("pypdf 가 필요합니다: pip install pypdf") from exc

    path = Path(path)
    reader = PdfReader(str(path))

    raw_pages: list[list[str]] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines = [_normalize_line(line) for line in text.splitlines()]
        raw_pages.append([line for line in lines if line])

    pages = _strip_boilerplate(raw_pages)
    empty_pages = [no for no, lines in enumerate(raw_pages, start=1) if not lines]

    doc_lines: list[Line] = []
    for page_no, lines in enumerate(pages, start=1):
        doc_lines.extend(Line(text=line, page=page_no) for line in lines)

    if not doc_lines:
        raise ValueError(
            f"{path.name}: {len(raw_pages)}페이지 전체에서 텍스트를 추출하지 못했습니다. "
            "텍스트 레이어가 없는 스캔 이미지 PDF 입니다. OCR 을 먼저 돌린 뒤 다시 넣으세요.\n"
            f"  예) ocrmypdf -l kor --rotate-pages --deskew '{path.name}' '{path.stem}_ocr.pdf'"
        )

    doc_title = title or _guess_title(pages, fallback=path.stem)
    return TermsDocument(
        doc_id=_doc_id(path, path.read_bytes()),
        title=doc_title,
        source=str(path),
        lines=doc_lines,
        page_count=len(pages),
        empty_pages=empty_pages,
    )


def scan_warning(doc: TermsDocument) -> str:
    """일부 페이지만 스캔 이미지인 경우의 경고 문구. 문제없으면 빈 문자열.

    실제 약관 PDF 는 본문은 텍스트인데 별표·부속서류만 스캔인 경우가 흔하다.
    그런 페이지는 조용히 통째로 빠지므로 반드시 알려야 한다.
    """
    if not doc.empty_pages or not doc.page_count:
        return ""
    ratio = len(doc.empty_pages) / doc.page_count
    shown = ", ".join(str(p) for p in doc.empty_pages[:10])
    more = f" 외 {len(doc.empty_pages) - 10}개" if len(doc.empty_pages) > 10 else ""
    return (
        f"주의: {doc.page_count}페이지 중 {len(doc.empty_pages)}페이지({ratio:.0%})에서 텍스트가 나오지 않았습니다"
        f" (p.{shown}{more}). 스캔 이미지 페이지로 보이며, 그 내용은 인덱스에 들어가지 않습니다."
        " 필요하면 OCR(ocrmypdf -l kor) 후 다시 넣으세요."
    )


def load_text(text: str, *, title: str = "약관", source: str = "<text>") -> TermsDocument:
    """평문 약관(테스트·붙여넣기용)을 TermsDocument 로 변환한다."""
    lines = [_normalize_line(line) for line in text.splitlines()]
    doc_lines = [Line(text=line, page=1) for line in lines if line]
    if not doc_lines:
        raise ValueError("빈 텍스트입니다.")
    return TermsDocument(
        doc_id=_doc_id(source if source != "<text>" else title, text.encode("utf-8")),
        title=title,
        source=source,
        lines=doc_lines,
        page_count=1,
    )


def _guess_title(pages: list[list[str]], *, fallback: str) -> str:
    """첫 페이지 상단에서 '○○ 이용약관' 같은 제목을 찾는다."""
    if not pages or not pages[0]:
        return fallback
    for text in pages[0][:6]:
        if re.search(r"(약관|방침|규정|정책|이용조건)\s*$", text) and len(text) <= 60:
            return text
    return fallback
