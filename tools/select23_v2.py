# -*- coding: utf-8 -*-
"""판매실적 순으로 생보 10개사 + 손보 13개사를 보종이 겹치지 않게 1개씩 뽑는다.

- 손보사는 데이터에 정확히 13개사뿐이므로 전 손보사가 1개씩 들어간다.
- 생보사는 21개사 중 실적 상위 10개사가 들어간다.
- 보종은 전체(생보+손보)에서 겹치지 않는 것을 1순위로 하고, 자리가 모자라면
  가장 적게 쓰인 보종부터 재사용한다.
"""
import re, sys
from pathlib import Path

SONBO = {"메리츠화재","현대해상","삼성화재","DB손보","KB손보","한화손보","롯데손보",
         "흥국화재","하나손보","NH농협손보","라이나손보","AIG손보","예별손보"}

RULES = [
    ("펫보험",       r"펫|반려|댕댕|의기냥냥|위풍|퍼민트"),
    ("치아보험",     r"치아|덴탈"),
    ("어린이·자녀",  r"어린이|자녀|아이러브|아이\(I\)러브|쑥쑥|꿈나무|금쪽|도담|슈퍼스타|청춘어람|우리아이|뉴키즈|키즈|아이맘|우리아이"),
    ("치매·간병",    r"치매|간병|요양"),
    ("실손의료비",   r"실손"),
    ("변액·연금",    r"변액|연금"),
    ("종신·사망",    r"종신|정기보험"),
    ("암보험",       r"암보험|암치료|암생활비"),
    ("운전자·상해",  r"운전자|오토바이|바이크|상해|라이더"),
    ("재물·비즈니스", r"재산종합|재물|비즈니스|BOP|비즈|성공예감|성공마스터|Owner|기업보장|단체"),
    ("가정·생활종합", r"화재|가정종합|가정생활|온가족|홈앤|우리집|생활종합|한아름|M-House|리치하우스"),
    ("간편건강",     r"건강|보장|보험"),
    ("건강보험",     r"건강"),
    ("종합·통합보장", r"종합|통합|보장보험"),
]
COMPANY = ["삼성화재","현대해상","흥국화재","메리츠화재","롯데손보","한화손보","DB손보","KB손보",
           "NH농협손보","하나손보","라이나손보","AIG손보","예별손보","삼성생명","한화생명","교보생명",
           "동양생명","흥국생명","신한라이프","KB라이프","DB생명","미래에셋생명","라이나생명","ABL생명",
           "KDB생명","NH농협생명","푸본현대생명","메트라이프","iM라이프","IBK연금보험","하나생명",
           "BNP파리바카디프생명","CHUBB","AIA생명","한화","삼성","흥국","메리츠","현대"]
SIMPLE = r"간편|유병|경증|고당지"

def classify(name):
    n = name
    for t in COMPANY:
        n = n.replace(t, " ")
    simple = re.search(SIMPLE, n) is not None
    for bucket, pat in RULES:
        if not re.search(pat, n):
            continue
        if bucket == "실손의료비" and simple:
            return "유병자실손"
        if bucket == "간편건강" and not simple:
            continue
        return bucket
    return "간편건강" if simple else "기타"

# 단체·기업·경영인 상품은 개인 고객이 약관을 묻지 않으므로 검증 대상에서 뺀다.
B2B = re.compile(r"단체|기업|경영인|교직원|재난배상책임")

rows = []
for line in Path("input/sales666.tsv").read_text(encoding="utf-8").splitlines():
    r, ins, prod, cnt, amt = line.split("\t")
    if B2B.search(prod):
        continue
    rows.append({"rank": int(r), "insurer": ins, "product": prod,
                 "count": int(cnt), "amount": int(amt),
                 "group": "손보" if ins in SONBO else "생보",
                 "bucket": classify(prod)})

QUOTA = {"생보": 10, "손보": 13}
picked, used_ins, used_bucket = [], set(), {}
filled = {"생보": 0, "손보": 0}

def take(r):
    picked.append(r)
    used_ins.add(r["insurer"])
    used_bucket[r["bucket"]] = used_bucket.get(r["bucket"], 0) + 1
    filled[r["group"]] += 1

# 1차: 취급 보험사가 적은 보종부터 대표를 확보한다.
# 실적 순으로 그냥 내려가면 펫보험처럼 취급사가 적은 보종이 반드시 탈락한다.
buckets = {}
for r in rows:
    buckets.setdefault(r["bucket"], []).append(r)
scarcity = sorted(buckets, key=lambda b: (len({x["insurer"] for x in buckets[b]}),
                                          buckets[b][0]["rank"]))
for b in scarcity:
    if b == "기타":
        continue
    for r in buckets[b]:
        if filled[r["group"]] >= QUOTA[r["group"]] or r["insurer"] in used_ins:
            continue
        if r["bucket"] in used_bucket:
            continue
        take(r)
        break

# 2차: 남은 자리는 아직 안 쓰인 보험사 중에서, 가장 적게 쓰인 보종을 우선해 채운다.
while filled["생보"] < QUOTA["생보"] or filled["손보"] < QUOTA["손보"]:
    best = None
    for r in rows:
        if filled[r["group"]] >= QUOTA[r["group"]] or r["insurer"] in used_ins:
            continue
        # '기타'(저축성 등 보장 내용이 없는 상품)는 마지막에만 쓴다.
        pen = 99 if r["bucket"] == "기타" else used_bucket.get(r["bucket"], 0)
        key = (pen, r["rank"])
        if best is None or key < best[0]:
            best = (key, r)
    if best is None:
        break
    take(best[1])

picked.sort(key=lambda r: r["rank"])
for grp in ("생보", "손보"):
    sel = [r for r in picked if r["group"] == grp]
    print(f'\n=== {grp} {len(sel)}개 ===')
    print(f'{"순위":>4} {"보종":<12} {"보험사":<12} {"상품명":<44} {"건수":>5} {"월납":>12}')
    for r in sel:
        print(f'{r["rank"]:>4} {r["bucket"]:<12} {r["insurer"]:<12} {r["product"][:42]:<44} {r["count"]:>5} {r["amount"]:>12,}')

cov = {}
for r in picked:
    cov[r["bucket"]] = cov.get(r["bucket"], 0) + 1
ta = sum(r["amount"] for r in rows); tc = sum(r["count"] for r in rows)
print(f'\n총 {len(picked)}개 | 보종 {len(cov)}종 | 보험사 {len({r["insurer"] for r in picked})}사')
print("보종별:", dict(sorted(cov.items(), key=lambda x: -x[1])))
print("커버율: 실적 %.1f%% / 건수 %.1f%%" % (
    100*sum(r["amount"] for r in picked)/ta, 100*sum(r["count"] for r in picked)/tc))
