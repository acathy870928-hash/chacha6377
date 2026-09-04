"""벨루가 검증용 상품 27개 선정.

규칙
1. 1차 지표 월납실적(내림차순), 동률 시 계약건수.
2. 생보·손보 각각의 모든 보종에서 실적 1위 상품을 우선 확보(보종별 최소 1개).
3. 남은 자리는 실적순으로 채우되, 같은 판매사×보종 조합은 1개만(유사 약관 중복 방지),
   한 보종은 최대 MAX_PER_LINE개까지만(종신·연금 편중 방지).
"""
from __future__ import annotations
import sys
import openpyxl
from classify import sector, line, simplified

TARGET = 27          # 선정 개수
MAX_PER_LINE = 3     # 한 보종에서 뽑을 최대 개수


def load(path="data/판매실적_상품목록.xlsx"):
    wb = openpyxl.load_workbook(path, data_only=True)
    rows = []
    for no, ins, name, n, _, prem, _ in wb.active.iter_rows(min_row=2, values_only=True):
        if not no:
            continue
        rows.append({"no": no, "insurer": ins, "name": name.strip(), "count": n, "premium": prem,
                     "sector": sector(ins), "line": line(name, ins), "simplified": simplified(name)})
    rows.sort(key=lambda r: (-r["premium"], -r["count"]))
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
    return rows


def select(rows, target=TARGET):
    chosen, used_pair, reasons = [], set(), {}
    groups = sorted({(r["sector"], r["line"]) for r in rows})
    for g in groups:  # 보종별 1위
        top = next(r for r in rows if (r["sector"], r["line"]) == g)
        chosen.append(top); used_pair.add((top["insurer"], top["line"]))
        reasons[top["no"]] = f"{g[0]} {g[1]} 보종 실적 1위 (필수 확보)"
    for r in rows:  # 잔여 실적순 + 판매사×보종 중복 배제
        if len(chosen) >= target:
            break
        if r in chosen or (r["insurer"], r["line"]) in used_pair:
            continue
        if sum(1 for c in chosen if (c["sector"], c["line"]) == (r["sector"], r["line"])) >= MAX_PER_LINE:
            continue
        chosen.append(r); used_pair.add((r["insurer"], r["line"]))
        reasons[r["no"]] = f"전체 실적 {r['rank']}위 (판매사×보종 중복 없음, 보종당 {MAX_PER_LINE}개 이내)"
    chosen.sort(key=lambda r: r["rank"])
    if len(chosen) != target:
        raise SystemExit(f"선정 수 {len(chosen)} != {target}")
    # 보종별 대체 후보(차순위 2개)
    alts = {}
    for r in chosen:
        g = (r["sector"], r["line"])
        alts[r["no"]] = [x for x in rows if (r["sector"], r["line"]) == (x["sector"], x["line"]) and x not in chosen][:2]
    return chosen, reasons, alts


if __name__ == "__main__":
    TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET
    rows = load()
    chosen, reasons, alts = select(rows, TARGET)
    for i, r in enumerate(chosen, 1):
        print(f"{i:>2} #{r['no']:<3} {r['sector'][:2]} {r['line']:<12} {r['insurer']:<10} {r['name']:<40} {r['count']:>3}건 {r['premium']:>10,}  | {reasons[r['no']]}")
    import collections
    print(collections.Counter(r["sector"] for r in chosen))
    print(collections.Counter(r["insurer"] for r in chosen).most_common())
