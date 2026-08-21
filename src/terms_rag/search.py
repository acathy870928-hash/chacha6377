"""검색 + 근거 기반 답변 생성.

검색은 벡터 + BM25 하이브리드(`VectorStore.search`)를 쓰고,
답변은 Claude 에게 **검색된 조항만** 근거로 쓰도록 강제한다.
약관은 틀린 답이 곧 분쟁이 되므로, 근거가 없으면 없다고 말하게 한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .embedder import Embedder, get_embedder
from .metadata import detect_insurers
from .store import SearchHit, VectorStore

SYSTEM_PROMPT = """당신은 약관 해석을 돕는 어시스턴트입니다.

규칙:
1. 아래 <약관_발췌> 안의 내용만 근거로 답하십시오. 발췌에 없는 내용은 추측하지 마십시오.
2. 답변의 각 주장 뒤에 근거 조항을 [1], [2] 형식으로 표시하십시오. 번호는 발췌의 번호입니다.
3. 발췌만으로 답할 수 없으면 "제공된 약관 발췌로는 확인할 수 없습니다" 라고 명확히 말하고,
   어떤 조항을 더 확인해야 하는지 알려주십시오.
4. 법률 자문이 아니라 약관 내용 안내임을 잊지 마십시오. 해석이 갈릴 수 있는 부분은 그렇다고 밝히십시오.
5. 한국어로, 결론을 먼저 쓰고 근거를 뒤에 붙이십시오."""


@dataclass
class Answer:
    text: str
    hits: list[SearchHit]
    model: str
    refused: bool = False

    def sources(self) -> list[str]:
        return [f"[{i}] {hit.chunk.citation}" for i, hit in enumerate(self.hits, start=1)]


def search(
    query: str,
    *,
    store: VectorStore,
    embedder: Embedder | None = None,
    settings: Settings | None = None,
    top_k: int = 5,
    doc_id: str | None = None,
    section: str | None = None,
    insurer: str | None = None,
    product_code: str | None = None,
    as_of: str | None = None,
    auto_insurer: bool = True,
    boost: float = 0.5,
    lexical_only: bool = False,
    alpha: float = 0.5,
    fusion: str = "score",
) -> list[SearchHit]:
    """질의에 해당하는 조항을 찾는다.

    `auto_insurer` 가 켜져 있으면 질문에서 보험사명을 찾아 그 회사 자료를 위로 올린다.
    "흥국화재 암보험…" 이라고 물었는데 삼성생명 자료가 먼저 나오는 문제를 막기 위한 것이다.
    보험사가 둘 이상 언급되면(비교 질문) 아무것도 밀어 올리지 않는다.
    """
    if not len(store):
        raise ValueError("벡터스토어가 비어 있습니다. 먼저 `ingest` 를 실행하세요.")

    query_vector = None
    if not lexical_only:
        settings = settings or Settings.from_env()
        embedder = embedder or get_embedder(settings)
        stored_model = store.manifest.get("model")
        if stored_model and stored_model != embedder.model:
            raise ValueError(
                f"인덱스는 '{stored_model}' 로 만들어졌는데 현재 설정은 '{embedder.model}' 입니다. "
                "같은 모델로 맞추거나 인덱스를 다시 만드세요."
            )
        query_vector = embedder.embed_query(query)

    boost_insurer = None
    if auto_insurer and not insurer:
        mentioned = detect_insurers(query)
        if len(mentioned) == 1:
            boost_insurer = mentioned[0]

    return store.search(
        query_vector,
        query_text=query,
        top_k=top_k,
        doc_id=doc_id,
        section=section,
        insurer=insurer,
        product_code=product_code,
        as_of=as_of,
        boost_insurer=boost_insurer,
        boost=boost,
        alpha=alpha,
        fusion=fusion,
    )


def build_context(hits: list[SearchHit]) -> str:
    blocks = []
    for i, hit in enumerate(hits, start=1):
        blocks.append(f"[{i}] 출처: {hit.chunk.citation}\n{hit.chunk.text}")
    return "\n\n".join(blocks)


def answer(
    query: str,
    hits: list[SearchHit],
    *,
    settings: Settings | None = None,
    max_tokens: int = 4000,
) -> Answer:
    """검색 결과를 근거로 Claude 가 답변을 작성한다."""
    settings = settings or Settings.from_env()
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - 설치 안내용
        raise RuntimeError("anthropic 이 필요합니다: pip install anthropic") from exc

    if not hits:
        return Answer(text="관련 조항을 찾지 못했습니다.", hits=[], model=settings.answer_model)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
    user_content = f"<약관_발췌>\n{build_context(hits)}\n</약관_발췌>\n\n질문: {query}"

    message = _create_message(
        client,
        model=settings.answer_model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        user_content=user_content,
    )

    # Claude Opus 5 는 안전 분류기가 요청을 거절하면 HTTP 200 + stop_reason="refusal" 로 응답한다.
    # content 를 읽기 전에 반드시 확인한다.
    if message.stop_reason == "refusal":
        return Answer(text="모델이 이 요청에 대한 응답을 거절했습니다.", hits=hits, model=settings.answer_model, refused=True)

    text = "\n".join(block.text for block in message.content if getattr(block, "type", None) == "text")
    return Answer(text=text.strip(), hits=hits, model=settings.answer_model)


def _create_message(client, *, model: str, max_tokens: int, system: str, user_content: str):
    """스트리밍으로 요청한다(긴 응답에서 HTTP 타임아웃 방지).

    거절 시 서버가 대체 모델로 자동 재시도하도록 server-side fallback 베타를 켠다.
    베타를 쓸 수 없는 환경(다른 플랫폼 등)에서는 일반 요청으로 내려간다.
    """
    import anthropic

    messages = [{"role": "user", "content": user_content}]
    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            return stream.get_final_message()
    except (anthropic.BadRequestError, TypeError, AttributeError):
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
        ) as stream:
            return stream.get_final_message()
