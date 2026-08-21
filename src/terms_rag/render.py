"""청크를 LLM 컨텍스트에 그대로 붙일 수 있는 형태로 렌더링한다.

검색해서 몇 조각만 넣든, 약관 전체를 통째로 넣든, LLM 이 읽는 쪽에서 필요한 건 같다.

1. **경계가 분명할 것** — 어디부터 어디까지가 약관 원문인지 모델이 헷갈리면 안 된다.
2. **조각마다 출처가 붙어 있을 것** — 그래야 모델이 "제12조 제2항에 따르면" 이라고 인용한다.
3. **번호가 있을 것** — `[1]`, `[2]` 로 짧게 인용할 수 있어야 답변이 검증 가능해진다.

토큰 수는 Claude 의 count_tokens 엔드포인트로 정확히 세고(키가 있을 때),
없으면 글자 수 기반으로 어림잡는다. tiktoken 류는 Claude 토크나이저가 아니므로 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .models import Chunk

FORMATS = ("xml", "markdown", "text", "jsonl")

# 한국어는 대략 1자 ≈ 1토큰(공백·조사 포함 시 조금 낮음). 보수적으로 잡는다.
CHARS_PER_TOKEN = 1.0


def render(
    chunks: Sequence[Chunk],
    *,
    fmt: str = "xml",
    title: str | None = None,
    instructions: bool = True,
) -> str:
    """청크 묶음을 LLM 프롬프트에 붙일 문자열로 만든다."""
    if fmt not in FORMATS:
        raise ValueError(f"알 수 없는 형식: {fmt!r} ({' | '.join(FORMATS)})")
    if not chunks:
        return ""
    if fmt == "xml":
        return _render_xml(chunks, title=title, instructions=instructions)
    if fmt == "markdown":
        return _render_markdown(chunks, title=title, instructions=instructions)
    if fmt == "text":
        return _render_text(chunks, title=title)
    return _render_jsonl(chunks)


def _doc_title(chunks: Sequence[Chunk], title: str | None) -> str:
    if title:
        return title
    titles = {c.doc_title for c in chunks}
    return titles.pop() if len(titles) == 1 else "약관 모음"


XML_GUIDE = """아래 <{root}> 안의 내용만 근거로 답하십시오. 없는 내용은 추측하지 말고
"제공된 자료에서 확인할 수 없습니다" 라고 답하십시오.
각 주장 뒤에는 근거를 [1], [2] 처럼 번호로 표시하십시오."""


def _root_tag(chunks: Sequence[Chunk]) -> tuple[str, str]:
    """(바깥 태그, 항목 태그). 약관이면 조항, 그 외 문서면 절 단위로 이름을 맞춘다."""
    return ("약관", "조항") if all(c.doc_kind == "약관" for c in chunks) else ("자료", "내용")


def _render_xml(chunks: Sequence[Chunk], *, title: str | None, instructions: bool) -> str:
    """Claude 가 가장 잘 읽는 형태. 태그로 원문 경계를 못 박는다."""
    root, item = _root_tag(chunks)
    parts: list[str] = []
    if instructions:
        parts.append(XML_GUIDE.format(root=root))
        parts.append("")
    parts.append(f'<{root} 제목="{_esc(_doc_title(chunks, title))}" 개수="{len(chunks)}">')
    for i, chunk in enumerate(chunks, start=1):
        attrs = [f'번호="{i}"', f'출처="{_esc(chunk.citation)}"']
        if chunk.article_no:
            attrs.append(f'조="{_esc(_article_label(chunk))}"')
        elif chunk.heading:
            attrs.append(f'절="{_esc(chunk.heading)}"')
        if chunk.section != "본문":
            attrs.append(f'구분="{_esc(chunk.section)}"')
        parts.append(f"  <{item} {' '.join(attrs)}>")
        parts.append(_indent(chunk.text, "    "))
        parts.append(f"  </{item}>")
    parts.append(f"</{root}>")
    return "\n".join(parts)


def _render_markdown(chunks: Sequence[Chunk], *, title: str | None, instructions: bool) -> str:
    parts: list[str] = []
    if instructions:
        root, _item = _root_tag(chunks)
        parts.append(XML_GUIDE.format(root=root).replace(f"아래 <{root}> 안의", "아래"))
        parts.append("")
    parts.append(f"# {_doc_title(chunks, title)}")
    parts.append("")
    for i, chunk in enumerate(chunks, start=1):
        parts.append(f"## [{i}] {chunk.heading or chunk.section}")
        parts.append(f"*출처: {chunk.citation}*")
        parts.append("")
        parts.append(chunk.text)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _render_text(chunks: Sequence[Chunk], *, title: str | None) -> str:
    parts = [_doc_title(chunks, title), "=" * 60, ""]
    for i, chunk in enumerate(chunks, start=1):
        parts.append(f"[{i}] {chunk.citation}")
        parts.append(chunk.text)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _render_jsonl(chunks: Sequence[Chunk]) -> str:
    import json

    return "\n".join(json.dumps(c.to_dict(), ensure_ascii=False) for c in chunks) + "\n"


def _article_label(chunk: Chunk) -> str:
    no = chunk.article_no
    label = f"제{no.split('-')[0]}조의{no.split('-')[1]}" if "-" in no else f"제{no}조"
    return f"{label}({chunk.article_title})" if chunk.article_title else label


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line if line else line for line in text.splitlines())


# ---------------------------------------------------------------------------
# 토큰 수 세기
# ---------------------------------------------------------------------------


@dataclass
class TokenCount:
    tokens: int
    exact: bool
    model: str | None = None

    def __str__(self) -> str:
        how = f"{self.model} 기준 실측" if self.exact else "글자 수 기반 추정"
        return f"{self.tokens:,} 토큰 ({how})"


def estimate_tokens(text: str) -> TokenCount:
    return TokenCount(tokens=int(len(text) / CHARS_PER_TOKEN), exact=False)


def count_tokens(text: str, *, model: str = "claude-opus-5", api_key: str | None = None) -> TokenCount:
    """Claude 의 count_tokens 로 정확히 센다. 실패하면 추정값으로 내려간다.

    토큰 수는 모델마다 다르므로 실제로 쓸 모델 ID 를 그대로 넘긴다.
    """
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        response = client.messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return TokenCount(tokens=response.input_tokens, exact=True, model=model)
    except Exception:
        # 키가 없거나 SDK 미설치, 네트워크 불가 — 붙여넣기용 대략치면 충분하다
        return estimate_tokens(text)


def split_by_tokens(chunks: Sequence[Chunk], *, max_tokens: int, fmt: str = "xml", **kwargs) -> list[list[Chunk]]:
    """렌더링 결과가 `max_tokens` 를 넘지 않도록 청크를 여러 묶음으로 나눈다.

    컨텍스트 한도보다 약관이 클 때 나눠 붙이기 위한 것. 조 경계는 유지된다.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens 는 1 이상이어야 합니다.")

    batches: list[list[Chunk]] = []
    current: list[Chunk] = []
    for chunk in chunks:
        candidate = current + [chunk]
        if current and estimate_tokens(render(candidate, fmt=fmt, **kwargs)).tokens > max_tokens:
            batches.append(current)
            current = [chunk]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def filter_chunks(
    chunks: Iterable[Chunk],
    *,
    articles: Sequence[str] | None = None,
    chapter: int | None = None,
    section: str | None = None,
) -> list[Chunk]:
    """조 번호 / 장 / 구분으로 골라낸다. `articles` 는 "12", "12-2" 형식."""
    wanted = {a.strip() for a in articles} if articles else None
    result = []
    for chunk in chunks:
        if wanted is not None and chunk.article_no not in wanted:
            continue
        if chapter is not None and chunk.chapter_no != chapter:
            continue
        if section is not None and chunk.section != section:
            continue
        result.append(chunk)
    return result
