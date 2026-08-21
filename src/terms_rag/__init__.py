"""약관(이용약관/개인정보처리방침 등) PDF 를 RAG 용으로 처리하는 파이프라인.

흐름: PDF 로드 → 구조 기반 청킹 → 임베딩 → 로컬 벡터스토어 → 하이브리드 검색 → 답변 생성
"""

from .models import Chunk, Line, TermsDocument
from .chunker import TermsChunker, ChunkConfig
from .pdf_loader import load_pdf, load_text
from .store import VectorStore, SearchHit

__all__ = [
    "Chunk",
    "Line",
    "TermsDocument",
    "TermsChunker",
    "ChunkConfig",
    "load_pdf",
    "load_text",
    "VectorStore",
    "SearchHit",
]

__version__ = "0.1.0"
