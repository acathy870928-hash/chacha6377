import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

import make_fixture_pdf  # noqa: E402
import split_standard_terms as sst  # noqa: E402


@pytest.fixture(scope="module")
def fixture(tmp_path_factory):
    d = tmp_path_factory.mktemp("fx")
    pdf = d / "fixture.pdf"
    spans = make_fixture_pdf.build(pdf)
    return pdf, spans


def _expected(spans):
    by_title = {t: (s, e) for t, s, e in spans}
    return {
        "life": by_title["생명보험 표준약관"],
        "health": by_title["질병·상해보험 표준약관"],
        "fire": by_title["화재보험 표준약관"],
        "auto": by_title["자동차보험 표준약관"],
        "liability": by_title["배상책임보험 표준약관"],
        "medical": by_title["실손의료보험 표준약관"],
        "travel": by_title["해외여행 실손의료보험 표준약관"],
    }


def test_normalize_handles_middle_dots_and_spaces():
    assert sst.normalize("질병 · 상해보험  표준약관") == "질병상해보험표준약관"
    assert sst.normalize("해외여행 실손의료보험 표준약관") == "해외여행실손의료보험표준약관"


def test_medical_pattern_does_not_match_travel():
    import re
    med = sst.SECTION_BY_KEY["medical"].pattern
    assert re.search(med, "실손의료보험표준약관")
    assert not re.search(med, "해외여행실손의료보험표준약관")


def test_auto_detection_matches_fixture_layout(fixture):
    pdf, spans = fixture
    reader = pypdf.PdfReader(str(pdf))
    texts = sst.page_texts(reader)
    starts = sst.detect_starts(texts, 80)
    ranges, prefix = sst.ranges_from_starts(starts, len(reader.pages))
    assert prefix == [0], "표지/목차 페이지는 어느 약관에도 속하지 않아야 한다"
    got = {k: (s + 1, e + 1) for k, (s, e) in ranges.items()}
    assert got == _expected(spans)
    sst.validate_ranges(ranges, len(reader.pages), prefix)


def test_cli_writes_seven_files_and_manifest(fixture, tmp_path):
    pdf, spans = fixture
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, str(ROOT / "tools/split_standard_terms.py"), str(pdf), "-o", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    files = sorted(p.name for p in out.glob("*.pdf"))
    assert files == [s.filename for s in sst.SECTIONS]
    manifest = json.loads((out / "split_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"]["pages"] == len(pypdf.PdfReader(str(pdf)).pages)
    exp = _expected(spans)
    for o in manifest["outputs"]:
        assert tuple(o["source_pages"]) == exp[o["key"]]
        rd = pypdf.PdfReader(str(out / o["file"]))
        assert len(rd.pages) == o["page_count"]
        # 각 결과 파일의 첫 쪽에 해당 약관 제목이 있고, 원본 페이지 번호 표기가 그대로 남아 있다
        raw = rd.pages[0].extract_text()
        assert sst.SECTION_BY_KEY[o["key"]].label in sst.normalize(raw)
        assert f"-{o['source_pages'][0]}-" in raw.replace(" ", "")


def test_ranges_override_and_validation(fixture, tmp_path):
    pdf, spans = fixture
    exp = _expected(spans)
    rj = tmp_path / "ranges.json"
    rj.write_text(json.dumps({k: list(v) for k, v in exp.items()}), encoding="utf-8")
    out = tmp_path / "out2"
    r = subprocess.run([sys.executable, str(ROOT / "tools/split_standard_terms.py"), str(pdf), "-o", str(out),
                        "--ranges", str(rj), "--prefix-to-first"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr + r.stdout
    life = pypdf.PdfReader(str(out / sst.SECTION_BY_KEY["life"].filename))
    assert len(life.pages) == exp["life"][1]  # 표지 1쪽 포함

    # 겹침이 있으면 실패해야 한다
    bad = dict(exp)
    bad["fire"] = [exp["fire"][0] - 1, exp["fire"][1]]
    rj.write_text(json.dumps({k: list(v) for k, v in bad.items()}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools/split_standard_terms.py"), str(pdf), "-o", str(out),
                        "--ranges", str(rj), "--dry-run"], capture_output=True, text=True)
    assert r.returncode != 0 and "겹치는 페이지" in (r.stderr + r.stdout)
