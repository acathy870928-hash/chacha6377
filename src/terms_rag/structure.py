"""약관의 상위 구조 — 보통약관 / 특별약관(특약) / 별표.

왜 필요한가
-----------
실제 보험 약관은 **보통약관 하나 + 특별약관 수십 개**로 되어 있고, 특약마다 조 번호가
제1조부터 다시 시작한다. 그래서 `제5조` 만으로는 주소가 되지 않는다.

    고액치료비암진단담보특별약관 > 제5조(고액치료비암의 정의 및 진단확정)
    ^^^^^^^^^^^^^^^^^^^^^^^^^^  이게 빠지면 같은 문서 안 다른 제5조와 구분이 안 된다

청킹기(`chunker.py`)는 조 단위 구조만 본다. 특약 경계는 **청킹이 끝난 뒤** 이 모듈이
원문 줄 순서를 따라가며 각 청크에 도장을 찍는다. 청킹 규칙과 상위 구조는 서로 바뀔
이유가 다르므로 분리해 둔다.

조항의 성격(정의 / 지급사유 / 면책 / 감액 …)도 여기서 분류한다. "고액치료비암의 정의"가
정의 조항인지 지급 조항인지는 관계를 만들 때 반드시 필요하다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Chunk, TermsDocument

# 특별약관 제목: "고액치료비암진단담보특별약관", "【암진단특약】", "<상해입원 특별약관>"
RE_SPECIAL = re.compile(
    r"^[\[\(【<〔]?\s*"
    r"(?P<name>(?:무배당\s*)?[^\s\[\(【<〔][^\[\]\(\)【】<>〔〕]{1,60}?"
    r"(?:특별약관|특약))"
    r"\s*[\]\)】>〕]?\s*$"
)
# 보통약관 시작
RE_GENERAL = re.compile(r"^[\[\(【<〔]?\s*([^\[\]\(\)【】<>〔〕]{0,50}?보통약관)\s*[\]\)】>〕]?\s*$")
# 별표·부표
RE_APPENDIX = re.compile(r"^[\[\(【<〔]?\s*((?:별\s*표|부\s*표|별첨)\s*\d*\s*[^\[\]\(\)]{0,40})\s*[\]\)】>〕]?\s*$")

# 조항 성격 — 제목이 우선, 없으면 본문 단서
ARTICLE_ROLES: list[tuple[str, re.Pattern]] = [
    ("정의", re.compile(r"정의|용어의?\s*뜻|이라\s*함은")),
    ("지급사유", re.compile(r"지급\s*사유|보험금의?\s*종류|급부")),
    ("면책", re.compile(r"지급하지\s*(?:아니|않)|면책|보상하지\s*(?:아니|않)")),
    ("감액", re.compile(r"감액|삭감|비례\s*보상|일부\s*지급")),
    ("보험기간", re.compile(r"보험기간|보장개시|책임개시|대기\s*기간|면책\s*기간")),
    ("계약", re.compile(r"청약|철회|해지|무효|취소|부활|고지의무|계약자")),
    ("절차", re.compile(r"청구|절차|서류|지급시기|이의|분쟁")),
]

# 제목보다 우선하는 본문 증거 — 숫자로 확인되는 감액, 명시적 부지급
STRONG_BODY_CUES: list[tuple[str, re.Pattern]] = [
    ("감액", re.compile(r"\d{1,3}\s*%\s*(?:에\s*해당하는\s*금액|를|을)?\s*(?:만\s*)?지급|감액하여\s*지급")),
]

BODY_ROLE_CUES: list[tuple[str, re.Pattern]] = [
    ("면책", re.compile(r"지급하지\s*(?:아니|않)|보상하지\s*(?:아니|않)")),
    ("감액", re.compile(r"(\d{1,3})\s*%\s*(?:에 해당하는 금액|를)?\s*(?:만\s*)?지급|감액하여")),
    ("지급사유", re.compile(r"보험금을\s*지급합니다|지급하여\s*드립니다")),
    ("정의", re.compile(r"(?:이란|이라\s*함은|(?<=\")란)\s*.{0,60}?말합니다")),
]

CLAUSE_KINDS = ("보통약관", "특별약관", "별표")


@dataclass
class ClauseSpan:
    """문서 안에서 한 약관(보통/특별/별표)이 차지하는 줄 범위."""

    name: str
    kind: str
    start: int  # doc.lines 인덱스 (제목 줄)
    end: int  # 다음 약관 직전까지 (exclusive)
    page: int = 1

    def __str__(self) -> str:
        return f"[{self.kind}] {self.name} (p.{self.page}, 줄 {self.start}~{self.end})"


def detect_clauses(doc: TermsDocument) -> list[ClauseSpan]:
    """문서를 보통약관/특별약관/별표 구간으로 자른다.

    제목만 나열된 목차 줄에 속지 않도록, **뒤에 조문이 실제로 따라오는 제목**만 인정한다.
    """
    marks: list[tuple[int, str, str]] = []
    for index, line in enumerate(doc.lines):
        text = line.text.strip()
        if len(text) > 80:
            continue
        for pattern, kind in ((RE_GENERAL, "보통약관"), (RE_SPECIAL, "특별약관"), (RE_APPENDIX, "별표")):
            match = pattern.match(text)
            if match:
                marks.append((index, match.group(1).strip(), kind))
                break

    marks = [m for m in marks if _has_articles_after(doc, m[0])]
    if not marks:
        return []

    spans: list[ClauseSpan] = []
    for position, (index, name, kind) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(doc.lines)
        spans.append(ClauseSpan(name=name, kind=kind, start=index, end=end, page=doc.lines[index].page))
    return spans


def _has_articles_after(doc: TermsDocument, index: int, *, window: int = 30, minimum: int = 1) -> bool:
    """제목 뒤 몇 줄 안에 조문이 나오는가. 목차 줄을 걸러낸다."""
    from .chunker import _match_article

    found = 0
    for line in doc.lines[index + 1 : index + 1 + window]:
        if _match_article(line.text):
            found += 1
            if found >= minimum:
                return True
        # 다음 약관 제목이 바로 나오면 목차다
        if RE_SPECIAL.match(line.text.strip()) or RE_GENERAL.match(line.text.strip()):
            return False
    return False


def attach_clauses(doc: TermsDocument, chunks: list[Chunk]) -> list[ClauseSpan]:
    """각 청크에 소속 약관(특약)을 찍는다.

    청크는 문서 순서대로 나오므로, 원문 줄을 앞에서부터 단조롭게 훑으며 맞춘다.
    청크 본문의 첫 줄(조 제목 줄)을 원문에서 찾아 위치를 정한다.
    """
    spans = detect_clauses(doc)
    if not spans:
        return []

    texts = [line.text.strip() for line in doc.lines]
    cursor = 0
    for chunk in chunks:
        head = chunk.text.splitlines()[0].strip() if chunk.text else ""
        position = _find_from(texts, head, cursor)
        if position is not None:
            cursor = position
        span = _span_at(spans, cursor)
        if span:
            chunk.special_clause = span.name if span.kind != "보통약관" else ""
            chunk.clause_kind = span.kind
    return spans


def _find_from(texts: list[str], needle: str, start: int) -> int | None:
    if not needle:
        return None
    for index in range(start, len(texts)):
        if texts[index] == needle or texts[index].startswith(needle):
            return index
    return None


def _span_at(spans: list[ClauseSpan], index: int) -> ClauseSpan | None:
    for span in spans:
        if span.start <= index < span.end:
            return span
    return None


def classify_article(title: str, text: str = "") -> str:
    """조항의 성격.

    감액·면책은 본문에 증거가 있으면 제목보다 우선한다. "보험금 지급에 관한 세부규정"
    처럼 제목이 뭉뚱그려져 있어도 본문이 "50%를 지급합니다" 면 그건 감액 조항이다.
    """
    for role, pattern in STRONG_BODY_CUES:
        if text and pattern.search(text):
            return role
    for role, pattern in ARTICLE_ROLES:
        if title and pattern.search(title):
            return role
    for role, pattern in BODY_ROLE_CUES:
        if text and pattern.search(text):
            return role
    return "기타"


def attach_roles(chunks: list[Chunk]) -> None:
    for chunk in chunks:
        chunk.article_role = classify_article(chunk.article_title, chunk.text)


def section_schema(chunk: Chunk) -> dict:
    """청크 하나의 위치를 나타내는 스키마.

    {"section": {"special_clause": ..., "article_no": 5, "article_title": ..., "page": 100}}
    """
    article_no: int | str | None = None
    if chunk.article_no:
        article_no = int(chunk.article_no) if chunk.article_no.isdigit() else chunk.article_no
    return {
        "section": {
            "special_clause": chunk.special_clause or None,
            "clause_kind": chunk.clause_kind or None,
            "article_no": article_no,
            "article_title": chunk.article_title or None,
            "article_role": chunk.article_role or None,
            "page": chunk.page_start,
        }
    }


def apply(doc: TermsDocument, chunks: list[Chunk]) -> list[ClauseSpan]:
    """상위 구조 인식 일괄 적용 — 약관 구간 + 조항 성격."""
    spans = attach_clauses(doc, chunks)
    attach_roles(chunks)
    return spans
