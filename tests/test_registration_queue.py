"""등록 후보 산정과 예산 배분.

벤더 약관 등록에는 비용이 든다. 요청이 왔다고 자동 등록하지 않고,
비용 대비 수요로 골라 승인한다.
"""

from orca.requests import RegistrationCandidate, RequestLog, TermsRequest, select_within_budget
from orca.versioning import ApproxDate


def _req(name, year, requester, *, product_id="p", question="", insurer="○○생명"):
    return TermsRequest(
        product_name=name,
        insurer=insurer,
        product_id=f"{product_id}:{name}" if product_id else None,
        contract_date=ApproxDate(year),
        question=question,
        requester_id=requester,
    )


def _candidate(name, *, requesters, requests_n, identified=True):
    return RegistrationCandidate(
        key=("○○생명", name, 2020),
        product_name=name,
        insurer="○○생명",
        product_id=f"id:{name}" if identified else None,
        edition_label="1판",
        contract_year=2020,
        request_count=requests_n,
        requester_count=requesters,
        questions=[],
    )


class TestCandidates:
    def test_같은_약관_요청을_하나로_묶는다(self):
        log = RequestLog()
        log.record(_req("옛날든든보험", 2018, "fa-1"))
        log.record(_req("옛날든든보험", 2018, "fa-2"))
        log.record(_req("다른보험", 2020, "fa-1"))

        candidates = log.candidates()
        assert len(candidates) == 2

        target = next(c for c in candidates if c.product_name == "옛날든든보험")
        assert target.request_count == 2
        assert target.requester_count == 2

    def test_같은_FA의_반복_요청은_요청자_수에_한_번만_센다(self):
        log = RequestLog()
        for _ in range(5):
            log.record(_req("옛날든든보험", 2018, "fa-1"))

        candidate = log.candidates()[0]
        assert candidate.request_count == 5
        assert candidate.requester_count == 1

    def test_가입_연도가_다르면_다른_후보다(self):
        # 판이 다르면 등록도 따로 해야 하므로 비용도 따로 든다.
        log = RequestLog()
        log.record(_req("실손의료비보장보험", 2015, "fa-1"))
        log.record(_req("실손의료비보장보험", 2021, "fa-2"))

        assert len(log.candidates()) == 2

    def test_검수용_질문이_후보에_실린다(self):
        log = RequestLog()
        log.record(_req("옛날든든보험", 2018, "fa-1", question="골절 진단금 나오나요?"))

        assert log.candidates()[0].questions == ["골절 진단금 나오나요?"]


class TestDemand:
    def test_여러_명이_물은_쪽을_더_높게_본다(self):
        # 한 사람이 열 번 vs 열 사람이 한 번 — 후자가 조직 전체로 더 자주 막힌다.
        one_person = _candidate("A", requesters=1, requests_n=10)
        many_people = _candidate("B", requesters=10, requests_n=10)
        assert many_people.demand > one_person.demand


class TestBudgetSelection:
    def test_예산만큼만_승인하고_나머지는_보류한다(self):
        candidates = [
            _candidate("A", requesters=9, requests_n=9),
            _candidate("B", requesters=6, requests_n=6),
            _candidate("C", requesters=3, requests_n=3),
        ]
        approved, held = select_within_budget(candidates, editions_budget=2)

        assert [c.product_name for c in approved] == ["A", "B"]
        assert [c.product_name for c in held] == ["C"]

    def test_요청자가_적으면_비용을_들이지_않는다(self):
        candidates = [
            _candidate("A", requesters=1, requests_n=8),
            _candidate("B", requesters=4, requests_n=4),
        ]
        approved, held = select_within_budget(candidates, editions_budget=10, min_requesters=2)

        # 한 명이 여덟 번 물어도 단독 요청이면 승인하지 않는다.
        assert [c.product_name for c in approved] == ["B"]
        assert [c.product_name for c in held] == ["A"]

    def test_식별되지_않은_상품명은_자동_승인하지_않는다(self):
        # 마스터에 없는 이름은 오타일 수 있다. 비용을 들이기 전에 사람이 본다.
        candidates = [_candidate("처음보는보험", requesters=5, requests_n=5, identified=False)]
        approved, held = select_within_budget(candidates, editions_budget=10)

        assert approved == []
        assert len(held) == 1

    def test_보류_목록도_수요순으로_정렬된다(self):
        candidates = [
            _candidate("A", requesters=2, requests_n=2),
            _candidate("B", requesters=7, requests_n=7),
            _candidate("C", requesters=5, requests_n=5),
        ]
        _, held = select_within_budget(candidates, editions_budget=1)
        assert [c.product_name for c in held] == ["C", "A"]

    def test_예산이_0이면_아무것도_승인하지_않는다(self):
        approved, held = select_within_budget(
            [_candidate("A", requesters=9, requests_n=9)], editions_budget=0
        )
        assert approved == []
        assert len(held) == 1
