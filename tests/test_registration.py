"""고객 등록과 약관 등록 경로.

보험사 → 검색 → 등록만 있으면 계약 6건에 열다섯 단계가 된다.
빠른 경로를 먼저 내놓아야 FA가 보장맵을 채운다.
"""

from datetime import date

import pytest

from orca.customers import CustomerDirectory
from orca.links import CustomerTermsLink, TermsLedger
from orca.registration import (
    ImportPreview,
    ParsedContract,
    RegistrationMethod,
    suggest_methods,
)


class TestCustomerCreation:
    @pytest.fixture
    def directory(self):
        return CustomerDirectory()

    def test_이름만으로_만든다(self, directory):
        # 상담을 시작하려면 「누구 기준인가」만 정해지면 된다.
        customer = directory.add("fa-1", "차○희")
        assert customer.name == "차○희"
        assert customer.advisor_id == "fa-1"
        assert customer.customer_id

    def test_공백_이름은_거부한다(self, directory):
        with pytest.raises(ValueError):
            directory.add("fa-1", "   ")

    def test_앞뒤_공백을_다듬는다(self, directory):
        assert directory.add("fa-1", "  차○희 ").name == "차○희"

    def test_만든_고객은_담당_목록에_들어간다(self, directory):
        created = directory.add("fa-1", "차○희")
        assert directory.get("fa-1", created.customer_id) == created
        assert directory.get("fa-2", created.customer_id) is None

    def test_동명이인을_미리_알려준다(self, directory):
        # 중복이 생기면 약관북과 보장맵이 둘로 쪼개진다.
        directory.add("fa-1", "김○수")
        assert len(directory.duplicates("fa-1", "김○수")) == 1
        assert directory.duplicates("fa-1", "박○영") == []

    def test_다른_FA의_동명이인은_걸리지_않는다(self, directory):
        directory.add("fa-2", "김○수")
        assert directory.duplicates("fa-1", "김○수") == []

    def test_메모로_동명이인을_가른다(self, directory):
        a = directory.add("fa-1", "김○수", note="85년생")
        b = directory.add("fa-1", "김○수", note="92년생")
        assert a.customer_id != b.customer_id
        assert {a.note, b.note} == {"85년생", "92년생"}

    def test_식별자는_이름과_분리한다(self, directory):
        # 동명이인·개명에 견디려면 이름을 키로 쓰면 안 된다.
        customer = directory.add("fa-1", "차○희")
        assert "차○희" not in customer.customer_id


class TestMethodSuggestion:
    def test_MyData가_가장_먼저다(self):
        options = suggest_methods()
        assert options[0].method is RegistrationMethod.MYDATA_IMPORT

    def test_MyData는_아직_열리지_않았다(self):
        # 상황에 없는 방법은 빼지만, 곧 열릴 방법은 두되 잠근다.
        mydata = suggest_methods()[0]
        assert not mydata.available
        assert mydata.hint == "현 시점 오픈하지 않음"
        assert mydata.note

    def test_열리면_고를_수_있게_된다(self):
        mydata = suggest_methods(mydata_open=True)[0]
        assert mydata.available
        assert "한 번에" in mydata.hint

    def test_쓸_수_없는_방법은_빼놓는다(self):
        # 최근 등록 이력이 없는 FA에게 「최근 등록한 상품」을 보여줄 이유가 없다.
        methods = {o.method for o in suggest_methods()}
        assert RegistrationMethod.FROM_CHAT not in methods
        # My Data는 예외 — 빼지 않고 잠근다.
        assert RegistrationMethod.MYDATA_IMPORT in methods

    def test_대화에서_말한_상품이_있으면_바로_등록을_제안한다(self):
        options = suggest_methods(mentioned_product="브라보라이프보험0808")
        chat = next(o for o in options if o.method is RegistrationMethod.FROM_CHAT)
        assert "브라보라이프보험0808" in chat.label

    def test_다른_고객에게_등록한_상품은_제안하지_않는다(self):
        # 지금 이 고객과 무관한 계약을 화면에 끌어오는 셈이 된다.
        labels = " ".join(o.label for o in suggest_methods(mentioned_product="가나보험"))
        assert "최근" not in labels

    def test_검색은_항상_마지막에_남는다(self):
        for kwargs in ({}, {"mydata_open": True}, {"mentioned_product": "가나보험"}):
            assert suggest_methods(**kwargs)[-1].method is RegistrationMethod.SEARCH

    def test_빠른_순으로_정렬된다(self):
        options = suggest_methods(mentioned_product="가나보험")
        assert [o.method for o in options] == [
            RegistrationMethod.MYDATA_IMPORT,
            RegistrationMethod.FROM_CHAT,
            RegistrationMethod.SEARCH,
        ]


class TestImportPreview:
    @pytest.fixture
    def preview(self):
        return ImportPreview(
            source_label="My Data · 2026.05.21 조회",
            contracts=(
                ParsedContract("KB손보", "KB다이렉트플러스운전자보험", 2024, 11,
                               terms_registered=True),
                ParsedContract("DB손보", "브라보라이프보험0808", 2009, 3, terms_registered=True),
                ParsedContract("하나손보", "무배당더블플러스건강보험", 2020, 1),
                ParsedContract("교보라이프플래닛", "라이프플래닛e정기보험", 2018, 3, selected=False),
            ),
        )

    def test_체크된_것만_등록한다(self, preview):
        # 파일에서 읽은 것을 확인 없이 다 넣지 않는다.
        assert len(preview.selected) == 3

    def test_약관이_있는_건과_없는_건을_가른다(self, preview):
        assert len(preview.ready) == 2
        assert len(preview.needs_terms) == 1
        assert preview.needs_terms[0].insurer == "하나손보"

    def test_약관_확보가_필요한_건을_요약에_밝힌다(self, preview):
        # 숨기면 보장맵이 채워진 것처럼 보이는데 답은 못 한다.
        assert preview.summary() == "계약 3건 · 약관 확보 필요 1건"

    def test_아무것도_고르지_않으면_안내한다(self):
        empty = ImportPreview(contracts=(ParsedContract("KB손보", "가나", selected=False),))
        assert "선택해 주세요" in empty.summary()

    def test_가입_시점_표기(self):
        assert ParsedContract("KB손보", "가나", 2024, 11).period_label == "2024.11 가입"
        assert ParsedContract("KB손보", "가나", 2024).period_label == "2024 가입"
        assert ParsedContract("KB손보", "가나").period_label == "가입 시점 미상"


class TestRecentProducts:
    def _link(self, product, customer, when, advisor="fa-1"):
        return CustomerTermsLink(
            customer_id=customer,
            customer_name=customer,
            advisor_id=advisor,
            insurer="DB손보",
            product_name=product,
            contract_year=2020,
            linked_on=when,
        )

    def test_최근_등록순으로_준다(self):
        ledger = TermsLedger()
        ledger.link(self._link("옛날건", "c1", date(2026, 7, 1)))
        ledger.link(self._link("최근건", "c2", date(2026, 8, 12)))

        assert [ln.product_name for ln in ledger.recent_products("fa-1")] == ["최근건", "옛날건"]

    def test_같은_상품은_한_번만_내놓는다(self):
        # 고객이 달라도 상품은 같다.
        ledger = TermsLedger()
        ledger.link(self._link("인기상품", "c1", date(2026, 8, 1)))
        ledger.link(self._link("인기상품", "c2", date(2026, 8, 12)))

        assert len(ledger.recent_products("fa-1")) == 1

    def test_다른_FA의_등록은_섞이지_않는다(self):
        ledger = TermsLedger()
        ledger.link(self._link("내것", "c1", date(2026, 8, 1)))
        ledger.link(self._link("남의것", "c9", date(2026, 8, 12), advisor="fa-2"))

        assert [ln.product_name for ln in ledger.recent_products("fa-1")] == ["내것"]

    def test_개수를_제한한다(self):
        ledger = TermsLedger()
        for i in range(12):
            ledger.link(self._link(f"상품{i}", f"c{i}", date(2026, 8, 1)))

        assert len(ledger.recent_products("fa-1", limit=5)) == 5
