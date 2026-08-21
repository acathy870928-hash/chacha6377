"""약관(이용약관/개인정보처리방침 등) PDF 를 RAG 용으로 처리하는 파이프라인.

흐름: PDF 로드 → 구조 기반 청킹 → 임베딩 → 로컬 벡터스토어 → 하이브리드 검색 → 답변 생성
"""

from .models import Chunk, Line, TermsDocument
from .chunker import TermsChunker, ChunkConfig
from .doc_chunker import DocumentChunker, chunk_document, detect_kind
from .loaders import load_document
from .metadata import DocumentMeta, detect_insurers, read_meta
from .structure import classify_article, detect_clauses, section_schema
from .concepts import build_graph, extract_definitions, route_query
from .ocr import OcrResult, needs_ocr, run_ocr
from .pdf_loader import load_pdf, load_text
from .html_loader import load_html
from .docx_loader import load_docx
from .store import VectorStore, SearchHit

__all__ = [
    "Chunk",
    "Line",
    "TermsDocument",
    "TermsChunker",
    "DocumentChunker",
    "chunk_document",
    "ChunkConfig",
    "load_document",
    "DocumentMeta",
    "read_meta",
    "detect_insurers",
    "detect_clauses",
    "classify_article",
    "section_schema",
    "extract_definitions",
    "build_graph",
    "route_query",
    "run_ocr",
    "needs_ocr",
    "OcrResult",
    "load_pdf",
    "load_html",
    "load_docx",
    "load_text",
    "detect_kind",
    "VectorStore",
    "SearchHit",
]

__version__ = "0.1.0"
