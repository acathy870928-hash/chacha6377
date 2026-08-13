"""벤더 질의에 개인정보가 실리지 않는지 검증.

보장분석은 본인인증으로 조회한 개인정보이고 약관 검색은 외부 벤더에서 이뤄진다.
벤더에 나가는 값은 약관을 특정하는 정보뿐이어야 한다.
"""

from conftest import DRIVER  # noqa: F401  (fixture 모듈 로딩용)

from orca.coverage import BenefitMatch, EnrolledBenefit, EnrolledContract
from orca.vendor_query import TermsQuery, build_queries, strip_pii
from orca.versioning import ApproxDate

CONTRACT = EnrolledContract(
    insurer="KB손보",
    product_name="KB다이렉트플러스운전자보험(무배당)(24.10)",
    contract_start=ApproxDate(2024, 11),
    premium=14800,
    policyholder="홍길동",
    insured="홍길동",
    contract_id="C-000123",
    benefits=(EnrolledBenefit("골절진단비(치아파절포함)(연간1회한)", 10),),
)

MATCH = BenefitMatch(contract=CONTRACT, benefit=CONTRACT.benefits[0])


class TestPayloadContents:
    def test_약관을_특정하는_정보만_보낸다(self):
        payload = build_queries((MATCH,))[0].as_payload()
        assert set(payload) <= {"insurer", "product", "edition", "benefit", "situation"}

    def test_상품과_판이_실린다(self):
        payload = build_queries((MATCH,))[0].as_payload()
        assert payload["insurer"] == "KB손보"
        assert payload["edition"] == "2024.11"
        assert payload["benefit"] == "골절진단비(치아파절포함)(연간1회한)"

    def test_계약자_피보험자_계약번호는_보내지_않는다(self):
        payload = build_queries((MATCH,))[0].as_payload()
        serialized = str(payload)
        assert "홍길동" not in serialized
        assert "C-000123" not in serialized

    def test_가입금액과_보험료도_보내지_않는다(self):
        # 약관은 지급사유만 답하면 된다. 금액은 우리 쪽에서 결합한다.
        payload = build_queries((MATCH,))[0].as_payload()
        serialized = str(payload)
        assert "14800" not in serialized
        assert "10" not in payload.get("benefit", "").replace("연간1회한", "")


class TestSituationSanitizing:
    def test_실명_호칭을_지운다(self):
        assert "차승희" not in strip_pii("차승희 고객님이 계단에서 넘어져 골절")

    def test_주민번호를_지운다(self):
        assert "870928" not in strip_pii("870928-2______ 피보험자 골절 사고")

    def test_전화번호를_지운다(self):
        assert "010" not in strip_pii("010-5833-8141로 연락 온 건, 골절 사고")

    def test_사고_내용은_남긴다(self):
        cleaned = strip_pii("차승희 고객님이 계단에서 넘어져 발목 골절")
        assert "계단에서 넘어져 발목 골절" in cleaned

    def test_질의에도_적용된다(self):
        query = build_queries((MATCH,), situation="차승희 고객님이 골절")[0]
        assert "차승희" not in query.as_payload()["situation"]


class TestQueryBuilding:
    def test_계약마다_질의가_나간다(self):
        other = EnrolledContract(
            insurer="DB손보",
            product_name="브라보라이프보험0808",
            contract_start=ApproxDate(2009, 3),
            benefits=(EnrolledBenefit("골절진단비(치아제외)", 30),),
        )
        matches = (MATCH, BenefitMatch(contract=other, benefit=other.benefits[0]))
        queries = build_queries(matches)
        assert len(queries) == 2
        assert {q.edition_label for q in queries} == {"2024.11", "2009.03"}

    def test_같은_계약_같은_담보는_한_번만(self):
        assert len(build_queries((MATCH, MATCH))) == 1

    def test_계약년월이_없으면_판을_비운다(self):
        contract = EnrolledContract(
            insurer="○○화재",
            product_name="옛날보험",
            benefits=(EnrolledBenefit("골절진단비"),),
        )
        query = build_queries((BenefitMatch(contract=contract, benefit=contract.benefits[0]),))[0]
        assert query.edition_label is None
        assert "edition" not in query.as_payload()


class TestQueryShape:
    def test_필드가_늘어나면_이_테스트가_깨진다(self):
        # 개인정보 필드가 무심코 추가되는 것을 막는 잠금장치다.
        assert set(TermsQuery.__dataclass_fields__) == {
            "insurer",
            "product_name",
            "edition_label",
            "benefit_name",
            "situation",
        }
