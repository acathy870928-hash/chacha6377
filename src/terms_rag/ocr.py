"""스캔 PDF → 텍스트. 청킹 앞단의 전처리 모듈.

스캔 이미지 약관은 텍스트 레이어가 없어서 어떤 청킹기도 손댈 수 없다. 이 모듈이
그 앞을 막는다. 청킹 모듈(`chunker` / `doc_chunker`)과는 완전히 분리돼 있고,
서로를 import 하지 않는다.

백엔드 세 가지 — 있는 것 중에서 고른다(`backend="auto"`).

| 백엔드 | 필요한 것 | 결과 | 언제 |
|---|---|---|---|
| ``ocrmypdf`` | ocrmypdf + tesseract-ocr-kor | 텍스트 레이어가 박힌 PDF **+** 텍스트 | 가장 좋음. 원본 PDF 를 그대로 재사용 가능 |
| ``tesseract`` | pdftoppm(poppler) + tesseract | 텍스트만 | ocrmypdf 가 없을 때 |
| ``claude``   | anthropic API 키 | 텍스트만 | 시스템 도구를 못 깔 때. 표·세로쓰기에 강하지만 느리고 비용이 든다 |

결과 텍스트는 페이지 표지를 넣어 저장하므로(`<<<PAGE 3>>>`), 청킹 후에도 인용에
쪽번호가 그대로 남는다.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .models import Line, TermsDocument
from .pdf_loader import _doc_id, _normalize_line

PAGE_MARK = "<<<PAGE {}>>>"
RE_PAGE_MARK = re.compile(r"^<<<PAGE (\d+)>>>$")
OCR_SUFFIX = ".ocr.txt"

BACKENDS = ("ocrmypdf", "tesseract", "claude")

TRANSCRIBE_PROMPT = """이 PDF 페이지들의 텍스트를 그대로 옮겨 적으십시오.

규칙:
- 각 페이지 시작에 `<<<PAGE N>>>` 을 넣으십시오. N 은 이 요청의 시작 페이지 번호부터 셉니다.
- 원문을 요약하거나 고치지 말고 보이는 그대로 옮기십시오. 오탈자도 그대로 두십시오.
- 조문 구조(제1조, ①②③, 1. 2. 3., 가. 나. 다.)와 줄바꿈을 살리십시오.
- 표는 한 행을 한 줄로, 셀 사이를 ` | ` 로 구분하십시오.
- 머리말·꼬리말·쪽번호는 옮기지 마십시오.
- 설명이나 인사말 없이 옮긴 텍스트만 출력하십시오."""


@dataclass
class OcrNeed:
    """이 PDF 에 OCR 이 필요한가."""

    path: Path
    page_count: int
    empty_pages: list[int]

    @property
    def needed(self) -> bool:
        return bool(self.empty_pages)

    @property
    def fully_scanned(self) -> bool:
        return self.page_count > 0 and len(self.empty_pages) == self.page_count

    @property
    def ratio(self) -> float:
        return len(self.empty_pages) / self.page_count if self.page_count else 0.0

    def __str__(self) -> str:
        if not self.needed:
            return f"{self.path.name}: 텍스트 레이어 있음 ({self.page_count}페이지), OCR 불필요"
        kind = "전체가 스캔" if self.fully_scanned else "일부만 스캔"
        return (
            f"{self.path.name}: {kind} — {self.page_count}페이지 중 "
            f"{len(self.empty_pages)}페이지({self.ratio:.0%})에 텍스트 없음"
        )


@dataclass
class OcrResult:
    backend: str
    text_path: Path
    page_texts: dict[int, str] = field(default_factory=dict)
    pdf_path: Path | None = None
    """ocrmypdf 백엔드에서만 채워진다 — 텍스트 레이어가 박힌 PDF."""

    @property
    def pages(self) -> int:
        return len(self.page_texts)

    @property
    def chars(self) -> int:
        return sum(len(t) for t in self.page_texts.values())

    def __str__(self) -> str:
        out = f"OCR 완료 [{self.backend}] {self.pages}페이지 · {self.chars:,}자 → {self.text_path}"
        if self.pdf_path:
            out += f"\n  텍스트 레이어 PDF: {self.pdf_path}"
        return out


# ---------------------------------------------------------------------------
# 판단 / 백엔드 탐색
# ---------------------------------------------------------------------------


def needs_ocr(path: str | Path) -> OcrNeed:
    """페이지별로 텍스트가 나오는지 확인한다."""
    from pypdf import PdfReader

    path = Path(path)
    reader = PdfReader(str(path))
    empty = [
        no
        for no, page in enumerate(reader.pages, start=1)
        if not (page.extract_text() or "").strip()
    ]
    return OcrNeed(path=path, page_count=len(reader.pages), empty_pages=empty)


def available_backends(*, api_key: str | None = None) -> list[str]:
    """이 환경에서 실제로 쓸 수 있는 백엔드 목록(선호 순)."""
    found: list[str] = []
    if shutil.which("ocrmypdf"):
        found.append("ocrmypdf")
    if shutil.which("tesseract") and shutil.which("pdftoppm"):
        found.append("tesseract")
    if api_key or os.getenv("ANTHROPIC_API_KEY"):
        found.append("claude")
    return found


def resolve_backend(backend: str = "auto", *, api_key: str | None = None) -> str:
    options = available_backends(api_key=api_key)
    if backend != "auto":
        if backend not in BACKENDS:
            raise ValueError(f"알 수 없는 백엔드: {backend!r} ({' | '.join(BACKENDS)})")
        if backend not in options:
            raise RuntimeError(f"{backend} 백엔드를 쓸 수 없습니다. {_install_hint(backend)}")
        return backend
    if not options:
        raise RuntimeError(
            "쓸 수 있는 OCR 백엔드가 없습니다.\n"
            "  - ocrmypdf : apt install ocrmypdf tesseract-ocr-kor  (권장)\n"
            "  - tesseract: apt install tesseract-ocr tesseract-ocr-kor poppler-utils\n"
            "  - claude   : ANTHROPIC_API_KEY 설정 (시스템 도구 없이 동작)"
        )
    return options[0]


def _install_hint(backend: str) -> str:
    return {
        "ocrmypdf": "설치: apt install ocrmypdf tesseract-ocr-kor (macOS: brew install ocrmypdf tesseract-lang)",
        "tesseract": "설치: apt install tesseract-ocr tesseract-ocr-kor poppler-utils",
        "claude": "ANTHROPIC_API_KEY 환경변수를 설정하세요.",
    }[backend]


# ---------------------------------------------------------------------------
# 페이지 범위
# ---------------------------------------------------------------------------


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    """"1-50", "3", "1-10,20,30-32" → 1-based 페이지 번호 목록."""
    if not spec:
        return list(range(1, page_count + 1))

    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                first, last = int(start), int(end)
            except ValueError as exc:
                raise ValueError(f"페이지 범위를 이해할 수 없습니다: {part!r}") from exc
            if first > last:
                raise ValueError(f"페이지 범위가 거꾸로입니다: {part!r}")
            pages.extend(range(first, last + 1))
        else:
            try:
                pages.append(int(part))
            except ValueError as exc:
                raise ValueError(f"페이지 번호를 이해할 수 없습니다: {part!r}") from exc

    pages = sorted({p for p in pages if 1 <= p <= page_count})
    if not pages:
        raise ValueError(f"유효한 페이지가 없습니다 (문서는 {page_count}페이지).")
    return pages


# ---------------------------------------------------------------------------
# 엔트리 포인트
# ---------------------------------------------------------------------------


def run_ocr(
    path: str | Path,
    *,
    backend: str = "auto",
    lang: str = "kor+eng",
    pages: str | None = None,
    dpi: int = 300,
    out_dir: str | Path | None = None,
    api_key: str | None = None,
    model: str = "claude-opus-5",
    batch_pages: int = 5,
    progress=lambda _msg: None,
) -> OcrResult:
    """스캔 페이지를 OCR 해서 페이지 표지가 붙은 텍스트 파일로 저장한다.

    이미 텍스트 레이어가 있는 페이지는 **OCR 하지 않고 그대로 가져다 쓴다.** 실제 약관은
    본문은 텍스트인데 별표·부속서류만 스캔인 경우가 많아서, 전부 다시 OCR 하면 느리고
    멀쩡한 본문 품질까지 떨어진다.

    `pages` 를 주면 그 범위만 결과에 담는다(발췌 검증용).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    chosen = resolve_backend(backend, api_key=api_key)
    out_dir = Path(out_dir) if out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / f"{path.stem}{OCR_SUFFIX}"

    need = needs_ocr(path)
    selected = parse_pages(pages, need.page_count)
    scanned = set(need.empty_pages)
    targets = [no for no in selected if no in scanned]
    if not targets:
        raise ValueError(
            f"{path.name}: 선택한 페이지에는 OCR 이 필요 없습니다(텍스트 레이어가 이미 있습니다)."
        )

    keep = {no: _extract_page(path, no) for no in selected if no not in scanned}
    progress(
        f"[OCR] {chosen} · 대상 {len(targets)}페이지 "
        f"(기존 텍스트 {len(keep)}페이지는 그대로 사용) · lang={lang}"
    )

    pdf_path: Path | None = None
    if chosen == "ocrmypdf":
        page_texts, pdf_path = _run_ocrmypdf(path, out_dir, lang=lang, pages=targets, progress=progress)
    elif chosen == "tesseract":
        page_texts = _run_tesseract(path, lang=lang, pages=targets, dpi=dpi, progress=progress)
    else:
        page_texts = _run_claude(
            path,
            pages=targets,
            api_key=api_key,
            model=model,
            batch_pages=batch_pages,
            progress=progress,
        )

    merged = {**keep, **page_texts}
    merged = {no: text for no, text in merged.items() if text.strip()}
    if not merged:
        raise RuntimeError(
            f"{path.name}: OCR 결과가 비어 있습니다. 해상도(--dpi)를 올리거나 다른 백엔드를 써 보세요."
        )

    write_ocr_text(text_path, merged)
    return OcrResult(backend=chosen, text_path=text_path, page_texts=merged, pdf_path=pdf_path)


# ---------------------------------------------------------------------------
# 백엔드
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"OCR 이 시간 안에 끝나지 않았습니다: {' '.join(cmd[:2])}") from exc


def _slice_pdf(path: Path, pages: list[int], target: Path) -> None:
    """1-based 페이지 목록만 뽑아 새 PDF 로 저장한다."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(path))
    writer = PdfWriter()
    for no in pages:
        writer.add_page(reader.pages[no - 1])
    with target.open("wb") as fh:
        writer.write(fh)


def _run_ocrmypdf(
    path: Path, out_dir: Path, *, lang: str, pages: list[int], progress
) -> tuple[dict[int, str], Path]:
    """텍스트 레이어를 박은 PDF 를 만들고, 거기서 페이지별 텍스트를 뽑는다."""
    from pypdf import PdfReader

    out_pdf = out_dir / f"{path.stem}_ocr.pdf"
    full = len(pages) == _page_count(path)

    with tempfile.TemporaryDirectory() as tmp:
        source = path
        if not full:
            source = Path(tmp) / "slice.pdf"
            _slice_pdf(path, pages, source)

        result = _run(
            [
                "ocrmypdf",
                "-l", lang,
                "--rotate-pages",
                "--deskew",
                "--skip-text",  # 텍스트가 이미 있는 페이지는 건너뛴다
                "--quiet",
                str(source),
                str(out_pdf),
            ]
        )
    if result.returncode != 0:
        raise RuntimeError(f"ocrmypdf 실패 (코드 {result.returncode}):\n{result.stderr.strip()[:800]}")

    reader = PdfReader(str(out_pdf))
    page_texts = {
        pages[i]: (page.extract_text() or "")
        for i, page in enumerate(reader.pages)
        if i < len(pages)
    }
    progress(f"[OCR] ocrmypdf 완료 → {out_pdf.name}")
    return page_texts, out_pdf


def _run_tesseract(path: Path, *, lang: str, pages: list[int], dpi: int, progress) -> dict[int, str]:
    """페이지를 이미지로 굽고 한 장씩 tesseract 에 넘긴다."""
    page_texts: dict[int, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, page_no in enumerate(pages, start=1):
            prefix = tmp_dir / f"p{page_no}"
            render = _run(
                [
                    "pdftoppm", "-r", str(dpi), "-png",
                    "-f", str(page_no), "-l", str(page_no),
                    str(path), str(prefix),
                ]
            )
            if render.returncode != 0:
                raise RuntimeError(f"pdftoppm 실패 (p.{page_no}): {render.stderr.strip()[:400]}")

            images = sorted(tmp_dir.glob(f"p{page_no}*.png"))
            if not images:
                continue
            recognized = _run(["tesseract", str(images[0]), "stdout", "-l", lang, "--psm", "3"])
            if recognized.returncode != 0:
                raise RuntimeError(f"tesseract 실패 (p.{page_no}): {recognized.stderr.strip()[:400]}")
            page_texts[page_no] = recognized.stdout
            if index % 10 == 0 or index == len(pages):
                progress(f"[OCR] tesseract {index}/{len(pages)}페이지")
    return page_texts


def _run_claude(
    path: Path, *, pages: list[int], api_key: str | None, model: str, batch_pages: int, progress
) -> dict[int, str]:
    """Claude 에 PDF 조각을 넘겨 텍스트를 받아 적는다(시스템 도구 없이 동작)."""
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - 설치 안내용
        raise RuntimeError("anthropic 이 필요합니다: pip install anthropic") from exc

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    page_texts: dict[int, str] = {}

    with tempfile.TemporaryDirectory() as tmp:
        for start in range(0, len(pages), batch_pages):
            batch = pages[start : start + batch_pages]
            chunk_pdf = Path(tmp) / f"batch_{batch[0]}.pdf"
            _slice_pdf(path, batch, chunk_pdf)

            payload = base64.standard_b64encode(chunk_pdf.read_bytes()).decode("ascii")
            message = _transcribe(client, model=model, payload=payload, first_page=batch[0])
            if message.stop_reason == "refusal":
                raise RuntimeError(f"모델이 p.{batch[0]}~{batch[-1]} 변환을 거절했습니다.")

            text = "\n".join(b.text for b in message.content if getattr(b, "type", None) == "text")
            page_texts.update(_split_page_marks(text, batch))
            progress(f"[OCR] claude {min(start + batch_pages, len(pages))}/{len(pages)}페이지")

    return page_texts


def _transcribe(client, *, model: str, payload: str, first_page: int):
    content = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": payload}},
        {"type": "text", "text": f"{TRANSCRIBE_PROMPT}\n\n이 묶음의 첫 페이지 번호는 {first_page} 입니다."},
    ]
    with client.messages.stream(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
    ) as stream:
        return stream.get_final_message()


def _split_page_marks(text: str, batch: list[int]) -> dict[int, str]:
    """모델이 붙인 `<<<PAGE N>>>` 표지로 페이지를 가른다. 표지가 없으면 첫 페이지에 몰아 넣는다."""
    result: dict[int, str] = {}
    current = batch[0]
    buffer: list[str] = []
    for line in text.splitlines():
        match = RE_PAGE_MARK.match(line.strip())
        if match:
            if buffer:
                result[current] = "\n".join(buffer).strip()
                buffer = []
            current = int(match.group(1))
            continue
        buffer.append(line)
    if buffer:
        result[current] = "\n".join(buffer).strip()
    return result


# ---------------------------------------------------------------------------
# 저장 / 로딩
# ---------------------------------------------------------------------------


def write_ocr_text(path: str | Path, page_texts: dict[int, str]) -> Path:
    """페이지 표지를 붙여 저장한다. 쪽번호를 잃지 않기 위한 형식."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = [f"{PAGE_MARK.format(no)}\n{page_texts[no].strip()}" for no in sorted(page_texts)]
    path.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return path


def load_ocr_text(path: str | Path, *, title: str | None = None) -> TermsDocument:
    """OCR 결과 텍스트(`.ocr.txt`)를 페이지 번호를 살려 TermsDocument 로 만든다."""
    path = Path(path)
    raw = path.read_text(encoding="utf-8")

    lines: list[Line] = []
    page_no = 1
    pages_seen: set[int] = set()
    for line in raw.splitlines():
        match = RE_PAGE_MARK.match(line.strip())
        if match:
            page_no = int(match.group(1))
            pages_seen.add(page_no)
            continue
        text = _normalize_line(line)
        if text:
            lines.append(Line(text=text, page=page_no))

    if not lines:
        raise ValueError(f"{path.name}: OCR 텍스트가 비어 있습니다.")

    stem = path.name[: -len(OCR_SUFFIX)] if path.name.endswith(OCR_SUFFIX) else path.stem
    return TermsDocument(
        doc_id=_doc_id(stem, raw.encode("utf-8")),
        title=title or stem,
        source=str(path),
        lines=lines,
        page_count=max(pages_seen) if pages_seen else 1,
    )


def _extract_page(path: Path, page_no: int) -> str:
    """텍스트 레이어가 이미 있는 페이지의 텍스트."""
    from pypdf import PdfReader

    return PdfReader(str(path)).pages[page_no - 1].extract_text() or ""


def _page_count(path: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(path)).pages)
