"""판매실적 목록을 보험구분(생보/손보)·보종으로 분류한다."""
from __future__ import annotations
import re

LIFE = {"iM라이프", "메트라이프", "푸본현대생명", "한화생명", "동양생명", "BNP파리바카디프생명", "삼성생명", "KDB생명",
        "교보생명", "IBK연금보험", "흥국생명", "신한라이프", "KB라이프", "DB생명", "미래에셋생명", "CHUBB", "라이나생명",
        "ABL생명", "NH농협생명"}
NONLIFE = {"DB손보", "KB손보", "메리츠화재", "현대해상", "삼성화재", "한화손보", "NH농협손보", "롯데손보", "흥국화재",
           "하나손보", "라이나손보"}

# (보종, 정규식)  위에서부터 먼저 맞는 것을 택한다
RULES = [
    ("실손의료보험", r"실손"),
    ("운전자보험", r"운전자"),
    ("펫보험", r"펫|반려"),
    ("치매간병보험", r"치매|간병|요양"),
    ("치아보험", r"치아"),
    ("자녀·어린이보험", r"자녀|어린이|우리아이|꿈나무"),
    ("재물·화재·가정종합보험", r"재물|재산종합|화재플러스|화재보험|홈앤|주택|우리집|가정종합|BOP"),
    ("연금저축(손보)", r"연금저축손해"),
    ("연금·변액보험", r"연금|변액"),
    ("종신보험", r"종신"),
    ("암보험", r"암보험"),
    ("상해보험", r"상해보험|통합상해"),
    ("건강·종합·보장보험", r"건강|종합|보장|통합|새로고침|마이핏|보험"),
]


def sector(insurer: str) -> str:
    if insurer in LIFE:
        return "생명보험"
    if insurer in NONLIFE:
        return "손해보험"
    raise KeyError(insurer)


def line(name: str, insurer: str = "") -> str:
    n = name.replace(" ", "")
    if insurer:
        n = n.replace(insurer.replace(" ", ""), "")  # 상품명 속 판매사명(예: 삼성화재)이 규칙에 걸리지 않도록 제거
    for label, pat in RULES:
        if re.search(pat, n):
            return label
    return "건강·종합·보장보험"  # 키워드가 없는 장기 간편보험류(예: 삼성화재 새로고침)는 건강·종합으로 본다


def simplified(name: str) -> bool:
    return bool(re.search(r"간편|유병|\d\.\s*N\.\s*\d|\d\.\d+\.\d|\d{3,4}(형|간편)|3N5|5N5|311", name))
