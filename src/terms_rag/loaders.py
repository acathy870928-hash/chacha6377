"""입력 파일 → TermsDocument 디스패처.

지원 형식
  - ``.pdf``            PDF (pypdf)
  - ``.html`` / ``.htm``  HTML (표준 라이브러리)
  - ``.docx``           Word (python-docx)
  - ``.txt`` / ``.md``    평문 (``.ocr.txt`` 는 OCR 결과로 인식해 쪽번호를 살린다)

약관(조문 구조)이든 보고서(제목 구조)든 같은 경로로 들어오고,
어느 쪽인지는 청킹 단계에서 판별한다.
"""

from __future__ import annotations

from pathlib import Path

from .docx_loader import load_docx
from .html_loader import load_html
from .models import TermsDocument
from .ocr import OCR_SUFFIX, load_ocr_text
from .pdf_loader import load_pdf, load_text

SUFFIXES = {".pdf", ".html", ".htm", ".docx", ".txt", ".md"}


def load_document(path: str | Path, *, title: str | None = None) -> TermsDocument:
    """확장자를 보고 알맞은 로더로 넘긴다."""
    path = Path(path)
    suffix = path.suffix.lower()

    # OCR 결과는 페이지 표지를 갖고 있어서 일반 텍스트와 다르게 읽는다
    if path.name.lower().endswith(OCR_SUFFIX):
        return load_ocr_text(path, title=title)
    if suffix == ".pdf":
        return load_pdf(path, title=title)
    if suffix in {".html", ".htm"}:
        return load_html(path, title=title)
    if suffix == ".docx":
        return load_docx(path, title=title)
    if suffix in {".txt", ".md"}:
        return load_text(
            path.read_text(encoding="utf-8", errors="replace"),
            title=title or path.stem,
            source=str(path),
        )
    if suffix == ".doc":
        raise ValueError(
            f"{path.name}: 구형 .doc 는 지원하지 않습니다. Word 에서 .docx 로 저장한 뒤 다시 시도하세요."
        )
    if suffix in {".hwp", ".hwpx"}:
        raise ValueError(
            f"{path.name}: 한글(.hwp) 은 지원하지 않습니다. PDF 또는 .docx 로 내보낸 뒤 다시 시도하세요."
        )
    raise ValueError(f"{path.name}: 지원하지 않는 형식입니다 ({', '.join(sorted(SUFFIXES))}).")
