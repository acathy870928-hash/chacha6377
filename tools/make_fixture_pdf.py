#!/usr/bin/env python3
"""
분할 스크립트 검증용 합성 PDF 생성기 (테스트 전용, 실제 약관 내용 아님).

실제 [별표 15] PDF 의 구조적 특징을 흉내낸다:
- 1쪽: 7개 약관 제목이 모두 나열된 표지/목차 (분할 시 어느 약관에도 속하지 않아야 함)
- 각 약관의 첫 쪽 상단에 제목, 이후 쪽에는 머리글로 약관명이 반복됨
- 실손의료보험 안에 "급여/비급여 실손의료비 특별약관" 소제목 존재
- "해외여행 실손의료보험" 은 "실손의료보험" 제목을 부분 문자열로 포함
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf", None),
    ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0),
]

# 실제 별표 15 수록 순서(생명 → 질병·상해 → 화재 → 자동차 → 배상책임 → 실손 → 해외여행실손)를 따른다.
# (쪽수는 임의)
LAYOUT = [
    ("생명보험 표준약관", 4, []),
    ("질병·상해보험 표준약관", 3, []),
    ("화재보험 표준약관", 2, []),
    ("자동차보험 표준약관", 5, []),
    ("배상책임보험 표준약관", 2, []),
    ("실손의료보험 표준약관", 6, [(2, "급여 실손의료비 특별약관"), (4, "비급여 실손의료비 특별약관")]),
    ("해외여행 실손의료보험 표준약관", 4, [(1, "급여 해외여행실손의료비 특별약관"), (3, "비급여 해외여행실손의료비 특별약관")]),
]


def register_font() -> str:
    for path, idx in FONT_CANDIDATES:
        if Path(path).exists():
            kw = {"subfontIndex": idx} if idx is not None else {}
            pdfmetrics.registerFont(TTFont("KR", path, **kw))
            return "KR"
    raise SystemExit("한글 폰트를 찾지 못했습니다")


def build(out: Path) -> list[tuple[str, int, int]]:
    """PDF 를 만들고 (제목, 시작쪽, 끝쪽) 1-based 목록을 돌려준다."""
    font = register_font()
    c = canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    # 표지/목차
    c.setFont(font, 16)
    c.drawString(60, h - 80, "[별표 15] 표준약관 (제7-64조 관련)")
    c.setFont(font, 11)
    for i, (title, _, _) in enumerate(LAYOUT):
        c.drawString(80, h - 130 - 20 * i, f"{i + 1}. {title}")
    c.showPage()

    page = 2
    spans = []
    for title, n, subs in LAYOUT:
        start = page
        sub_at = dict(subs)
        for k in range(n):
            c.setFont(font, 9)
            c.drawString(60, h - 40, f"보험업감독업무시행세칙 [별표 15]  {title}")  # 머리글
            y = h - 90
            if k == 0:
                c.setFont(font, 18)
                c.drawString(60, y, title)
                y -= 40
            if k in sub_at:
                c.setFont(font, 14)
                c.drawString(60, y, sub_at[k])
                y -= 30
            c.setFont(font, 10)
            c.drawString(60, y, f"제{k + 1}조(테스트) 이 페이지는 {title} 의 {k + 1}번째 쪽(전체 {page}쪽)입니다.")
            c.drawString(60, 40, f"- {page} -")
            c.showPage()
            page += 1
        spans.append((title, start, page - 1))
    c.save()
    return spans


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "fixture_byulpyo15.pdf")
    for title, s, e in build(out):
        print(f"{title:<20} {s}-{e}")
    print(f"→ {out}")
