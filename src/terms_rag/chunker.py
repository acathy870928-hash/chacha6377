"""한국어 약관 구조(장/조/항/호/목)를 인식하는 청킹기.

설계 원칙
---------
1. **조(條)가 기본 검색 단위다.** 약관 질의는 대부분 "환불", "해지", "책임" 처럼
   조 하나에 답이 들어 있다. 고정 길이로 자르면 조가 두 동강 나면서 답이 사라진다.
2. **길면 항(項) 경계에서 쪼갠다.** 문장 중간에서 자르지 않는다.
3. **쪼개도 조 제목을 매 청크에 다시 붙인다.** "제12조(환불) …" 라는 맥락이 없으면
   임베딩도 사람도 그 조각이 무엇에 대한 규정인지 알 수 없다.
4. **그래도 긴 항은** 문장 단위로 자르고 약간의 overlap 을 준다.
5. 전문(前文)·부칙은 별도 section 으로 보존한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Chunk, Line, TermsDocument

# ---------------------------------------------------------------------------
# 구조 표지 정규식
# ---------------------------------------------------------------------------

# 제2장 총칙 / 제 2 장  이용계약
RE_CHAPTER = re.compile(r"^제\s*(\d+)\s*장\s*[.·:]?\s*(.*)$")

# 항: ① ~ ⑳ 또는 줄 첫머리의 "(1)"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
RE_PARAGRAPH = re.compile(rf"^([{CIRCLED}])\s*(.*)$")
RE_PARAGRAPH_PAREN = re.compile(r"^\(\s*(\d{1,2})\s*\)\s*(.+)$")

# 호: "1." "2)" — 뒤에 내용이 이어져야 한다(날짜·금액 오탐 방지)
RE_ITEM = re.compile(r"^(\d{1,2})\s*[.)]\s*(\S.*)$")

# 목: "가." "나)"
RE_SUBITEM = re.compile(r"^([가-힣])\s*[.)]\s*(\S.*)$")

# 부칙 / 附則
RE_ADDENDUM = re.compile(r"^(부\s*칙|附\s*則)\s*(?:[(（<]\s*(.*?)\s*[)）>])?\s*$")

# 목차 페이지 감지용
RE_TOC = re.compile(r"^(목\s*차|차\s*례|목록)\s*$")

# 문장 분할: 종결어미/구두점 뒤에서 자른다.
RE_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*|(?<=요\.)\s*|(?<=함\.)\s*|(?<=음\.)\s*")

CIRCLED_TO_INT = {ch: i + 1 for i, ch in enumerate(CIRCLED)}


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------


@dataclass
class ChunkConfig:
    """청킹 파라미터 (모두 '문자 수' 기준. 한국어는 대략 1자 ≈ 0.7~1.2 토큰)."""

    max_chars: int = 1200
    """청크 최대 길이. 이 값을 넘으면 항 → 문장 순으로 분할한다."""

    min_chars: int = 200
    """이 길이 미만인 인접 청크는 앞 청크와 합친다(정의 조항의 짧은 호 등)."""

    overlap_chars: int = 120
    """문장 단위로까지 쪼개야 할 때만 적용되는 겹침 길이."""

    keep_heading_prefix: bool = True
    """분할된 조각마다 조 제목을 다시 붙일지 여부."""

    drop_toc: bool = True
    """앞부분 목차 페이지를 버릴지 여부."""

    merge_short_articles: bool = False
    """짧은 조를 앞 조와 합칠지 여부.

    기본은 False. 약관은 조 하나가 곧 하나의 규정이라, 합치면 인용 출처가
    "제12조의2 / 제13조" 처럼 흐려진다. 청크 수를 줄이는 게 더 중요하면 켠다."""

    drop_stub_chars: int = 30
    """조 번호가 없는 이 길이 미만의 조각(표지·머리글 잔여물)은 버린다. 0이면 끄기."""

    def __post_init__(self) -> None:
        if self.max_chars < 100:
            raise ValueError("max_chars 는 100 이상이어야 합니다.")
        if self.min_chars >= self.max_chars:
            raise ValueError("min_chars 는 max_chars 보다 작아야 합니다.")
        if self.overlap_chars >= self.max_chars:
            raise ValueError("overlap_chars 는 max_chars 보다 작아야 합니다.")


# ---------------------------------------------------------------------------
# 내부 표현
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    """같은 표지(항/호/목/평문) 아래 묶인 텍스트 덩어리."""

    kind: str  # chapter | article | paragraph | item | subitem | addendum | plain
    text: str
    page_start: int
    page_end: int
    number: int | None = None  # 항/호 번호
    meta: dict = field(default_factory=dict)

    def append(self, line: Line) -> None:
        self.text = _join(self.text, line.text)
        self.page_end = max(self.page_end, line.page_end or line.page)


@dataclass
class _Article:
    """조 하나 = 헤더 + 본문 블록들."""

    article_no: str
    article_title: str
    header_text: str
    blocks: list[_Block]
    page_start: int
    page_end: int
    chapter_no: int | None
    chapter_title: str
    section: str  # 본문 | 전문 | 부칙

    @property
    def heading(self) -> str:
        parts = []
        if self.chapter_no is not None:
            parts.append(f"제{self.chapter_no}장 {self.chapter_title}".strip())
        if self.article_no:
            title = _article_header(self.article_no, self.article_title)
            parts.append(title)
        elif self.section != "본문":
            parts.append(self.section)
        return " > ".join(parts)


def _join(base: str, extra: str) -> str:
    """PDF 줄바꿈으로 끊긴 문장을 잇는다.

    한글 문서(HWP/Word)는 대개 어절 단위로 줄을 바꾸므로 공백을 넣어 잇는 편이
    더 정확하다. 영문 하이픈 분철("regu-\nlation")만 예외로 붙여 쓴다.
    """
    if not base:
        return extra
    if not extra:
        return base
    if base.endswith("-") and extra[0].isascii() and extra[0].isalpha():
        return base[:-1] + extra
    if base[-1].isspace() or extra[0].isspace():
        return (base + extra).replace("  ", " ")
    return f"{base} {extra}"


# ---------------------------------------------------------------------------
# 청킹기
# ---------------------------------------------------------------------------


class TermsChunker:
    """TermsDocument → list[Chunk]."""

    def __init__(self, config: ChunkConfig | None = None) -> None:
        self.config = config or ChunkConfig()

    # -- public ------------------------------------------------------------

    def chunk(self, doc: TermsDocument) -> list[Chunk]:
        lines = self._drop_toc(doc.lines) if self.config.drop_toc else doc.lines
        articles = self._parse(lines)

        chunks: list[Chunk] = []
        for article in articles:
            chunks.extend(self._chunk_article(doc, article))

        chunks = self._merge_tiny(chunks)
        for order, chunk in enumerate(chunks):
            chunk.order = order
            chunk.chunk_id = f"{doc.doc_id}#{order:04d}"
            chunk.char_len = len(chunk.text)
        return chunks

    # -- 1단계: 목차 제거 ---------------------------------------------------

    @staticmethod
    def _drop_toc(lines: list[Line]) -> list[Line]:
        """'목차' 표지가 있으면, 그 뒤 첫 번째 '조 + 본문' 이 나오기 전까지 버린다."""
        start = None
        for idx, line in enumerate(lines[:40]):
            if RE_TOC.match(line.text):
                start = idx
                break
        if start is None:
            return lines

        # 목차 이후 실제 본문 시작점: 조 헤더 다음 줄이 조 헤더가 아닌 첫 지점
        for idx in range(start + 1, len(lines) - 1):
            if _match_article(lines[idx].text) and not _match_article(lines[idx + 1].text):
                return lines[idx:]
        return lines[start + 1 :]

    # -- 2단계: 구조 파싱 ---------------------------------------------------

    def _parse(self, lines: list[Line]) -> list[_Article]:
        articles: list[_Article] = []
        chapter_no: int | None = None
        chapter_title = ""
        section = "전문"

        current: _Article | None = None
        block: _Block | None = None

        def flush_block() -> None:
            nonlocal block
            if current is not None and block is not None and block.text.strip():
                current.blocks.append(block)
                current.page_end = max(current.page_end, block.page_end)
            block = None

        def flush_article() -> None:
            nonlocal current
            flush_block()
            if current is not None and (current.blocks or current.header_text):
                articles.append(current)
            current = None

        def open_article(**kwargs) -> None:
            nonlocal current
            flush_article()
            current = _Article(chapter_no=chapter_no, chapter_title=chapter_title, blocks=[], **kwargs)

        for line in lines:
            text = line.text
            page = line.page

            # 장
            m = RE_CHAPTER.match(text)
            if m:
                flush_article()
                chapter_no = int(m.group(1))
                chapter_title = m.group(2).strip()
                continue

            # 부칙
            m = RE_ADDENDUM.match(text)
            if m:
                section = "부칙"
                chapter_no, chapter_title = None, ""
                label = m.group(2) or ""
                open_article(
                    article_no="",
                    article_title=label,
                    header_text=text,
                    page_start=page,
                    page_end=page,
                    section="부칙",
                )
                continue

            # 조
            m = _match_article(text)
            if m:
                no, title, rest = m
                if section == "전문":
                    section = "본문"
                open_article(
                    article_no=no,
                    article_title=title,
                    header_text=_article_header(no, title),
                    page_start=page,
                    page_end=page,
                    section=section,
                )
                if rest:
                    block = _Block(kind="plain", text=rest, page_start=page, page_end=page)
                continue

            if current is None:
                # 전문(제목·머리말) — 가상의 조로 담아둔다
                open_article(
                    article_no="",
                    article_title="",
                    header_text="",
                    page_start=page,
                    page_end=page,
                    section="전문",
                )

            # 항 / 호 / 목 / 평문
            kind, number, body = _classify(text)
            if kind == "plain" and block is not None:
                block.append(line)
                continue

            flush_block()
            block = _Block(kind=kind, text=text if kind == "plain" else body, page_start=page, page_end=page, number=number)
            if kind != "plain":
                block.meta["marker"] = text[: len(text) - len(body)].strip()
                block.text = text  # 표지를 살려 둔다: "① 회사는 …"

        flush_article()
        return [a for a in articles if a.header_text or a.blocks]

    # -- 3단계: 조 → 청크 ---------------------------------------------------

    def _chunk_article(self, doc: TermsDocument, article: _Article) -> list[Chunk]:
        cfg = self.config
        header = article.header_text
        body_units = _group_units(article.blocks)

        full_text = _compose(header, [u.text for u in body_units])
        if not full_text.strip():
            return []

        # 조 전체가 한 청크에 들어가는 경우 (대부분)
        if len(full_text) <= cfg.max_chars:
            return [
                self._make_chunk(
                    doc,
                    article,
                    text=full_text,
                    page_start=article.page_start,
                    page_end=article.page_end,
                    paragraph_nos=_paragraph_numbers(body_units),
                )
            ]

        # 항 단위로 묶어서 분할
        groups: list[list[_Block]] = []
        buffer: list[_Block] = []
        buffer_len = len(header)
        for unit in body_units:
            unit_len = len(unit.text) + 1
            if buffer and buffer_len + unit_len > cfg.max_chars:
                groups.append(buffer)
                buffer, buffer_len = [], len(header)
            buffer.append(unit)
            buffer_len += unit_len
        if buffer:
            groups.append(buffer)

        pieces: list[tuple[str, int, int, list[int]]] = []
        for group in groups:
            text = _compose(header if cfg.keep_heading_prefix else "", [u.text for u in group])
            page_start = min(u.page_start for u in group)
            page_end = max(u.page_end for u in group)
            nos = _paragraph_numbers(group)
            if len(text) <= cfg.max_chars:
                pieces.append((text, page_start, page_end, nos))
                continue
            # 항 하나가 여전히 너무 길다 → 문장 단위 분할
            body = _compose("", [u.text for u in group])
            for part in self._split_sentences(body):
                merged = _compose(header if cfg.keep_heading_prefix else "", [part])
                pieces.append((merged, page_start, page_end, nos))

        return [
            self._make_chunk(
                doc,
                article,
                text=text,
                page_start=ps,
                page_end=pe,
                paragraph_nos=nos,
                part=idx + 1,
                part_count=len(pieces),
            )
            for idx, (text, ps, pe, nos) in enumerate(pieces)
        ]

    def _split_sentences(self, text: str) -> list[str]:
        """문장 경계로 자르고 overlap 을 준다. 마지막 안전망."""
        cfg = self.config
        sentences = [s for s in RE_SENT_SPLIT.split(text) if s and s.strip()]
        if not sentences:
            sentences = [text]

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

    def _make_chunk(
        self,
        doc: TermsDocument,
        article: _Article,
        *,
        text: str,
        page_start: int,
        page_end: int,
        paragraph_nos: list[int],
        part: int = 1,
        part_count: int = 1,
    ) -> Chunk:
        return Chunk(
            chunk_id="",  # chunk() 에서 부여
            doc_id=doc.doc_id,
            doc_title=doc.title,
            source=doc.source,
            text=text.strip(),
            heading=article.heading,
            chapter_no=article.chapter_no,
            chapter_title=article.chapter_title,
            article_no=article.article_no,
            article_title=article.article_title,
            paragraph_nos=paragraph_nos,
            section=article.section,
            page_start=page_start,
            page_end=page_end,
            part=part,
            part_count=part_count,
        )

    # -- 4단계: 너무 짧은 청크 병합 ----------------------------------------

    def _merge_tiny(self, chunks: list[Chunk]) -> list[Chunk]:
        """조각난 청크를 정리한다.

        - 같은 조가 쪼개졌는데 마지막 조각이 너무 짧으면 앞 조각에 붙인다.
        - 조 번호가 없는 잔여 조각(문서 제목 줄 등)은 같은 성격의 앞 조각에 붙이거나 버린다.
        - 다른 조끼리 합치는 것은 기본적으로 하지 않는다(``merge_short_articles``).
        """
        cfg = self.config
        merged: list[Chunk] = []
        for chunk in chunks:
            prev = merged[-1] if merged else None
            if prev is not None and len(chunk.text) < cfg.min_chars and self._mergeable(prev, chunk):
                prev.text = f"{prev.text}\n{chunk.text}"
                prev.page_end = max(prev.page_end, chunk.page_end)
                prev.paragraph_nos = prev.paragraph_nos + chunk.paragraph_nos
                if chunk.heading and chunk.heading != prev.heading:
                    prev.heading = f"{prev.heading} / {chunk.heading}" if prev.heading else chunk.heading
                continue
            merged.append(chunk)

        if cfg.drop_stub_chars:
            merged = [
                c for c in merged if c.article_no or len(c.text) >= cfg.drop_stub_chars
            ]
        return merged

    def _mergeable(self, prev: Chunk, chunk: Chunk) -> bool:
        cfg = self.config
        if prev.doc_id != chunk.doc_id or prev.section != chunk.section:
            return False
        if len(prev.text) + len(chunk.text) + 1 > cfg.max_chars:
            return False
        same_article = bool(chunk.article_no) and prev.article_no == chunk.article_no
        both_stub = not prev.article_no and not chunk.article_no
        if same_article or both_stub:
            return True
        return cfg.merge_short_articles and len(prev.text) < cfg.min_chars

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _match_article(text: str) -> tuple[str, str, str] | None:
    """'제5조(목적) 본문…' → ("5", "목적", "본문…"). 조 헤더가 아니면 None."""
    m = re.match(
        r"^제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*"
        r"(?:[(（\[【<]\s*([^)）\]】>]{0,40}?)\s*[)）\]】>])?"
        r"\s*(.*)$",
        text,
    )
    if not m:
        return None
    no = m.group(1) if not m.group(2) else f"{m.group(1)}-{m.group(2)}"
    title = (m.group(3) or "").strip()
    rest = (m.group(4) or "").strip()
    # 괄호 제목이 없으면 뒤따르는 짧은 텍스트를 제목으로 본다 ("제5조 목적")
    if not title and rest and len(rest) <= 25 and not re.search(r"[.。]$", rest):
        title, rest = rest, ""
    return no, title, rest


def _article_header(no: str, title: str) -> str:
    if "-" in no:
        main, sub = no.split("-", 1)
        label = f"제{main}조의{sub}"
    else:
        label = f"제{no}조"
    return f"{label}({title})" if title else label


def _classify(text: str) -> tuple[str, int | None, str]:
    m = RE_PARAGRAPH.match(text)
    if m:
        return "paragraph", CIRCLED_TO_INT.get(m.group(1)), m.group(2).strip()
    m = RE_PARAGRAPH_PAREN.match(text)
    if m:
        return "paragraph", int(m.group(1)), m.group(2).strip()
    m = RE_ITEM.match(text)
    if m:
        return "item", int(m.group(1)), m.group(2).strip()
    m = RE_SUBITEM.match(text)
    if m:
        return "subitem", None, m.group(2).strip()
    return "plain", None, text


def _group_units(blocks: list[_Block]) -> list[_Block]:
    """호/목은 자신이 속한 항에 붙여 하나의 분할 단위로 만든다."""
    units: list[_Block] = []
    for block in blocks:
        if block.kind in {"item", "subitem"} and units:
            host = units[-1]
            host.text = f"{host.text}\n{block.text}"
            host.page_end = max(host.page_end, block.page_end)
            continue
        units.append(
            _Block(
                kind=block.kind,
                text=block.text,
                page_start=block.page_start,
                page_end=block.page_end,
                number=block.number,
                meta=dict(block.meta),
            )
        )
    return units


def _paragraph_numbers(units: list[_Block]) -> list[int]:
    return [u.number for u in units if u.kind == "paragraph" and u.number is not None]


def _compose(header: str, bodies: list[str]) -> str:
    parts = [p for p in ([header] + bodies) if p and p.strip()]
    return "\n".join(parts).strip()
