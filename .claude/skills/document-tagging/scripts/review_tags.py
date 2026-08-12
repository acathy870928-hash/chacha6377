#!/usr/bin/env python3
"""태깅 결과 전체를 검토해 태그 체계 정리 리포트를 만든다.

사용법:
    python3 review_tags.py 태깅결과.json -o 검토리포트.md
    python3 review_tags.py 태깅결과.xlsx -o 검토리포트.md

태깅의 목표는 태그를 많이 만드는 것이 아니라 적은 수의 태그를 여러 문서가
공유하게 만드는 것이다. 그래서 이 리포트는 "몇 개나 붙였나"가 아니라
"어떤 태그가 혼자 놀고 있나 / 어떤 태그끼리 사실상 같은 말인가"를 본다.
"""

import argparse
import json
import os
from collections import Counter, defaultdict

RARE_THRESHOLD = 3          # 이 이하로 쓰인 태그는 지나치게 고유할 가능성이 있어 재검토 대상
DUP_RATIO = 0.80            # 한 태그가 다른 태그와 이 비율 이상 함께 붙으면 중복 의심


def load_records(path: str):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = ["" if c is None else str(c) for c in next(it)]
        cols = {name: header.index(name) for name in header}
        records = []
        for row in it:
            row = ["" if c is None else str(c) for c in row]
            get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else ""
            records.append({
                "제목": get("제목") or get("파일명"),
                "태깅여부": get("태깅여부"),
                "태그": [t for t in (get("태그1"), get("태그2"), get("태그3")) if t],
            })
        return records

    import csv
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return [{"제목": r.get("제목") or r.get("파일명", ""),
             "태깅여부": r.get("태깅여부", ""),
             "태그": [r.get(k, "") for k in ("태그1", "태그2", "태그3") if r.get(k)]}
            for r in rows]


def build_report(records, dictionary_tags=None):
    targets = [r for r in records if r.get("태깅여부") == "대상"]
    excluded = [r for r in records if r.get("태깅여부") == "제외"]

    counts = Counter(t for r in targets for t in r["태그"])
    pairs = Counter()
    for r in targets:
        tags = sorted(set(r["태그"]))
        for i, a in enumerate(tags):
            for b in tags[i + 1:]:
                pairs[(a, b)] += 1

    rare = sorted([(t, c) for t, c in counts.items() if c <= RARE_THRESHOLD], key=lambda x: x[1])

    # 사실상 같은 말인지 의심되는 조합: 함께 붙는 비율이 높거나, 태그명이 서로 포함 관계
    dup = []
    for (a, b), n in pairs.items():
        ratio = n / min(counts[a], counts[b])
        if ratio >= DUP_RATIO:
            dup.append((a, b, n, ratio, "동시 사용 %.0f%%" % (ratio * 100)))
    for a in counts:
        for b in counts:
            if a != b and a in b and not any(d[0] == a and d[1] == b for d in dup):
                dup.append((a, b, pairs.get(tuple(sorted((a, b))), 0),
                            0.0, "태그명 포함 관계"))
    dup.sort(key=lambda d: -d[3])

    examples = defaultdict(list)
    for r in targets:
        for t in r["태그"]:
            if len(examples[t]) < 3:
                examples[t].append(r.get("제목", "")[:70])

    lines = []
    add = lines.append
    add("# 태그 체계 최종 검토 리포트\n")
    add("## 1. 전체 현황\n")
    add("| 항목 | 값 |")
    add("| --- | ---: |")
    add("| 전체 문서 | %d건 |" % len(records))
    add("| 태깅 대상 | %d건 |" % len(targets))
    add("| 태깅 제외 | %d건 |" % len(excluded))
    add("| 사용된 태그 종류 | %d개 |" % len(counts))
    add("| 문서당 평균 태그 수 | %.2f개 |" % (sum(len(r["태그"]) for r in targets) / max(1, len(targets))))
    add("| 태그당 평균 문서 수 | %.1f건 |" % (sum(counts.values()) / max(1, len(counts))))
    if dictionary_tags:
        unused = [t for t in dictionary_tags if t not in counts]
        add("| 사전에 있으나 미사용된 태그 | %d개 |" % len(unused))
    add("")

    if excluded:
        add("### 제외 사유별 분포\n")
        reasons = Counter(r.get("판단근거", "").replace("에 해당하여 태깅 제외", "") for r in excluded)
        add("| 제외 사유 | 문서 수 |")
        add("| --- | ---: |")
        for reason, n in reasons.most_common():
            add("| %s | %d |" % (reason or "(미기재)", n))
        add("")

    add("## 2. 태그별 사용 문서 수\n")
    add("| 순위 | 태그 | 문서 수 | 비중 | 예시 문서 |")
    add("| ---: | --- | ---: | ---: | --- |")
    total = sum(counts.values())
    for i, (tag, n) in enumerate(counts.most_common(), start=1):
        add("| %d | #%s | %d | %.1f%% | %s |" % (i, tag, n, n / total * 100, examples[tag][0] if examples[tag] else ""))
    add("")

    add("## 3. 재검토가 필요한 저빈도 태그 (%d건 이하)\n" % RARE_THRESHOLD)
    if rare:
        add("한두 문서에만 붙은 태그는 지나치게 고유한 태그일 가능성이 있다. 상위 개념으로 올리거나 기존 태그로 흡수할지 판단한다.\n")
        add("| 태그 | 문서 수 | 사용된 문서 |")
        add("| --- | ---: | --- |")
        for tag, n in rare:
            add("| #%s | %d | %s |" % (tag, n, " / ".join(examples[tag])))
    else:
        add("1~%d건만 쓰인 태그 없음. 모든 태그가 여러 문서에서 공유되고 있다." % RARE_THRESHOLD)
    add("")

    add("## 4. 의미가 겹칠 가능성이 있는 태그\n")
    if dup:
        add("| 태그 A | 태그 B | 함께 붙은 문서 | 판단 근거 |")
        add("| --- | --- | ---: | --- |")
        for a, b, n, _, why in dup[:30]:
            add("| #%s | #%s | %d | %s |" % (a, b, n, why))
    else:
        add("동시 사용률이 높은 태그 조합 없음.")
    add("")

    add("## 5. 통합 권장\n")
    recs = []
    for tag, n in rare:
        recs.append("- `#%s` (%d건): 저빈도. 상위 개념 태그로 흡수하거나, 앞으로도 반복될 개념인지 확인 후 유지 여부 결정." % (tag, n))
    for a, b, n, ratio, why in dup[:10]:
        if ratio >= DUP_RATIO:
            smaller, bigger = (a, b) if counts[a] <= counts[b] else (b, a)
            recs.append("- `#%s` → `#%s`: %s(%d건 겹침). 별도 태그로 남길 이유가 없으면 상위 태그로 통합." % (smaller, bigger, why, n))
    if recs:
        lines.extend(recs)
    else:
        add("현재 태그 체계에서 즉시 통합이 필요한 항목 없음.")
    add("")

    add("## 6. 통합 후 최종 표준 태그 목록\n")
    keep = [t for t, n in counts.most_common() if n > RARE_THRESHOLD]
    add("총 %d개\n" % len(keep))
    add(" ".join("#" + t for t in sorted(keep)))
    add("")
    return "\n".join(lines)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="태그 체계 최종 검토 리포트 생성")
    ap.add_argument("input", help="태깅 결과 (.json / .xlsx / .csv)")
    ap.add_argument("-o", "--output", required=True, help="리포트 파일 (.md)")
    ap.add_argument("--rules", default=os.path.join(here, "tag_rules.json"))
    args = ap.parse_args()

    dictionary_tags = None
    if os.path.exists(args.rules):
        with open(args.rules, encoding="utf-8") as fh:
            dictionary_tags = [r["tag"] for r in json.load(fh)["tags"]]

    report = build_report(load_records(args.input), dictionary_tags)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(report)
    print("리포트 저장: %s" % args.output)


if __name__ == "__main__":
    main()
