# -*- coding: utf-8 -*-
"""현재 판매 상품 데이터(CSV)와 임의의 상품명 문자열을 매칭한다.

판정 단계:
  EXACT   상품명 완전일치            → 현재 판매 상품으로 확정 (Tier A)
  VARIANT 상품군+개정코드 일치       → 종/플랜만 불명확 (Tier A/B)
  GROUP   상품군만 일치              → 상품군은 판매중, 문서 시점 확인 필요 (Tier B)
  NONE    미매칭                     → 현재 판매 여부 확인 불가 (Tier C)
"""
import csv
import re
import unicodedata
from collections import defaultdict

# 보험사 별칭: 문서에서 쓰이는 표기 → CSV 표기
INSURER_ALIASES = {
    "DB손해보험": "DB손보", "디비손보": "DB손보", "디비손해보험": "DB손보",
    "KB손해보험": "KB손보", "메리츠": "메리츠화재", "현대해상화재보험": "현대해상",
    "삼성화재해상보험": "삼성화재", "한화손해보험": "한화손보",
    "롯데손해보험": "롯데손보", "농협손해보험": "농협손보", "NH농협손보": "농협손보",
    "흥국화재해상보험": "흥국화재", "하나손해보험": "하나손보",
    "신한라이프": "신한라이프생명", "KB라이프": "KB라이프생명",
    "NH농협생명보험": "NH농협생명", "DB생명보험": "DB생명",
}

# 단독 매칭을 금지할 일반명사형 상품명 길이 기준(정규화 후 글자수)
GENERIC_LEN = 8

_ROMAN = {"Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5", "I": "1", "II": "2", "III": "3"}
_REV = re.compile(r"2[0-9](?:0[1-9]|1[0-2])")


def normalize(text):
    """비교용 정규화: 무배당 표기·공백·구두점 제거, 전각/로마숫자 통일."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    # NFKC가 Ⅲ을 III로 풀어놓으므로 긴 표기부터 치환해야 III→111이 되지 않는다
    for k in sorted(_ROMAN, key=len, reverse=True):
        t = t.replace(k, _ROMAN[k])
    t = re.sub(r"\(\s*무\s*\)|\(\s*무배당\s*\)|무배당", "", t)
    t = re.sub(r"[\s\-_·‧·,./'\"’“”]", "", t)
    return t.upper()


def split_name(name):
    """상품명 → (상품군 base, 개정코드, 종/플랜 variant)."""
    rev = _REV.search(name)
    rev = rev.group(0) if rev else ""
    variants = re.findall(r"\(([^()]*)\)", name)
    variants = [v for v in variants if v.strip() not in ("무", "무배당")]
    base = re.sub(r"\([^()]*\)", "", name)
    base = _REV.sub("", base)
    return normalize(base), rev, normalize("|".join(variants))


class ProductIndex:
    def __init__(self, csv_path):
        self.rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
        self.by_exact = defaultdict(list)      # norm(상품명) -> rows
        self.by_base_rev = defaultdict(list)   # (base, rev) -> rows
        self.by_base = defaultdict(list)       # base -> rows
        self.base_owners = defaultdict(set)    # base -> {보험회사}
        for r in self.rows:
            base, rev, _ = split_name(r["상품명"])
            r["_base"], r["_rev"] = base, rev
            self.by_exact[normalize(r["상품명"])].append(r)
            self.by_base_rev[(base, rev)].append(r)
            self.by_base[base].append(r)
            self.base_owners[base].add(r["보험회사"])
        # 긴 쪽부터 검사해야 최장일치가 보장된다
        self.bases_desc = sorted(self.by_base, key=len, reverse=True)
        self.fulls_desc = sorted((k for k in self.by_exact if len(k) > GENERIC_LEN),
                                 key=len, reverse=True)
        self.기준일 = self.rows[0]["기준일"] if self.rows else ""

    def _resolve_insurer(self, text):
        norm = normalize(text)
        for alias, canon in INSURER_ALIASES.items():
            if normalize(alias) in norm:
                return canon
        for company in {r["보험회사"] for r in self.rows}:
            if normalize(company) in norm:
                return company
        return None

    def match(self, text, insurer=None):
        """문서 제목/본문 조각에서 현재 판매 상품을 찾는다."""
        insurer = insurer or self._resolve_insurer(text)
        norm = normalize(text)
        base_q, rev_q, _ = split_name(text)

        def scope(rows):
            return [r for r in rows if not insurer or r["보험회사"] == insurer]

        # 1) 상품명 완전일치
        hit = scope(self.by_exact.get(norm, []))
        if hit:
            return self._result("EXACT", hit, insurer)

        # 1-2) 상품명이 문장 안에 포함된 경우(최장일치)
        #      "DB손보 (무)참좋은암보험2607(CM) 안내" 처럼 앞뒤에 다른 말이 붙는 형태
        for full in self.fulls_desc:
            if full not in norm:
                continue
            hit = scope(self.by_exact[full])
            if hit:
                return self._result("EXACT", hit, insurer)

        # 2) 상품군 + 개정코드 일치
        if base_q and rev_q:
            hit = scope(self.by_base_rev.get((base_q, rev_q), []))
            if hit:
                return self._result("VARIANT", hit, insurer)

        # 3) 상품군 최장일치 (일반명사형은 보험사명 동반 필수)
        for base in self.bases_desc:
            # norm은 원문 그대로, base_q는 괄호·개정코드를 뗀 형태.
            # "…간편건강보험 2604 4종"처럼 개정코드가 상품명 중간에 끼는 표기는 base_q에서만 걸린다.
            if not base or (base not in norm and base not in base_q):
                continue
            if len(base) <= GENERIC_LEN and not insurer:
                continue                      # '건강보험' 단독 매칭 차단
            if len(self.base_owners[base]) > 1 and not insurer:
                continue                      # 여러 보험사 공통 명칭
            hit = scope(self.by_base[base])
            if not hit:
                continue
            revs = sorted({r["_rev"] for r in hit if r["_rev"]})
            if rev_q and revs and rev_q not in revs:
                # 문서 개정코드가 판매중 목록에 없음 → 구버전 자료
                return self._result("GROUP", hit, insurer, note=f"문서 개정코드 {rev_q}는 판매중 목록에 없음(판매중: {', '.join(revs)})")
            return self._result("VARIANT" if rev_q else "GROUP", hit, insurer)

        return {"level": "NONE", "tier": "C", "matches": [], "insurer": insurer,
                "기준일": self.기준일, "note": "현재 판매 상품 데이터에서 확인되지 않음"}

    def _result(self, level, rows, insurer, note=""):
        tier = {"EXACT": "A", "VARIANT": "A", "GROUP": "B"}[level]
        if note:
            tier = "B"
        return {
            "level": level, "tier": tier, "insurer": insurer,
            "matches": [{"상품명": r["상품명"], "보험회사": r["보험회사"],
                         "상품분류": r["상품분류"], "판매채널": r["판매채널"],
                         "상품ID": r["상품ID"]} for r in rows[:5]],
            "match_count": len(rows), "기준일": self.기준일, "note": note,
        }
