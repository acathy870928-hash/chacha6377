#!/usr/bin/env python3
"""
보험업감독업무시행세칙 [별표 15] 표준약관 PDF를 보험종목별 7개 PDF로 분할한다.

원칙
- 원본 페이지 객체를 그대로 복사한다(재작성·재조판 없음). 글자·표·서식이 원문과 동일하게 유지된다.
- 각 약관의 시작 페이지는 페이지 상단 텍스트에서 약관 제목을 찾아 자동 판별한다.
- 자동 판별 결과는 항상 `--dry-run` / `--detect` 로 사람이 확인할 수 있고,
  `--ranges ranges.json` 으로 페이지 범위를 직접 지정해 덮어쓸 수 있다.
- 분할 결과는 빠짐·겹침 없이 원본 페이지를 정확히 한 번씩 나누어 담아야 하며, 이를 검증한다.
- 결과와 함께 manifest(원본/결과 SHA-256, 페이지 범위)를 기록해 원문 동일성을 증빙한다.

사용 예
  python tools/split_standard_terms.py 원본.pdf --detect            # 제목 후보 페이지 확인
  python tools/split_standard_terms.py 원본.pdf --dry-run           # 분할 계획만 출력
  python tools/split_standard_terms.py 원본.pdf -o out/             # 분할 실행
  python tools/split_standard_terms.py 원본.pdf -o out/ --ranges ranges.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    sys.exit("pypdf 가 필요합니다:  pip install pypdf")


EFFECTIVE_DATE = "20260910"  # [시행 2026.9.10] [2026.8.28 일부개정]


@dataclass(frozen=True)
class Section:
    key: str            # ranges.json 의 키
    order: int          # 출력 파일 번호
    label: str          # 출력 파일명 본문
    pattern: str        # 정규화된 텍스트(공백·구두점 제거)에 대한 정규식
    note: str = ""

    @property
    def filename(self) -> str:
        return f"{self.order:02d}_{self.label}_표준약관_{EFFECTIVE_DATE}.pdf"


# 정규화된 텍스트에는 공백·괄호·가운뎃점 등이 모두 제거되어 있으므로
# "질병·상해보험 표준약관" 도 "질병상해보험표준약관" 으로 매칭된다.
SECTIONS: list[Section] = [
    Section("life", 1, "생명보험", r"생명보험표준약관"),
    Section("fire", 2, "화재보험", r"화재보험표준약관"),
    Section("auto", 3, "자동차보험", r"자동차보험표준약관"),
    Section("health", 4, "질병상해보험", r"질병상해보험표준약관"),
    # "해외여행실손의료보험표준약관" 안에 "실손의료보험표준약관" 이 포함되므로 앞에 해외여행이 없는 경우만 매칭
    Section("medical", 5, "실손의료보험", r"(?<!해외여행)실손의료보험표준약관", "급여·비급여 특별약관 포함"),
    Section("travel", 6, "해외여행실손의료보험", r"해외여행실손의료보험표준약관", "급여·비급여 특별약관 포함"),
    Section("liability", 7, "배상책임보험", r"배상책임보험표준약관"),
]
SECTION_BY_KEY = {s.key: s for s in SECTIONS}

_STRIP_RE = re.compile(r"[\s·ㆍ•・‧/,.\-–—()\[\]【】〔〕「」『』<>〈〉《》:;'\"“”‘’ㆍ]+")


def normalize(text: str) -> str:
    return _STRIP_RE.sub("", text or "")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def page_texts(reader: PdfReader) -> list[str]:
    texts = []
    for i, page in enumerate(reader.pages):
        try:
            texts.append(page.extract_text() or "")
        except Exception as e:  # pragma: no cover - 손상 페이지 방어
            print(f"[경고] {i + 1}쪽 텍스트 추출 실패: {e}", file=sys.stderr)
            texts.append("")
    return texts


def detect_candidates(texts: list[str], head_chars: int) -> list[dict]:
    """각 페이지에 대해 상단(head)에서 매칭된 약관 키 목록과 본문 전체 매칭 키 목록을 돌려준다."""
    rows = []
    for i, text in enumerate(texts):
        norm = normalize(text)
        head = norm[:head_chars]
        head_keys = [s.key for s in SECTIONS if re.search(s.pattern, head)]
        any_keys = [s.key for s in SECTIONS if re.search(s.pattern, norm)]
        rows.append({"page": i + 1, "head": head_keys, "anywhere": any_keys, "snippet": norm[:60]})
    return rows


def detect_starts(texts: list[str], head_chars: int) -> dict[str, int]:
    """약관별 시작 페이지(0-based)를 판별한다.

    규칙
    - 페이지 상단에서 정확히 하나의 약관 제목만 매칭되는 페이지를 후보로 본다
      (여러 제목이 동시에 나오는 표지·목차 페이지는 제외).
    - 약관별로 첫 번째 후보 페이지를 시작 페이지로 삼는다.
      (머리글에 약관명이 반복되는 PDF에서도 첫 페이지가 시작이 된다.)
    """
    starts: dict[str, int] = {}
    for row in detect_candidates(texts, head_chars):
        if len(row["head"]) != 1:
            continue
        key = row["head"][0]
        starts.setdefault(key, row["page"] - 1)
    return starts


def ranges_from_starts(starts: dict[str, int], n_pages: int) -> tuple[dict[str, tuple[int, int]], list[int]]:
    """시작 페이지들로부터 (start, end) 0-based inclusive 범위를 만든다. 첫 약관 이전 페이지는 prefix 로 돌려준다."""
    missing = [s.key for s in SECTIONS if s.key not in starts]
    if missing:
        raise SystemExit(
            "시작 페이지를 찾지 못한 약관: " + ", ".join(missing)
            + "\n  --detect 로 후보를 확인한 뒤 --ranges 로 직접 지정하세요."
        )
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    ranges: dict[str, tuple[int, int]] = {}
    for idx, (key, start) in enumerate(ordered):
        end = ordered[idx + 1][1] - 1 if idx + 1 < len(ordered) else n_pages - 1
        ranges[key] = (start, end)
    prefix = list(range(0, ordered[0][1]))
    return ranges, prefix


def load_ranges(path: Path, n_pages: int) -> dict[str, tuple[int, int]]:
    """ranges.json: {"life": [1, 40], "fire": [41, 60], ...}  (1-based inclusive)"""
    data = json.loads(path.read_text(encoding="utf-8"))
    ranges: dict[str, tuple[int, int]] = {}
    for key, val in data.items():
        if key not in SECTION_BY_KEY:
            raise SystemExit(f"ranges.json 에 알 수 없는 키: {key} (허용: {', '.join(SECTION_BY_KEY)})")
        if not (isinstance(val, list) and len(val) == 2 and all(isinstance(v, int) for v in val)):
            raise SystemExit(f"{key}: [시작쪽, 끝쪽] 형식(1-based)이어야 합니다: {val}")
        s, e = val[0] - 1, val[1] - 1
        if not (0 <= s <= e < n_pages):
            raise SystemExit(f"{key}: 범위 {val} 가 원본 페이지 수({n_pages})를 벗어납니다")
        ranges[key] = (s, e)
    return ranges


def validate_ranges(ranges: dict[str, tuple[int, int]], n_pages: int, prefix: list[int]) -> None:
    missing = [s.key for s in SECTIONS if s.key not in ranges]
    if missing:
        raise SystemExit("범위가 지정되지 않은 약관: " + ", ".join(missing))
    covered = [0] * n_pages
    for s, e in ranges.values():
        for p in range(s, e + 1):
            covered[p] += 1
    for p in prefix:
        covered[p] += 1
    dup = [p + 1 for p, c in enumerate(covered) if c > 1]
    gap = [p + 1 for p, c in enumerate(covered) if c == 0]
    if dup:
        raise SystemExit(f"겹치는 페이지: {dup}")
    if gap:
        raise SystemExit(f"누락된 페이지: {gap}")


def plan_table(ranges: dict[str, tuple[int, int]], texts: list[str]) -> str:
    lines = [f"{'번호':<4} {'파일명':<44} {'쪽 범위':<12} {'쪽수':>4}  첫 줄"]
    for sec in SECTIONS:
        s, e = ranges[sec.key]
        first = (texts[s] or "").strip().splitlines()[:1]
        lines.append(f"{sec.order:<4} {sec.filename:<44} {s + 1:>4}-{e + 1:<7} {e - s + 1:>4}  {first[0][:40] if first else ''}")
    return "\n".join(lines)


def write_outputs(reader: PdfReader, ranges: dict[str, tuple[int, int]], out_dir: Path, src: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    src_meta = reader.metadata or {}
    manifest = {
        "source": {"file": src.name, "sha256": sha256(src), "pages": len(reader.pages)},
        "effective_date": "2026-09-10",
        "basis": "보험업감독업무시행세칙 [별표 15] 표준약관 [시행 2026.9.10] [2026.8.28 일부개정]",
        "outputs": [],
    }
    for sec in SECTIONS:
        s, e = ranges[sec.key]
        writer = PdfWriter()
        for p in range(s, e + 1):
            writer.add_page(reader.pages[p])  # 페이지 객체를 그대로 복사 (내용 재작성 없음)
        meta = {"/Title": f"{sec.label} 표준약관 (시행 2026.9.10)"}
        for k in ("/Author", "/Producer", "/Creator"):
            if k in src_meta and src_meta[k]:
                meta[k] = str(src_meta[k])
        writer.add_metadata(meta)
        out = out_dir / sec.filename
        with open(out, "wb") as f:
            writer.write(f)
        manifest["outputs"].append({
            "order": sec.order, "key": sec.key, "file": sec.filename, "note": sec.note,
            "source_pages": [s + 1, e + 1], "page_count": e - s + 1, "sha256": sha256(out),
        })
    (out_dir / "split_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", type=Path, help="[별표 15] 표준약관 원본 PDF")
    ap.add_argument("-o", "--out-dir", type=Path, default=Path("standard_terms") / EFFECTIVE_DATE)
    ap.add_argument("--ranges", type=Path, help="페이지 범위를 직접 지정하는 JSON (1-based, inclusive)")
    ap.add_argument("--head-chars", type=int, default=80, help="제목을 찾을 페이지 상단 글자 수(정규화 기준)")
    ap.add_argument("--prefix-to-first", action="store_true",
                    help="첫 약관 앞의 표지/목차 페이지를 1번 파일(생명보험)에 포함")
    ap.add_argument("--detect", action="store_true", help="페이지별 제목 매칭 결과만 출력")
    ap.add_argument("--dry-run", action="store_true", help="분할 계획만 출력하고 파일은 쓰지 않음")
    args = ap.parse_args(argv)

    if not args.source.is_file():
        raise SystemExit(f"원본 파일을 찾을 수 없습니다: {args.source}")
    reader = PdfReader(str(args.source))
    if reader.is_encrypted:
        reader.decrypt("")
    n = len(reader.pages)
    texts = page_texts(reader)
    print(f"원본: {args.source}  ({n}쪽, sha256 {sha256(args.source)[:16]}…)")

    if args.detect:
        for row in detect_candidates(texts, args.head_chars):
            if row["head"] or row["anywhere"]:
                print(f"{row['page']:>5}쪽  상단={row['head'] or '-'}  본문={row['anywhere'] or '-'}  | {row['snippet']}")
        return 0

    prefix: list[int] = []
    if args.ranges:
        ranges = load_ranges(args.ranges, n)
        first = min(s for s, _ in ranges.values())
        prefix = list(range(0, first))
        print(f"페이지 범위: {args.ranges} 에서 읽음")
    else:
        starts = detect_starts(texts, args.head_chars)
        ranges, prefix = ranges_from_starts(starts, n)
        print("페이지 범위: 제목 자동 판별")

    if prefix:
        if args.prefix_to_first:
            first_key = min(ranges, key=lambda k: ranges[k][0])
            ranges[first_key] = (0, ranges[first_key][1])
            print(f"표지/목차 {len(prefix)}쪽(1-{len(prefix)}쪽)을 첫 약관 파일에 포함")
            prefix = []
        else:
            print(f"[안내] 첫 약관 앞 {len(prefix)}쪽(1-{len(prefix)}쪽)은 어느 파일에도 넣지 않습니다. 포함하려면 --prefix-to-first")

    validate_ranges(ranges, n, prefix)
    print(plan_table(ranges, texts))
    if args.dry_run:
        return 0

    manifest = write_outputs(reader, ranges, args.out_dir, args.source)
    print(f"\n완료: {args.out_dir}/ 에 {len(manifest['outputs'])}개 파일 + split_manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
