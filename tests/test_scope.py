"""약관 스코프 — 검색 전에 한 권으로 좁히고, 결과를 그 안에 가둔다.

약관은 서로 80~90%가 닮아 있어 스코프 없이 검색하면 아무거나 집어온다.
게다가 검색은 「모르겠다」를 출력할 수 없어 1등은 반드시 나온다.
그래서 막는 자리를 코드로 만들고 여기서 지킨다.
"""

import pytest

from orca.scope import (
    AnswerBasis,
    InsuranceLine,
    Retrieved,
    ScopeLevel,
    ScopeNotLocked,
    ScopeVerdict,
    TermsScope,
    confine,
    require_locked,
)


def _scope(**kw) -> TermsScope:
    base = dict(
        insurer="DB손해보험",
        line=InsuranceLine.LONG_TERM,
        product_name="무배당 프로미라이프 참좋은동행보험",
        product_id="db-good-journey",
        edition_id="ed-2109",
        edition_label="2021.09 시행판",
    )
    base.update(kw)
    return TermsScope(**base)


def _hit(score=0.8, **kw) -> Retrieved:
    base = dict(
        clause_ref="제5조 제2항",
        text="…골절의 진단이 확정된 경우…",
        score=score,
        insurer="DB손해보험",
        product_key="db-good-journey",
        edition_id="ed-2109",
    )
    base.update(kw)
    return Retrieved(**base)


class TestLevel:
    def test_단계는_보험사_보종_상품_판_순이다(self):
        assert TermsScope().level is ScopeLevel.NONE
        assert TermsScope(insurer="DB손해보험").level is ScopeLevel.INSURER
        assert TermsScope(
            insurer="DB손해보험", line=InsuranceLine.LONG_TERM
        ).level is ScopeLevel.LINE
        assert _scope(edition_id="").level is ScopeLevel.PRODUCT
        assert _scope().level is ScopeLevel.EDITION

    def test_판까지_정해져야_잠긴다(self):
        # 상품까지만으로는 안 된다. 판이 다르면 답이 달라진다.
        assert not _scope(edition_id="").is_locked
        assert _scope().is_locked

    def test_다음에_고를_것을_알려준다(self):
        assert TermsScope().next_step == "보험사"
        assert TermsScope(insurer="DB손해보험").next_step == "보종"
        assert _scope(edition_id="").next_step == "가입 시점(판)"
        assert _scope().next_step is None

    def test_화면에_띄울_한_줄(self):
        # 어느 약관으로 답하고 있는지가 보이지 않으면 답을 옮길 수 없다.
        assert _scope().label == (
            "DB손해보험 · 무배당 프로미라이프 참좋은동행보험 · 2021.09 시행판"
        )
        assert TermsScope().label == "약관 미지정"


class TestRequireLocked:
    def test_잠기지_않으면_검색을_막는다(self):
        # 막지 않으면 100권을 뒤진 결과가 그대로 답이 된다.
        with pytest.raises(ScopeNotLocked):
            require_locked(_scope(edition_id=""))

    def test_다음_단계를_예외에_담는다(self):
        with pytest.raises(ScopeNotLocked, match="보종"):
            require_locked(TermsScope(insurer="DB손해보험"))

    def test_잠겼으면_통과한다(self):
        require_locked(_scope())


class TestConfine:
    def test_스코프_안의_근거만_채택한다(self):
        result = confine([_hit()], _scope())
        assert result.verdict is ScopeVerdict.FOUND
        assert len(result.kept) == 1

    def test_다른_상품_조항은_점수가_높아도_버린다(self):
        # 약관은 서로 90%가 닮아 남의 조항이 1등으로 올라온다.
        hits = [_hit(score=0.99, product_key="kb-driver"), _hit(score=0.5)]
        result = confine(hits, _scope())

        assert [h.product_key for h in result.kept] == ["db-good-journey"]
        assert len(result.out_of_scope) == 1

    def test_다른_판_조항도_버린다(self):
        result = confine([_hit(edition_id="ed-1803")], _scope())
        assert result.kept == ()
        assert len(result.out_of_scope) == 1

    def test_점수_미달은_근거로_쓰지_않는다(self):
        # 「닮은 것 중 1등」일 뿐인 결과를 조항으로 제시하면 안 된다.
        result = confine([_hit(score=0.1)], _scope(), score_floor=0.35)
        assert result.kept == ()
        assert len(result.below_floor) == 1

    def test_남는_것이_없으면_해당_조항_없음이다(self):
        # 순위를 낮춰가며 채우지 않는다.
        result = confine([_hit(product_key="kb-driver")], _scope())
        assert result.verdict is ScopeVerdict.NO_CLAUSE
        assert not result.has_evidence

    def test_결과가_비어도_조항_없음으로_끝낸다(self):
        assert confine([], _scope()).verdict is ScopeVerdict.NO_CLAUSE

    def test_잠기지_않은_스코프로는_거르지_않는다(self):
        result = confine([_hit()], _scope(edition_id=""))
        assert result.verdict is ScopeVerdict.NOT_LOCKED
        assert result.kept == ()

    def test_점수가_높은_순으로_준다(self):
        hits = [_hit(score=0.4, clause_ref="제9조"), _hit(score=0.9, clause_ref="제5조")]
        assert [h.clause_ref for h in confine(hits, _scope()).kept] == ["제5조", "제9조"]

    def test_버린_것을_남긴다(self):
        # 스코프 밖 반환이 계속 나오면 벤더 필터가 안 도는다는 신호다.
        result = confine(
            [_hit(product_key="kb-driver"), _hit(score=0.05), _hit()], _scope()
        )
        note = result.note()
        assert "채택 1" in note and "스코프밖 1" in note and "점수미달 1" in note


class TestAnswerBasis:
    def test_근거_종류를_구분한다(self):
        # 담보 데이터로 답한 것과 약관 원문으로 답한 것을 섞으면
        # 외부 데이터가 틀렸을 때 책임 범위를 가릴 수 없다.
        assert len({AnswerBasis.TERMS, AnswerBasis.COVERAGE_DATA, AnswerBasis.GENERAL}) == 3
