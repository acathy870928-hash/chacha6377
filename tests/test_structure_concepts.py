"""상위 구조(특약)와 개념 정규화·관계 생성 테스트.

사슬 전체를 검증한다:
    보험사 → 상품 → 적용기간 → 특약 → 조항 → 보장대상 → 지급조건 → 면책조건 → 감액조건 → 정의 → 원문 근거
"""

import pytest

from terms_rag.concepts import (
    build_graph,
    concept_schema,
    extract_definitions,
    link_mentions,
    route_query,
    index_entries,
    _abbreviates,
)
from terms_rag.doc_chunker import chunk_document
from terms_rag.metadata import DocumentMeta
from terms_rag.pdf_loader import load_text
from terms_rag.structure import (
    classify_article,
    detect_clauses,
    section_schema,
)

TERMS = """무배당 하이라이프퍼펙트종합보험 보통약관

제1조(목적)
이 약관은 회사와 계약자 사이의 보험계약에 관한 사항을 정함을 목적으로 합니다.

제5조(보험금의 지급사유)
회사는 피보험자가 보험기간 중 사망한 경우 사망보험금을 지급합니다.

고액치료비암진단담보특별약관

제1조(보험금의 지급사유)
회사는 피보험자가 보험기간 중 고액치료비암으로 진단확정된 경우 고액치료비암진단보험금을 지급합니다.

제5조(고액치료비암의 정의 및 진단확정)
① 이 특별약관에서 "고액치료비암"이라 함은 한국표준질병사인분류에 있어서 뇌 및 중추신경계통의 암,
골 및 관절연골의 암 등 치료비용이 고액인 것으로 분류되는 악성신생물을 말합니다.
② "진단확정"은 병리 또는 진단검사의학의 전문의 자격증을 가진 자에 의하여 내려져야 합니다.

제6조(보험금을 지급하지 않는 사유)
회사는 피보험자가 보장개시일 이전에 고액치료비암으로 진단확정된 경우 보험금을 지급하지 않습니다.

제7조(보험금 지급에 관한 세부규정)
계약일부터 1년 미만에 고액치료비암으로 진단확정된 경우에는 약정한 보험금의 50%를 지급합니다.

상해입원일당특별약관

제1조(보험금의 지급사유)
회사는 피보험자가 상해로 인하여 입원한 경우 입원일당을 지급합니다.

제5조(상해의 정의)
이 특별약관에서 "상해"라 함은 급격하고도 우연한 외래의 사고로 신체에 입은 손상을 말합니다.
"""

META = DocumentMeta(
    insurer="현대해상",
    product_name_standard="하이라이프퍼펙트종합보험",
    product_code="HI0908",
    effective_from="2009-08-01",
    effective_to="2009-10-01",
)


@pytest.fixture
def doc():
    document = load_text(TERMS, title="하이라이프퍼펙트종합보험 약관")
    document.meta = META.to_dict()
    return document


@pytest.fixture
def chunks(doc):
    return chunk_document(doc)


def by_clause(chunks, clause, article_no):
    return next(c for c in chunks if c.special_clause == clause and c.article_no == article_no)


class TestClauseDetection:
    def test_finds_general_and_special_clauses(self, doc):
        spans = detect_clauses(doc)
        assert [s.kind for s in spans] == ["보통약관", "특별약관", "특별약관"]
        assert spans[1].name == "고액치료비암진단담보특별약관"

    def test_table_of_contents_is_not_mistaken_for_a_clause(self):
        toc = load_text(
            "목 차\n고액치료비암진단담보특별약관\n상해입원일당특별약관\n\n"
            "고액치료비암진단담보특별약관\n제1조(목적)\n내용입니다.\n"
        )
        spans = detect_clauses(toc)
        assert len(spans) == 1  # 조문이 따라오는 진짜 제목만

    def test_document_without_riders(self):
        assert detect_clauses(load_text("제1조(목적)\n내용입니다.\n제2조(정의)\n내용입니다.")) == []


class TestClauseAttachment:
    def test_same_article_number_in_different_riders_is_disambiguated(self, chunks):
        fives = [c for c in chunks if c.article_no == "5"]
        assert len(fives) == 3  # 보통약관 + 특약 2개
        assert {c.special_clause for c in fives} == {
            "",
            "고액치료비암진단담보특별약관",
            "상해입원일당특별약관",
        }

    def test_general_clause_chunks_are_marked(self, chunks):
        target = next(c for c in chunks if c.article_no == "1" and not c.special_clause)
        assert target.clause_kind == "보통약관"

    def test_citation_includes_the_rider(self, chunks):
        target = by_clause(chunks, "고액치료비암진단담보특별약관", "5")
        assert "고액치료비암진단담보특별약관 제5조" in target.citation
        assert target.citation.startswith("현대해상 하이라이프퍼펙트종합보험(HI0908)")

    def test_embed_text_carries_the_rider(self, chunks):
        target = by_clause(chunks, "고액치료비암진단담보특별약관", "5")
        assert "고액치료비암진단담보특별약관" in target.embed_text


class TestArticleRole:
    @pytest.mark.parametrize(
        "title, text, expected",
        [
            ("고액치료비암의 정의 및 진단확정", "", "정의"),
            ("보험금의 지급사유", "", "지급사유"),
            ("보험금을 지급하지 않는 사유", "", "면책"),
            ("보험금 지급에 관한 세부규정", "약정한 보험금의 50%를 지급합니다.", "감액"),
            ("보험기간", "", "보험기간"),
            ("청약의 철회", "", "계약"),
            ("잡다한 규정", "특별히 정한 바가 없습니다.", "기타"),
        ],
    )
    def test_classification(self, title, text, expected):
        assert classify_article(title, text) == expected

    def test_body_evidence_beats_a_vague_title(self, chunks):
        # "보험금 지급에 관한 세부규정" 은 제목만 보면 지급사유처럼 보인다
        assert by_clause(chunks, "고액치료비암진단담보특별약관", "7").article_role == "감액"

    def test_roles_across_the_document(self, chunks):
        roles = {(c.special_clause, c.article_no): c.article_role for c in chunks}
        assert roles[("고액치료비암진단담보특별약관", "5")] == "정의"
        assert roles[("고액치료비암진단담보특별약관", "6")] == "면책"


class TestSectionSchema:
    def test_matches_the_requested_shape(self, chunks):
        payload = section_schema(by_clause(chunks, "고액치료비암진단담보특별약관", "5"))["section"]
        assert payload["special_clause"] == "고액치료비암진단담보특별약관"
        assert payload["article_no"] == 5
        assert payload["article_title"] == "고액치료비암의 정의 및 진단확정"
        assert payload["page"] == 1


class TestConceptExtraction:
    def test_only_definition_articles_produce_concepts(self, chunks):
        concepts = extract_definitions(chunks)
        assert {c.raw_term for c in concepts} == {"고액치료비암", "진단확정", "상해"}
        assert all(c.defined_in.article_title.endswith(("정의", "진단확정")) for c in concepts)

    def test_taxonomy_comes_from_the_definition_body(self, chunks):
        cancer = next(c for c in extract_definitions(chunks) if c.raw_term == "고액치료비암")
        assert (cancer.category, cancer.sub_category) == ("질병", "암")
        assert cancer.concept_type == "보장대상 정의"

    def test_matches_the_requested_concept_shape(self, chunks):
        concepts = {c.raw_term: c.to_dict() for c in extract_definitions(chunks)}
        assert concepts["고액치료비암"] == {
            "raw_term": "고액치료비암",
            "standard_term": "고액치료비암",
            "category": "질병",
            "sub_category": "암",
            "concept_type": "보장대상 정의",
        }
        assert concepts["진단확정"] == {
            "raw_term": "진단확정",
            "standard_term": "진단확정",
            "concept_type": "지급조건",
        }

    def test_every_concept_carries_its_evidence(self, chunks):
        for concept in extract_definitions(chunks):
            assert concept.defined_in and concept.defined_in.chunk_id
            assert concept.defined_in.page >= 1

    def test_undefined_terms_never_become_concepts(self, chunks):
        """본문에만 나오는 말은 개념이 아니다 — 임의로 표준화하지 않는다."""
        terms = {c.raw_term for c in extract_definitions(chunks)}
        assert "고액치료비암진단보험금" not in terms
        assert "입원일당" not in terms

    def test_no_definitions_means_no_concepts(self):
        plain = load_text("제1조(목적)\n이 약관은 목적을 정합니다.\n제2조(적용)\n적용합니다.")
        assert extract_definitions(chunk_document(plain)) == []


class TestRelations:
    def test_concept_links_to_payout_exclusion_and_reduction(self, chunks):
        concepts = extract_definitions(chunks)
        relations = link_mentions(concepts, chunks)
        cancer = [r for r in relations if r.term == "고액치료비암"]
        assert {r.relation for r in cancer} == {"정의", "지급조건", "면책조건", "감액조건"}
        exclusion = next(r for r in cancer if r.relation == "면책조건")
        assert exclusion.evidence.article_no == "6"

    def test_relations_stay_inside_their_rider(self, chunks):
        concepts = extract_definitions(chunks)
        relations = link_mentions(concepts, chunks)
        for relation in relations:
            if relation.term == "상해":
                assert relation.evidence.special_clause == "상해입원일당특별약관"

    def test_graph_contains_the_whole_chain(self, chunks):
        graph = build_graph(chunks)
        assert graph["document"]["insurer"] == "현대해상"
        assert graph["document"]["effective_from"] == "2009-08-01"
        assert {c["name"] for c in graph["clauses"]} >= {"고액치료비암진단담보특별약관"}

        cancer = next(c for c in graph["concepts"] if c["raw_term"] == "고액치료비암")
        assert cancer["defined_in"]["article_no"] == 5
        assert {r["relation"] for r in cancer["relations"]} == {"정의", "지급조건", "면책조건", "감액조건"}

    def test_concept_schema_per_chunk(self, chunks):
        concepts = extract_definitions(chunks)
        payload = concept_schema(by_clause(chunks, "고액치료비암진단담보특별약관", "5"), concepts)
        terms = {c["raw_term"] for c in payload["insurance_concepts"]}
        assert terms == {"고액치료비암", "진단확정"}


class TestQueryRouting:
    @pytest.mark.parametrize(
        "token, term, expected",
        [
            ("고액암", "고액치료비암", True),
            ("고액치료비암", "고액치료비암", False),  # 같은 길이는 줄임말이 아니다
            ("치료암", "고액치료비암", False),  # 첫 글자가 다르다
            ("암", "고액치료비암", False),  # 한 글자는 위험하다
            ("상해입원", "상해입원일당", True),
        ],
    )
    def test_abbreviation_matching(self, token, term, expected):
        assert _abbreviates(token, term) is expected

    def test_routes_an_abbreviation_to_the_defined_term(self, chunks):
        entries = index_entries(extract_definitions(chunks))
        routed = route_query("고액암 조건이 어떻게 되나요?", entries)
        assert [r["raw_term"] for r in routed] == ["고액치료비암"]
        assert routed[0]["special_clause"] == "고액치료비암진단담보특별약관"

    def test_exact_term_also_routes(self, chunks):
        entries = index_entries(extract_definitions(chunks))
        assert route_query("진단확정 기준", entries)[0]["raw_term"] == "진단확정"

    def test_unrelated_query_routes_nowhere(self, chunks):
        entries = index_entries(extract_definitions(chunks))
        assert route_query("보험료 납입 방법", entries) == []
