"""파이프라인 전역에서 쓰는 데이터 구조."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Line:
    """원본 문서에서 뽑아낸 한 줄. 페이지 번호를 함께 들고 다녀서 인용 근거로 쓴다."""

    text: str
    page: int  # 1-based
    page_end: int | None = None  # 여러 줄이 합쳐진 경우 마지막 줄의 페이지
    heading_level: int | None = None
    """제목 줄이면 그 깊이(1=H1). HTML/DOCX 로더가 채운다. PDF 는 None."""

    def __post_init__(self) -> None:
        if self.page_end is None:
            self.page_end = self.page


@dataclass
class TermsDocument:
    """청킹 입력이 되는 약관 문서 하나."""

    doc_id: str
    title: str
    source: str  # 원본 파일 경로 (또는 "<text>")
    lines: list[Line]
    page_count: int = 0
    kind: str = "auto"
    """"약관"(조문 구조) / "문서"(제목 구조) / "auto"(청킹기가 판별). 청킹 전략이 갈린다."""

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class Chunk:
    """검색 단위. 기본은 '조' 단위이고, 길면 '항' 단위로 쪼갠다."""

    chunk_id: str
    doc_id: str
    doc_title: str
    source: str
    text: str

    # 구조 메타데이터
    heading: str = ""  # 사람이 읽는 경로: "제2장 이용계약 > 제5조(청약철회)"
    chapter_no: int | None = None
    chapter_title: str = ""
    article_no: str = ""  # "5" 또는 "10-2" (제10조의2)
    article_title: str = ""
    paragraph_nos: list[int] = field(default_factory=list)  # 포함된 항 번호 ①②③
    section: str = "본문"  # 본문 | 전문 | 부칙
    doc_kind: str = "약관"  # 약관 | 문서

    # 위치 메타데이터
    page_start: int = 0
    page_end: int = 0
    order: int = 0  # 문서 내 청크 순번
    part: int = 1  # 같은 조가 여러 청크로 나뉜 경우 1,2,3...
    part_count: int = 1
    char_len: int = 0

    def __post_init__(self) -> None:
        if not self.char_len:
            self.char_len = len(self.text)

    @property
    def embed_text(self) -> str:
        """임베딩할 문자열. 제목 경로를 앞에 붙여 맥락을 보존한다."""
        prefix_parts = [p for p in (self.doc_title, self.heading) if p]
        prefix = " | ".join(prefix_parts)
        return f"{prefix}\n{self.text}" if prefix else self.text

    @property
    def citation(self) -> str:
        """답변에 붙일 짧은 출처 표기."""
        loc = f"p.{self.page_start}" if self.page_start == self.page_end else f"p.{self.page_start}-{self.page_end}"
        head = self.heading or self.section
        tail = f" ({self.part}/{self.part_count})" if self.part_count > 1 else ""
        return f"{self.doc_title} {head}{tail}, {loc}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chunk":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})
