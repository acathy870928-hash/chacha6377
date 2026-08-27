#!/usr/bin/env python3
"""docs/insurance_ai_product_rules.md -> PDF (Korean, reportlab)."""
import csv
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "docs", "insurance_ai_product_rules.md")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "Insurance_AI_보험상품_운영규칙_v1.1.pdf")

FONT_DIR = "/usr/share/fonts/truetype/nanum"
pdfmetrics.registerFont(TTFont("Nanum", os.path.join(FONT_DIR, "NanumBarunGothic.ttf")))
pdfmetrics.registerFont(TTFont("Nanum-Bold", os.path.join(FONT_DIR, "NanumBarunGothicBold.ttf")))
pdfmetrics.registerFont(TTFont("NanumMono", os.path.join(FONT_DIR, "NanumGothicCoding.ttf")))
pdfmetrics.registerFontFamily("Nanum", normal="Nanum", bold="Nanum-Bold",
                              italic="Nanum", boldItalic="Nanum-Bold")

NAVY = colors.HexColor("#1f3864")
ACCENT = colors.HexColor("#2e75b6")
RULE = colors.HexColor("#c9d3e4")
HEAD_BG = colors.HexColor("#eaf0f8")
ZEBRA = colors.HexColor("#f7f9fc")
BODY_TXT = colors.HexColor("#222222")

S = {
    "title": ParagraphStyle("title", fontName="Nanum-Bold", fontSize=25, leading=34,
                            textColor=NAVY, alignment=TA_CENTER),
    "subtitle": ParagraphStyle("subtitle", fontName="Nanum", fontSize=13, leading=20,
                               textColor=ACCENT, alignment=TA_CENTER),
    "cover_meta": ParagraphStyle("cover_meta", fontName="Nanum", fontSize=10.5, leading=18,
                                 textColor=colors.HexColor("#555555"), alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", fontName="Nanum-Bold", fontSize=15.5, leading=22,
                         textColor=colors.white, backColor=NAVY,
                         borderPadding=(6, 8, 6, 8), spaceBefore=16, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Nanum-Bold", fontSize=12.5, leading=18,
                         textColor=NAVY, spaceBefore=12, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName="Nanum-Bold", fontSize=11, leading=16,
                         textColor=ACCENT, spaceBefore=9, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Nanum", fontSize=9.8, leading=16,
                           textColor=BODY_TXT, alignment=TA_LEFT, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", fontName="Nanum", fontSize=9.8, leading=16,
                             textColor=BODY_TXT, leftIndent=12, bulletIndent=2, spaceAfter=2.5),
    "quote": ParagraphStyle("quote", fontName="Nanum", fontSize=9.8, leading=17,
                            textColor=colors.HexColor("#1a1a1a"), backColor=colors.HexColor("#f2f6fb"),
                            borderColor=ACCENT, borderWidth=0, leftIndent=10, rightIndent=8,
                            borderPadding=(8, 9, 8, 9), spaceBefore=4, spaceAfter=8),
    "th": ParagraphStyle("th", fontName="Nanum-Bold", fontSize=9.2, leading=14,
                         textColor=NAVY, alignment=TA_CENTER),
    "td": ParagraphStyle("td", fontName="Nanum", fontSize=8.8, leading=13.5, textColor=BODY_TXT),
    "td_c": ParagraphStyle("td_c", fontName="Nanum", fontSize=8.8, leading=13.5,
                           textColor=BODY_TXT, alignment=TA_CENTER),
}


def inline(text):
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font face="NanumMono" size="8.8" backColor="#eef1f5">\1</font>', text)
    return text


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def make_table(header, rows, widths=None, center_cols=()):
    data = [[Paragraph(inline(c), S["th"]) for c in header]]
    for r in rows:
        data.append([Paragraph(inline(c), S["td_c"] if i in center_cols else S["td"])
                     for i, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(2, len(data), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
    t.setStyle(TableStyle(style))
    return t


def csv_table(rel_path, avail):
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    keep = [0, 1, 3, 4, 5]
    header = [header[i] for i in keep]
    body = [[r[i] for i in keep] for r in body]
    w = [avail * f for f in (0.07, 0.53, 0.11, 0.16, 0.13)]
    return make_table(header, body, w, center_cols=(0, 2, 3, 4))


def build():
    with open(SRC, encoding="utf-8") as fh:
        raw = fh.read()

    meta = {}
    if raw.startswith("---"):
        fm, raw = raw.split("---", 2)[1:]
        for ln in fm.strip().splitlines():
            k, _, v = ln.partition(":")
            meta[k.strip()] = v.strip()

    doc = BaseDocTemplate(OUT, pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=20 * mm, bottomMargin=18 * mm,
                          title=meta.get("title", ""), author="Insurance AI 운영")
    avail = doc.width

    def deco(canvas, d):
        canvas.saveState()
        if canvas.getPageNumber() > 1:
            canvas.setFont("Nanum", 7.6)
            canvas.setFillColor(colors.HexColor("#8894a8"))
            canvas.drawString(d.leftMargin, A4[1] - 13 * mm,
                              "%s  %s" % (meta.get("title", ""), meta.get("version", "")))
            canvas.setStrokeColor(RULE)
            canvas.setLineWidth(0.5)
            canvas.line(d.leftMargin, A4[1] - 15 * mm, A4[0] - d.rightMargin, A4[1] - 15 * mm)
            canvas.drawCentredString(A4[0] / 2, 11 * mm, "- %d -" % canvas.getPageNumber())
        canvas.restoreState()

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=deco)])

    F = []
    # ---- cover ----
    F += [Spacer(1, 52 * mm),
          Paragraph(meta.get("title", ""), S["title"]),
          Spacer(1, 5 * mm),
          Paragraph(meta.get("subtitle", ""), S["subtitle"]),
          Spacer(1, 10 * mm)]
    line = Table([[""]], colWidths=[46 * mm], rowHeights=[0.1])
    line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, ACCENT)]))
    line.hAlign = "CENTER"
    F += [line, Spacer(1, 10 * mm),
          Paragraph("버전 %s" % meta.get("version", ""), S["cover_meta"]),
          Paragraph("작성일 %s" % meta.get("date", ""), S["cover_meta"]),
          PageBreak()]

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()

        if not s:
            i += 1
            continue

        m = re.match(r"^<!--\s*TABLE:(.+?)\s*-->$", s)
        if m:
            F.append(csv_table(m.group(1), avail))
            i += 1
            continue

        if s.startswith("### "):
            F.append(Paragraph(inline(s[4:]), S["h3"]))
        elif s.startswith("## "):
            F.append(Paragraph(inline(s[3:]), S["h2"]))
        elif s.startswith("# "):
            F.append(Paragraph(inline(s[2:]), S["h1"]))
        elif s.startswith("> "):
            F.append(Paragraph(inline(s[2:]), S["quote"]))
        elif s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            header = split_row(block[0])
            body = [split_row(b) for b in block[2:]]
            n = len(header)
            if n == 2 and header[0] in ("조항", "순위", "구분", "버전"):
                w = [avail * 0.14, avail * 0.86]
                cc = (0,)
            elif n == 2:
                w = [avail * 0.22, avail * 0.78]
                cc = ()
            elif n == 3:
                w = [avail * 0.16, avail * 0.30, avail * 0.54]
                cc = (0,)
            elif n == 4:
                w = [avail * f for f in (0.10, 0.16, 0.62, 0.12)]
                cc = (0, 1, 3)
            else:
                w = [avail / n] * n
                cc = (0, 1)
            F.append(make_table(header, body, w, center_cols=cc))
            F.append(Spacer(1, 4 * mm))
            continue
        elif re.match(r"^[-*] ", s):
            F.append(Paragraph(inline(s[2:]), S["bullet"], bulletText="•"))
        elif re.match(r"^\d+\. ", s):
            num, _, rest = s.partition(". ")
            F.append(Paragraph(inline(rest), S["bullet"], bulletText=num + "."))
        else:
            F.append(Paragraph(inline(s), S["body"]))
        i += 1

    doc.build(F)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
