# -*- coding: utf-8 -*-
"""판매 실적 시트에서 약관 검증용 상품 23개를 선정한다.

선정 원칙
1. 보종(15개 버킷)을 먼저 덮는다  - 표준약관 7종이 못 잡는 상품 고유 조항을 검증하기 위함.
2. 한 보험사에서 최대 2개까지만 뽑는다 - 특정 회사 약관 문체에 과적합되는 것을 막는다.
3. 같은 보종 안에서는 실적/건수 종합 점수가 높은 순으로 고른다.
4. 보종을 다 덮고 남은 자리는 종합 점수 상위로 채운다.
"""
import argparse, json, re, sys
from pathlib import Path

import openpyxl

# (버킷명, 키워드 정규식). 위에서부터 먼저 맞는 것을 채택하므로 좁은 규칙을 위에 둔다.
RULES = [
    ("펫보험",       r"펫|반려|댕댕|의기냥냥|위풍"),
    ("치아보험",     r"치아"),
    ("어린이·자녀",  r"어린이|자녀|아이러브|쑥쑥|꿈나무|금쪽|도담|슈퍼스타|청춘어람"),
    ("치매·간병",    r"치매|간병|요양"),
    ("유병자실손",   r"실손"),          # 앞단에서 간편·유병 여부를 먼저 가른다
    ("실손의료비",   r"실손"),
    ("변액·연금",    r"변액|연금"),
    ("종신·사망",    r"종신"),
    ("암보험",       r"암보험"),
    ("운전자·상해",  r"운전자|오토바이|상해"),
    ("재물·비즈니스", r"재산종합|재물|비즈니스|BOP|비즈|성공예감|Owner"),
    ("가정·생활종합", r"화재|가정종합|온가족|홈앤|우리집|생활종합|한아름"),
    ("간편건강",     r"건강|보장|보험"),  # 앞단에서 간편 고지 여부를 먼저 가른다
    ("건강보험",     r"건강"),
    ("종합·통합보장", r"종합|통합|보장보험"),
]

# 상품명에 섞여 있는 회사명이 보종 키워드로 오인식되는 것을 막는다.
# (예: "삼성화재 간편보험 새로고침" 의 '화재' 가 화재보험으로 잡히던 문제)
COMPANY_TOKENS = [
    "삼성화재", "현대해상", "흥국화재", "메리츠화재", "롯데손보", "한화손보", "DB손보",
    "KB손보", "NH농협손보", "하나손보", "라이나손보", "삼성생명", "한화생명", "교보생명",
    "동양생명", "흥국생명", "신한라이프", "KB라이프", "DB생명", "미래에셋생명", "라이나생명",
    "ABL생명", "KDB생명", "NH농협생명", "푸본현대생명", "메트라이프", "iM라이프",
    "IBK연금보험", "BNP파리바카디프생명", "CHUBB", "한화", "삼성", "흥국", "메리츠",
]

SIMPLE_ISSUE = r"간편|유병|경증|고당지|간편가입|간편고지"   # 간편고지(유병자) 신호

def classify(name: str) -> str:
    """상품명으로 보종을 판정한다. 회사명을 먼저 지우고 좁은 규칙부터 적용한다."""
    n = name
    for tok in COMPANY_TOKENS:
        n = n.replace(tok, " ")
    simple = re.search(SIMPLE_ISSUE, n) is not None
    for bucket, pat in RULES:
        if not re.search(pat, n):
            continue
        if bucket == "유병자실손":
            if not simple:
                continue                      # 표준 실손은 아래 "실손의료비" 로 내려보낸다
        elif bucket == "실손의료비":
            pass
        elif bucket == "간편건강":
            if not simple:
                continue                      # 간편고지 신호가 없으면 일반 건강/종합으로
        return bucket
    # "간편365 당당한 새로고침100세" 처럼 상품명에 '건강/보험' 단어가 없는 간편고지 상품
    return "간편건강" if simple else "기타"

def load(path: Path):
    ws = openpyxl.load_workbook(path, data_only=True)["Sheet1"]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] in (None, ""):
            continue
        rows.append({
            "rank_amt": int(r[0]),
            "insurer": str(r[1]).strip(),
            "product": str(r[2]).strip(),
            "count": int(r[3]),
            "amount": int(r[5]),
            "bucket": classify(str(r[2])),
        })
    return rows

def score(rows):
    """실적과 건수를 각각 최대값 대비로 정규화해 합산한다.

    실적만 쓰면 2건짜리 고액 종신이 위로 오고, 건수만 쓰면 소액 상품이 위로 온다.
    약관 질문은 가입 건수를 따라오므로 건수에 더 큰 가중치(0.6)를 준다.
    """
    max_a = max(r["amount"] for r in rows)
    max_c = max(r["count"] for r in rows)
    for r in rows:
        r["score"] = round(0.4 * r["amount"] / max_a + 0.6 * r["count"] / max_c, 4)
    return rows

def select(rows, total=23, per_insurer=2):
    rows = sorted(rows, key=lambda r: -r["score"])
    picked, used = [], {}

    def take(r, why):
        if used.get(r["insurer"], 0) >= per_insurer:
            return False
        r = dict(r, reason=why)
        picked.append(r)
        used[r["insurer"]] = used.get(r["insurer"], 0) + 1
        return True

    # 1단계: 보종 커버리지. 버킷은 그 버킷 최고 점수 순으로 처리한다.
    buckets = {}
    for r in rows:
        buckets.setdefault(r["bucket"], []).append(r)
    order = sorted(buckets, key=lambda b: -buckets[b][0]["score"])
    for b in order:
        if len(picked) >= total:
            break
        for r in buckets[b]:
            if take(r, f"보종 대표: {b}"):
                break

    # 2단계: 남은 자리는 종합 점수 상위로 채운다.
    ids = {(r["insurer"], r["product"]) for r in picked}
    for r in rows:
        if len(picked) >= total:
            break
        if (r["insurer"], r["product"]) in ids:
            continue
        take(r, "판매 상위 보강")

    return sorted(picked, key=lambda r: -r["score"])

def select_spread(rows, total=23, per_insurer=1):
    """보험사 1사 1상품을 지키면서 보종을 최대한 고르게 뽑는다.

    점수 상위부터 그냥 내려가면 펫·암처럼 취급사가 적은 보종이 반드시 탈락한다.
    (펫보험은 KB손보·삼성화재·DB손보 3사, 암보험은 메리츠·한화생명·흥국화재 3사에만
    있는데, 이 회사들은 실적 상위라 다른 보종에 먼저 쓰이기 때문이다.)
    그래서 취급 보험사가 적은 보종부터 자리를 잡고, 남는 자리를 점수순으로 채운다.
    """
    rows = sorted(rows, key=lambda r: -r["score"])
    picked, used_ins = [], {}
    per_bucket = {}

    def take(r, why):
        if used_ins.get(r["insurer"], 0) >= per_insurer:
            return False
        picked.append(dict(r, reason=why))
        used_ins[r["insurer"]] = used_ins.get(r["insurer"], 0) + 1
        per_bucket[r["bucket"]] = per_bucket.get(r["bucket"], 0) + 1
        return True

    buckets = {}
    for r in rows:
        buckets.setdefault(r["bucket"], []).append(r)

    # 1단계: 취급 보험사가 적은 보종(희소 보종)부터 대표 1개씩 확보한다.
    scarcity = sorted(buckets, key=lambda b: (len({r["insurer"] for r in buckets[b]}), -buckets[b][0]["score"]))
    for b in scarcity:
        if len(picked) >= total:
            break
        for r in buckets[b]:
            if take(r, f"보종 대표: {b}"):
                break

    # 2단계: 남은 자리는 '지금까지 적게 뽑힌 보종'을 우선하되 그 안에서는 점수순으로 채운다.
    while len(picked) < total:
        cand = None
        for r in rows:
            if used_ins.get(r["insurer"], 0) >= per_insurer:
                continue
            key = (per_bucket.get(r["bucket"], 0), -r["score"])
            if cand is None or key < cand[0]:
                cand = (key, r)
        if cand is None:
            break                      # 남은 보험사가 없다
        take(cand[1], "판매 상위 보강")

    return sorted(picked, key=lambda r: -r["score"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("-n", "--total", type=int, default=23)
    ap.add_argument("--per-insurer", type=int, default=2)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--audit", action="store_true", help="보종 분류 결과 전체를 출력")
    ap.add_argument("--spread", action="store_true", help="1사 1상품 + 보종 균등 분산")
    a = ap.parse_args()

    rows = score(load(a.source))
    if a.audit:
        for r in sorted(rows, key=lambda r: (r["bucket"], -r["score"])):
            print(f'{r["bucket"]:<12} {r["insurer"]:<12} {r["product"][:44]}')
        return

    picker = select_spread if a.spread else select
    picked = picker(rows, a.total, a.per_insurer)
    print(f'{"#":>2}  {"보종":<12} {"보험사":<12} {"상품명":<46} {"건수":>4} {"월납":>10}')
    for i, r in enumerate(picked, 1):
        print(f'{i:>2}  {r["bucket"]:<12} {r["insurer"]:<12} {r["product"][:44]:<46} {r["count"]:>4} {r["amount"]:>10,}')

    cov = {}
    for r in picked:
        cov[r["bucket"]] = cov.get(r["bucket"], 0) + 1
    print("\n보종 커버리지:", len(cov), "종 /", dict(sorted(cov.items(), key=lambda x: -x[1])))
    ins = {}
    for r in picked:
        ins[r["insurer"]] = ins.get(r["insurer"], 0) + 1
    print("보험사:", len(ins), "사 /", dict(sorted(ins.items(), key=lambda x: -x[1])))
    print("전체 실적 대비 커버율: %.1f%%" % (100 * sum(r["amount"] for r in picked) / sum(r["amount"] for r in rows)))
    print("전체 건수 대비 커버율: %.1f%%" % (100 * sum(r["count"] for r in picked) / sum(r["count"] for r in rows)))

    if a.json:
        a.json.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
