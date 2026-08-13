from orca.requests import RequestLog, TermsRequest
from orca.versioning import ApproxDate


def _request(name, year=None, insurer="○○생명", question=""):
    return TermsRequest(
        product_name=name,
        insurer=insurer,
        contract_date=ApproxDate(year) if year else None,
        question=question,
    )


class TestPriorities:
    def test_요청이_많은_약관이_먼저_온다(self):
        log = RequestLog()
        for _ in range(3):
            log.record(_request("옛날든든보험", 2018))
        log.record(_request("다른보험", 2020))

        ranked = log.priorities()
        assert [(r.product_name, count) for r, count in ranked] == [
            ("옛날든든보험", 3),
            ("다른보험", 1),
        ]

    def test_같은_상품이라도_가입_연도가_다르면_따로_센다(self):
        # 연도가 다르면 필요한 판이 다를 수 있다.
        log = RequestLog()
        log.record(_request("옛날든든보험", 2018))
        log.record(_request("옛날든든보험", 2018))
        log.record(_request("옛날든든보험", 2022))

        ranked = log.priorities()
        assert [count for _, count in ranked] == [2, 1]

    def test_건수가_같으면_먼저_요청된_것이_앞에_온다(self):
        log = RequestLog()
        log.record(_request("먼저요청", 2019))
        log.record(_request("나중요청", 2019))

        ranked = log.priorities()
        assert [r.product_name for r, _ in ranked] == ["먼저요청", "나중요청"]

    def test_보험사가_다르면_다른_약관이다(self):
        log = RequestLog()
        log.record(_request("든든보험", 2020, insurer="○○생명"))
        log.record(_request("든든보험", 2020, insurer="△△화재"))

        assert len(log.priorities()) == 2

    def test_상위_몇_건만_받을_수_있다(self):
        log = RequestLog()
        for name in ("가", "나", "다", "라"):
            log.record(_request(name, 2020))

        assert len(log.priorities(limit=2)) == 2

    def test_대표_요청에_원_질문이_남는다(self):
        log = RequestLog()
        log.record(_request("옛날든든보험", 2018, question="음주운전 사고인데 나오나요?"))

        representative, _ = log.priorities()[0]
        assert representative.question == "음주운전 사고인데 나오나요?"

    def test_비어_있으면_빈_목록(self):
        assert RequestLog().priorities() == []
        assert RequestLog().unresolved_count() == 0
