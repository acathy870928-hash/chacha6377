"""고객 ↔ 약관 연결 장부.

답변한 약관을 「누구 고객 건」으로 남기면 쌓인다.
쌓이면 다음 상담에서 그 고객의 약관이 바로 후보가 되고, FA가 계속 쓸 이유가 된다.
"""

from datetime import date

import pytest

from orca.clarify import NextAction, plan_turn
from orca.links import CustomerTermsLink, LinkSource, TermsLedger
from orca.routing import Classification, route
from orca.types import QuestionType


def _link(customer_id="c1", name="차○희", advisor="fa-1", product="내맘같은어린이보험", year=2019, **kw):
    return CustomerTermsLink(
        customer_id=customer_id,
        customer_name=name,
        advisor_id=advisor,
        insurer=kw.pop("insurer", "○○화재"),
        product_name=product,
        edition_label=kw.pop("edition_label", "2019.04 시행"),
        contract_year=year,
        linked_on=kw.pop("linked_on", date(2026, 8, 13)),
        **kw,
    )


@pytest.fixture
def ledger():
    return TermsLedger()


class TestLinking:
    def test_연결을_남긴다(self, ledger):
        assert ledger.link(_link()) is True
        assert len(ledger.terms_for("c1")) == 1

    def test_같은_고객_같은_약관은_중복되지_않는다(self, ledger):
        ledger.link(_link())
        assert ledger.link(_link()) is False
        assert len(ledger.terms_for("c1")) == 1

    def test_같은_고객_다른_약관은_쌓인다(self, ledger):
        ledger.link(_link())
        ledger.link(_link(product="든든운전자보험", year=2022))
        assert len(ledger.terms_for("c1")) == 2

    def test_가입_연도가_다르면_다른_약관이다(self, ledger):
        # 판이 다르면 답이 달라지므로 별도 연결로 본다.
        ledger.link(_link(year=2019))
        assert ledger.link(_link(year=2023)) is True

    def test_연결_경로를_구분한다(self, ledger):
        ledger.link(_link(source=LinkSource.PURCHASED))
        assert ledger.terms_for("c1")[0].source is LinkSource.PURCHASED


class TestReuse:
    def test_같은_약관을_쓰는_고객을_센다(self, ledger):
        # 확보 비용을 들인 약관이 몇 명에게 쓰이는지가 곧 그 등록의 값어치다.
        ledger.link(_link(customer_id="c1", name="차○희"))
        ledger.link(_link(customer_id="c2", name="김○수"))
        key = ledger.links[0].terms_key
        assert ledger.customer_count(key) == 2

    def test_같은_고객이_여러_번_물어도_한_명으로_센다(self, ledger):
        ledger.link(_link(customer_id="c1"))
        ledger.link(_link(customer_id="c1"))
        assert ledger.customer_count(ledger.links[0].terms_key) == 1

    def test_고객별_연결_수를_센다(self, ledger):
        ledger.link(_link(customer_id="c1"))
        ledger.link(_link(customer_id="c1", product="든든운전자보험", year=2022))
        ledger.link(_link(customer_id="c2"))
        assert ledger.customers_with_terms("fa-1") == {"c1": 2, "c2": 1}

    def test_다른_FA의_연결은_섞이지_않는다(self, ledger):
        ledger.link(_link(customer_id="c1", advisor="fa-1"))
        ledger.link(_link(customer_id="c3", advisor="fa-2"))
        assert set(ledger.customers_with_terms("fa-1")) == {"c1"}

    def test_연결_여부를_확인한다(self, ledger):
        ledger.link(_link())
        key = ledger.links[0].terms_key
        assert ledger.is_linked("c1", key)
        assert not ledger.is_linked("c2", key)


class TestTermsBook:
    """약관북 — 첫 화면(질문창)과 별도 메뉴. 고객 = 폴더."""

    def test_고객별_폴더로_묶인다(self, ledger):
        ledger.link(_link(customer_id="c1", name="차○희"))
        ledger.link(_link(customer_id="c1", name="차○희", product="든든운전자보험", year=2022))
        ledger.link(_link(customer_id="c2", name="김○수"))

        folders = ledger.folders("fa-1")
        assert len(folders) == 2
        assert {f.customer_name for f in folders} == {"차○희", "김○수"}

    def test_폴더에_약관_수가_보인다(self, ledger):
        ledger.link(_link(customer_id="c1"))
        ledger.link(_link(customer_id="c1", product="든든운전자보험", year=2022))
        assert ledger.folders("fa-1")[0].count == 2

    def test_최근에_추가된_폴더가_위로_온다(self, ledger):
        ledger.link(_link(customer_id="c1", name="차○희", linked_on=date(2026, 8, 1)))
        ledger.link(_link(customer_id="c2", name="김○수", linked_on=date(2026, 8, 12)))
        assert [f.customer_name for f in ledger.folders("fa-1")] == ["김○수", "차○희"]

    def test_폴더_안도_최근순이다(self, ledger):
        ledger.link(_link(product="옛날건", year=2015, linked_on=date(2026, 7, 1)))
        ledger.link(_link(product="최근건", year=2024, linked_on=date(2026, 8, 12)))
        folder = ledger.folders("fa-1")[0]
        assert [t.product_name for t in folder.terms] == ["최근건", "옛날건"]

    def test_폴더에_보험사가_요약된다(self, ledger):
        ledger.link(_link(insurer="○○화재"))
        ledger.link(_link(insurer="KB손보", product="운전자보험", year=2024))
        assert set(ledger.folders("fa-1")[0].insurers) == {"○○화재", "KB손보"}

    def test_담당_밖_폴더는_열리지_않는다(self, ledger):
        ledger.link(_link(customer_id="c9", advisor="fa-2"))
        assert ledger.folders("fa-1") == []
        assert ledger.folder("fa-1", "c9") is None

    def test_폴더를_연다(self, ledger):
        ledger.link(_link(customer_id="c1", name="차○희"))
        folder = ledger.folder("fa-1", "c1")
        assert folder.customer_name == "차○희"
        assert folder.terms[0].product_name == "내맘같은어린이보험"


class TestFolderSearch:
    def test_고객명으로_찾는다(self, ledger):
        ledger.link(_link(customer_id="c1", name="차○희"))
        ledger.link(_link(customer_id="c2", name="김○수"))
        assert [f.customer_name for f in ledger.search_folders("fa-1", "차")] == ["차○희"]

    def test_상품명으로도_찾는다(self, ledger):
        # 「그 어린이보험 어디 있더라」로 찾는 경우.
        ledger.link(_link(customer_id="c1", name="차○희"))
        ledger.link(_link(customer_id="c2", name="김○수", product="든든운전자보험", year=2022))
        found = ledger.search_folders("fa-1", "어린이")
        assert [f.customer_name for f in found] == ["차○희"]

    def test_빈_검색어는_전체_폴더(self, ledger):
        ledger.link(_link(customer_id="c1"))
        ledger.link(_link(customer_id="c2", name="김○수"))
        assert len(ledger.search_folders("fa-1", "")) == 2


class TestLabel:
    def test_판이_있으면_함께_보여준다(self):
        assert _link().label == "내맘같은어린이보험 · 2019.04 시행"

    def test_판이_없으면_상품명만(self):
        assert _link(edition_label=None).label == "내맘같은어린이보험"


class TestOfferLink:
    def test_보상_답변이_특정되면_고객_지정을_제안한다(self, catalog):
        decision = route(
            Classification(
                question_type=QuestionType.COVERAGE,
                product_mentioned="무배당 운전자보험",
                period_mentioned="2021년 6월",
            )
        )
        plan = plan_turn(decision, catalog)
        assert plan.action is NextAction.SEARCH
        assert plan.offer_customer_link

    def test_되묻는_중에는_제안하지_않는다(self, catalog):
        decision = route(
            Classification(
                question_type=QuestionType.COVERAGE,
                product_mentioned="무배당 운전자보험",
            )
        )
        plan = plan_turn(decision, catalog)
        assert plan.action is NextAction.ASK_CONTRACT_DATE
        assert not plan.offer_customer_link

    def test_담보_용어_설명에는_제안하지_않는다(self, catalog):
        # 특정 계약과 무관한 일반 설명이므로 고객에 묶을 근거가 없다.
        decision = route(Classification(question_type=QuestionType.BENEFIT_TERM))
        plan = plan_turn(decision, catalog)
        assert not plan.offer_customer_link

    def test_개념_질문에도_제안하지_않는다(self, catalog):
        decision = route(Classification(question_type=QuestionType.CONCEPT))
        plan = plan_turn(decision, catalog)
        assert not plan.offer_customer_link
