"""선정 결과 검증 (python -m pytest beluga/tests_selection.py)"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from classify import line, sector, simplified  # noqa: E402
from select27 import load, select  # noqa: E402

rows = load(str(Path(__file__).resolve().parent / "data/판매실적_상품목록.xlsx"))
chosen, reasons, alts = select(rows)


def test_source_has_199_products():
    assert len(rows) == 199


def test_exactly_27_selected_and_unique():
    assert len(chosen) == 27
    assert len({r["no"] for r in chosen}) == 27


def test_both_sectors_present():
    c = collections.Counter(r["sector"] for r in chosen)
    assert c["생명보험"] > 0 and c["손해보험"] > 0


def test_every_line_in_source_has_at_least_one_pick():
    all_groups = {(r["sector"], r["line"]) for r in rows}
    picked_groups = {(r["sector"], r["line"]) for r in chosen}
    assert all_groups == picked_groups


def test_top_of_each_line_is_selected():
    for g in {(r["sector"], r["line"]) for r in rows}:
        top = next(r for r in rows if (r["sector"], r["line"]) == g)
        assert top in chosen, f"{g} 1위 미선정: {top['name']}"


def test_no_duplicate_insurer_line_pair():
    pairs = [(r["insurer"], r["line"]) for r in chosen]
    assert len(pairs) == len(set(pairs))


def test_no_line_exceeds_cap():
    c = collections.Counter((r["sector"], r["line"]) for r in chosen)
    assert max(c.values()) <= 3


def test_classification_rules():
    assert sector("삼성생명") == "생명보험" and sector("삼성화재") == "손해보험"
    assert line("메리츠 유병력자 실손의료비보험") == "실손의료보험"
    assert line("(무)삼성화재 운전자보험 안전운전 파트너 플러스", "삼성화재") == "운전자보험"
    assert line("(무)삼성화재간편보험마이핏", "삼성화재") == "건강·종합·보장보험"
    assert line("무배당성공하는Owner재산종합보험") == "재물·화재·가정종합보험"
    assert simplified("KB 탑클래스 3.N.5 초경증 간편건강보험")
    assert not simplified("삼성 더행복종신보험")


def test_no_unknown_line_bucket():
    assert all(r["line"] != "기타" for r in rows)
