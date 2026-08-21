"""조문 구조가 없는 문서(보고서·가이드·회의록 등)를 위한 제목 기반 청킹기.

약관 청킹기(`chunker.TermsChunker`)는 건드리지 않는다. 약관은 조(條)가 검색 단위라는
전제 위에서 규칙이 굳어져 있고, 거기에 문서용 예외를 섞으면 약관 청킹 품질이
조용히 흔들린다. 그래서 **완전히 별도 경로**로 둔다.

문서 청킹 규칙
1. 검색 단위는 제목(H1~H6) 기준 **절**이다.
2. 절이 `max_chars` 를 넘으면 문단 경계에서 쪼개고, 조각마다 제목을 다시 붙인다.
3. 문단 하나가 그래도 길면 문장 경계로 자르고 overlap 을 준다.
4. 본문 없이 제목만 있는 절은 뒤따르는 하위 절 앞머리에 접어 넣는다.
5. 그리디 분할에서 생기는 자투리는 이웃 묶음에 흡수시킨다.
6. 제목 경로 맨 앞이 문서 제목과 같으면 지운다(출처 중복 표기 방지).

표는 로더가 `셀 | 셀 | 셀` 행으로 펼쳐 두므로 여기서는 일반 문단과 같게 다룬다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .chunker import RE_SENT_SPLIT, ChunkConfig, _join, _match_article
from .metadata import DocumentMeta, apply_to_chunks
from .models import Chunk, Line, TermsDocument


def detect_kind(doc: TermsDocument, *, min_articles: int = 2) -> str:
    """조문 구조가 있으면 "약관", 없으면 "문서".

    `제N조` 헤더가 `min_articles` 개 이상이면 약관으로 본다. 형식(PDF/HTML/DOCX)이
    아니라 내용의 구조로 판단하므로, 홈페이지에 HTML 로 올라간 약관도 약관 경로를 탄다.
    문서 쪽에서 `kind` 를 명시했으면 그 값을 그대로 따른다.
    """
    if doc.kind in {"약관", "문서"}:
        return doc.kind
    articles = sum(1 for line in doc.lines if _match_article(line.text))
    return "약관" if articles >= min_articles else "문서"


@dataclass
class _Section:
    """제목 하나와 그 아래 본문 줄들."""

    path: list[str]
    header: str
    lines: list[Line] = field(default_factory=list)
    page_start: int = 1
    page_end: int = 1

    @property
    def heading(self) -> str:
        return " > ".join(self.path)

    @property
    def title(self) -> str:
        return self.path[-1] if self.path else ""

    @property
    def top(self) -> str:
        return self.path[0] if self.path else ""


class DocumentChunker:
    """TermsDocument(문서) → list[Chunk]."""

    def __init__(self, config: ChunkConfig | None = None) -> None:
        self.config = config or ChunkConfig()

    # -- public ------------------------------------------------------------

    def chunk(self, doc: TermsDocument) -> list[Chunk]:
        sections = self._split_sections(doc.lines)

        chunks: list[Chunk] = []
        for section in sections:
            chunks.extend(self._chunk_section(doc, section))

        _strip_title_prefix(chunks, doc.title)
        chunks = self._fold_heading_only(chunks)
        chunks = self._merge_tiny(chunks)

        for order, chunk in enumerate(chunks):
            chunk.order = order
            chunk.chunk_id = f"{doc.doc_id}#{order:04d}"
            chunk.char_len = len(chunk.text)
        return chunks

    # -- 1단계: 제목으로 절 나누기 -----------------------------------------

    def _split_sections(self, lines: list[Line]) -> list[_Section]:
        sections: list[_Section] = []
        stack: list[tuple[int, str]] = []
        current: _Section | None = None

        for line in lines:
            if line.heading_level:
                if current is not None:
                    sections.append(current)
                while stack and stack[-1][0] >= line.heading_level:
                    stack.pop()
                stack.append((line.heading_level, line.text))
                current = _Section(
                    path=[text for _level, text in stack],
                    header=line.text,
                    page_start=line.page,
                    page_end=line.page_end or line.page,
                )
                continue

            if current is None:
                # 첫 제목 앞에 오는 표지·머리말
                current = _Section(path=[], header="", page_start=line.page, page_end=line.page)
            current.lines.append(line)
            current.page_end = max(current.page_end, line.page_end or line.page)

        if current is not None:
            sections.append(current)
        return [s for s in sections if s.header or s.lines]

    # -- 2단계: 절 → 청크 ---------------------------------------------------

    def _chunk_section(self, doc: TermsDocument, section: _Section) -> list[Chunk]:
        cfg = self.config
        bodies = [line.text for line in section.lines]
        full_text = _compose(section.header, bodies)
        if not full_text.strip():
            return []

        if len(full_text) <= cfg.max_chars:
            return [self._make_chunk(doc, section, text=full_text)]

        groups = _pack(bodies, limit=cfg.max_chars, header_len=len(section.header))
        groups = _absorb_runt(groups, header_len=len(section.header), cfg=cfg)

        pieces: list[str] = []
        for group in groups:
            text = _compose(section.header if cfg.keep_heading_prefix else "", group)
            if len(text) <= cfg.max_chars:
                pieces.append(text)
                continue
            for part in _split_sentences(_compose("", group), cfg):
                pieces.append(_compose(section.header if cfg.keep_heading_prefix else "", [part]))

        return [
            self._make_chunk(doc, section, text=text, part=i + 1, part_count=len(pieces))
            for i, text in enumerate(pieces)
        ]

    def _make_chunk(
        self,
        doc: TermsDocument,
        section: _Section,
        *,
        text: str,
        part: int = 1,
        part_count: int = 1,
    ) -> Chunk:
        return Chunk(
            chunk_id="",  # chunk() 에서 부여
            doc_id=doc.doc_id,
            doc_title=doc.title,
            source=doc.source,
            text=text.strip(),
            heading=section.heading,
            chapter_no=None,
            chapter_title=section.top,
            article_no="",
            article_title=section.title,
            section="본문",
            doc_kind="문서",
            page_start=section.page_start,
            page_end=section.page_end,
            part=part,
            part_count=part_count,
        )

    # -- 3단계: 정리 --------------------------------------------------------

    def _fold_heading_only(self, chunks: list[Chunk]) -> list[Chunk]:
        """본문 없이 제목만 있는 절을 바로 뒤의 하위 절 앞머리에 붙인다.

        "4. 원인 분석" 처럼 내용이 전부 하위 절에 있는 상위 제목이, 8자짜리
        쓸모없는 청크로 남는 것을 막는다.
        """
        folded: list[Chunk] = []
        pending: Chunk | None = None
        for chunk in chunks:
            if pending is not None:
                fits = len(pending.text) + len(chunk.text) + 1 <= self.config.max_chars
                if chunk.heading.startswith(pending.heading) and fits:
                    chunk.text = f"{pending.text}\n{chunk.text}"
                    chunk.page_start = min(pending.page_start, chunk.page_start)
                else:
                    folded.append(pending)
                pending = None
            if _is_heading_only(chunk):
                pending = chunk
                continue
            folded.append(chunk)
        if pending is not None:
            folded.append(pending)
        return folded

    def _merge_tiny(self, chunks: list[Chunk]) -> list[Chunk]:
        """짧은 절을 앞 청크에 합친다. 보고서는 짧은 하위 절이 많아 그대로 두면 먼지가 된다."""
        cfg = self.config
        merged: list[Chunk] = []
        for chunk in chunks:
            prev = merged[-1] if merged else None
            if prev is not None and len(chunk.text) < cfg.min_chars and self._mergeable(prev, chunk):
                prev.text = f"{prev.text}\n{chunk.text}"
                prev.page_end = max(prev.page_end, chunk.page_end)
                prev.heading = _combine_headings(prev.heading, chunk.heading)
                continue
            merged.append(chunk)

        if cfg.drop_stub_chars:
            merged = [c for c in merged if c.heading or len(c.text) >= cfg.drop_stub_chars]
        return merged

    def _mergeable(self, prev: Chunk, chunk: Chunk) -> bool:
        cfg = self.config
        if prev.doc_id != chunk.doc_id:
            return False
        if len(prev.text) + len(chunk.text) + 1 > cfg.max_chars:
            return False
        same_section = bool(chunk.heading) and prev.heading == chunk.heading
        both_stub = not prev.heading and not chunk.heading
        # 같은 상위 제목 아래라면 짧은 하위 절끼리 이어 붙인다
        same_parent = bool(chunk.chapter_title) and prev.chapter_title == chunk.chapter_title
        return same_section or both_stub or same_parent


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _compose(header: str, bodies: list[str]) -> str:
    parts = [p for p in ([header] + bodies) if p and p.strip()]
    return "\n".join(parts).strip()


def _pack(bodies: list[str], *, limit: int, header_len: int) -> list[list[str]]:
    """문단들을 상한에 맞춰 그리디로 묶는다."""
    groups: list[list[str]] = []
    buffer: list[str] = []
    length = header_len
    for body in bodies:
        size = len(body) + 1
        if buffer and length + size > limit:
            groups.append(buffer)
            buffer, length = [], header_len
        buffer.append(body)
        length += size
    if buffer:
        groups.append(buffer)
    return groups


def _absorb_runt(groups: list[list[str]], *, header_len: int, cfg: ChunkConfig) -> list[list[str]]:
    """min_chars 미만의 자투리 묶음을 이웃에 흡수시킨다(상한 15% 초과 허용).

    자투리 청크는 그 자체로 검색되지도, 문맥이 되지도 못한다. 앞 묶음을 우선한다.
    """
    if len(groups) < 2:
        return groups

    limit = cfg.max_chars * 1.15

    def size(group: list[str]) -> int:
        return header_len + sum(len(body) + 1 for body in group)

    result = list(groups)
    index = 0
    while index < len(result):
        if len(result) < 2 or size(result[index]) - header_len >= cfg.min_chars:
            index += 1
            continue
        prev_ok = index > 0 and size(result[index - 1] + result[index]) <= limit
        next_ok = index + 1 < len(result) and size(result[index] + result[index + 1]) <= limit
        if prev_ok:
            result[index - 1] = result[index - 1] + result[index]
            del result[index]
        elif next_ok:
            result[index + 1] = result[index] + result[index + 1]
            del result[index]
        else:
            index += 1
    return result


def _split_sentences(text: str, cfg: ChunkConfig) -> list[str]:
    """문단 하나가 상한을 넘을 때의 마지막 안전망. 문장 경계로 자르고 overlap 을 준다."""
    sentences = [s for s in RE_SENT_SPLIT.split(text) if s and s.strip()] or [text]

    parts: list[str] = []
    buffer = ""
    for sentence in sentences:
        if len(sentence) > cfg.max_chars:  # 마침표 없는 초장문 방어
            if buffer:
                parts.append(buffer)
                buffer = ""
            for i in range(0, len(sentence), cfg.max_chars):
                parts.append(sentence[i : i + cfg.max_chars])
            continue
        candidate = _join(buffer, sentence) if buffer else sentence
        if len(candidate) > cfg.max_chars:
            parts.append(buffer)
            tail = buffer[-cfg.overlap_chars :] if cfg.overlap_chars else ""
            buffer = _join(tail, sentence) if tail else sentence
        else:
            buffer = candidate
    if buffer:
        parts.append(buffer)
    return parts


def _strip_title_prefix(chunks: list[Chunk], doc_title: str) -> None:
    """제목 경로 맨 앞이 문서 제목과 같으면 지운다.

    HTML/DOCX 는 본문 첫 H1 이 문서 제목과 같은 경우가 흔해서, 그대로 두면
    출처가 "피드백 문서 피드백 문서 > 4. ..." 처럼 두 번 찍힌다.
    """
    if not doc_title:
        return
    prefix = f"{doc_title} > "
    for chunk in chunks:
        if chunk.heading == doc_title:
            chunk.heading = ""
        elif chunk.heading.startswith(prefix):
            chunk.heading = chunk.heading[len(prefix) :]


def _is_heading_only(chunk: Chunk) -> bool:
    """본문 없이 제목 줄만 들어 있는 청크인가."""
    if not chunk.heading:
        return False
    return chunk.text.strip() == (chunk.article_title or "").strip()


def _combine_headings(left: str, right: str) -> str:
    """두 청크를 합칠 때 표시할 제목. 한쪽이 다른 쪽의 상위 경로면 상위만 남긴다."""
    if not left:
        return right
    if not right or left == right:
        return left
    if right.startswith(left):
        return left
    if left.startswith(right):
        return right
    return f"{left} / {right}"


def chunk_document(doc: TermsDocument, config: ChunkConfig | None = None) -> list[Chunk]:
    """문서 종류를 판별해 알맞은 청킹기로 넘기고, 문서 신원을 찍는다.

    약관이면 `chunker.TermsChunker`(원본 그대로), 아니면 `DocumentChunker`.
    """
    if detect_kind(doc) == "약관":
        from .chunker import TermsChunker

        chunks = TermsChunker(config).chunk(doc)
    else:
        chunks = DocumentChunker(config).chunk(doc)

    if doc.meta:
        apply_to_chunks(chunks, DocumentMeta.from_dict(doc.meta))
    return chunks
