"""요구사항 정의서 마크다운을 인쇄용 PDF로 만든다.

한글 문서라 폰트(나눔고딕)를 명시하고, 표가 A4 폭을 넘지 않도록
글자 크기와 여백을 인쇄 기준으로 잡는다.
"""

import io
import re
import subprocess
import sys

import markdown

SRC = "/home/user/chacha6377/docs/requirements.md"
HTML = "/tmp/claude-0/-home-user-chacha6377/ca7f6080-cf3a-5093-8a0d-eb3bfdb80785/scratchpad/requirements.html"
OUT = "/home/user/chacha6377/docs/Insurance_AI_요구사항정의서_v1.pdf"

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm; }
* { box-sizing: border-box; }
body {
  font-family: "NanumGothic", "NanumBarunGothic", sans-serif;
  font-size: 9.4pt; line-height: 1.62; color: #1C2621;
  margin: 0; word-break: keep-all;
}
h1 {
  font-size: 20pt; margin: 0 0 4mm; letter-spacing: -0.02em;
  padding-bottom: 3mm; border-bottom: 2.4px solid #14A05A;
}
h2 {
  font-size: 13.5pt; margin: 11mm 0 3.5mm; padding-top: 3mm;
  border-top: 1px solid #D8E2DC; letter-spacing: -0.01em;
  page-break-after: avoid;
}
h3 {
  font-size: 10.6pt; margin: 7mm 0 2.5mm; color: #0B7C44;
  page-break-after: avoid;
}
h2 + h3 { margin-top: 4mm; }
p { margin: 0 0 2.6mm; }
ul, ol { margin: 0 0 3mm; padding-left: 5.5mm; }
li { margin-bottom: 1.1mm; }
strong { font-weight: 800; }
code {
  font-family: "NanumGothicCoding", monospace; font-size: 8.6pt;
  background: #F1F5F2; padding: 0.5mm 1.2mm; border-radius: 2px;
  color: #245C41;
}
pre {
  background: #F7FAF8; border: 1px solid #E1E9E4; border-radius: 3px;
  padding: 3mm 3.5mm; font-size: 8.2pt; line-height: 1.5;
  overflow: hidden; page-break-inside: avoid; margin: 0 0 3.5mm;
}
pre code { background: none; padding: 0; color: #1C2621; }
blockquote {
  margin: 0 0 3.5mm; padding: 2.5mm 4mm; border-left: 3px solid #14A05A;
  background: #F4FAF6; font-size: 9pt;
}
blockquote p:last-child { margin-bottom: 0; }
table {
  width: 100%; border-collapse: collapse; margin: 0 0 4mm;
  font-size: 8.5pt; page-break-inside: avoid; table-layout: auto;
}
th, td {
  border: 1px solid #DCE5E0; padding: 1.7mm 2.2mm;
  text-align: left; vertical-align: top; line-height: 1.5;
}
th { background: #EFF5F1; font-weight: 700; }
tr:nth-child(even) td { background: #FBFCFB; }
hr { border: none; border-top: 1px solid #E1E9E4; margin: 7mm 0; }
a { color: #0B7C44; text-decoration: none; }

/* 요구사항 머리표 — 분류/고유번호/우선순위/담당 한 줄 */
table.reqhead { margin-bottom: 2.5mm; }
table.reqhead th { background: #14A05A; color: #FFF; font-size: 8.4pt; }
table.reqhead th:nth-child(even) { background: #F1F7F3; color: #1C2621; }
"""


def main() -> int:
    text = io.open(SRC, encoding="utf-8").read()
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "attr_list"])

    # 요구사항 머리표(본문 없이 헤더만 있는 표)를 따로 칠한다.
    body = re.sub(
        r"<table>\s*<thead>\s*<tr>\s*<th>분류</th>",
        '<table class="reqhead">\n<thead>\n<tr>\n<th>분류</th>',
        body,
    )

    html = (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        "<title>Insurance AI 요구사항 정의서</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    io.open(HTML, "w", encoding="utf-8").write(html)

    subprocess.run(
        [
            "/opt/pw-browsers/chromium",
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--no-pdf-header-footer",
            f"--print-to-pdf={OUT}",
            f"file://{HTML}",
        ],
        check=True,
        capture_output=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
