"""요구사항 정의서 마크다운 → 조판된 HTML 문서.

약관 문서의 조항 체계를 그대로 빌려온다. 요구사항 고유번호(IA-FUN-001)를
조 번호처럼 바깥 여백에 걸고, 본문은 명칭 · 정의 · 요구사항 · 상세기술 ·
산출정보 다섯 칸으로 반복한다. 표는 문서 폭을 넘길 수 있으므로 자기 안에서만
가로로 흐르게 한다.
"""

import html
import io
import re

import markdown

SRC = "/home/user/chacha6377/docs/requirements.md"
OUT = "/home/user/chacha6377/docs/requirements.html"

FIELDS = ("명칭", "정의", "요구사항", "상세기술", "산출정보", "요구사항 · 상세기술")

CSS = """
:root {
  --paper: #FAFBFA;
  --surface: #FFFFFF;
  --ink: #151E1C;
  --muted: #64716E;
  --faint: #8B9793;
  --rule: #E1E7E4;
  --rule-soft: #EEF2F0;
  --accent: #0B6E5F;
  --accent-soft: #E8F2EF;
  --second: #7A5C2E;
  --second-soft: #F6F0E4;
  --warn: #A33A22;
  --warn-soft: #FAEDE8;
  --shadow: 0 1px 2px rgba(21, 30, 28, .05);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #101615;
    --surface: #161E1D;
    --ink: #E7EEEB;
    --muted: #9AA8A4;
    --faint: #778481;
    --rule: #27322F;
    --rule-soft: #1D2726;
    --accent: #52C9AF;
    --accent-soft: #16302B;
    --second: #C9A567;
    --second-soft: #2C2519;
    --warn: #E68A6E;
    --warn-soft: #33201A;
    --shadow: 0 1px 2px rgba(0, 0, 0, .3);
  }
}
:root[data-theme="dark"] {
  --paper: #101615;
  --surface: #161E1D;
  --ink: #E7EEEB;
  --muted: #9AA8A4;
  --faint: #778481;
  --rule: #27322F;
  --rule-soft: #1D2726;
  --accent: #52C9AF;
  --accent-soft: #16302B;
  --second: #C9A567;
  --second-soft: #2C2519;
  --warn: #E68A6E;
  --warn-soft: #33201A;
  --shadow: 0 1px 2px rgba(0, 0, 0, .3);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
    "Malgun Gothic", "Noto Sans KR", system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.72;
  word-break: keep-all;
  overflow-wrap: anywhere;
  -webkit-font-smoothing: antialiased;
}

.wrap {
  max-width: 980px;
  margin: 0 auto;
  padding: 56px 28px 120px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── 표제 ─────────────────────────────────────────── */
.masthead { border-bottom: 2.5px solid var(--accent); padding-bottom: 26px; margin-bottom: 34px; }
.eyebrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px; letter-spacing: .16em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 12px;
}
h1 {
  font-size: clamp(28px, 5vw, 40px); line-height: 1.22; margin: 0 0 10px;
  letter-spacing: -0.025em; font-weight: 800; text-wrap: balance;
}
.subtitle { color: var(--muted); font-size: 15px; margin: 0; }

/* ── 목차 ─────────────────────────────────────────── */
.toc {
  border: 1px solid var(--rule); border-radius: 10px; background: var(--surface);
  padding: 18px 22px; margin-bottom: 44px; box-shadow: var(--shadow);
}
.toc-h {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--faint); margin-bottom: 10px;
}
.toc ol { margin: 0; padding: 0; list-style: none; columns: 2; column-gap: 32px; }
.toc li { break-inside: avoid; margin-bottom: 3px; font-size: 13.5px; }
.toc a { color: var(--ink); text-decoration: none; border-bottom: 1px solid transparent; }
.toc a:hover, .toc a:focus-visible { border-bottom-color: var(--accent); color: var(--accent); }
.toc .n {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--faint); font-size: 12px; margin-right: 7px;
}

/* ── 본문 ─────────────────────────────────────────── */
h2 {
  font-size: 21px; font-weight: 800; letter-spacing: -0.02em;
  margin: 60px 0 20px; padding-top: 22px; border-top: 1px solid var(--rule);
  scroll-margin-top: 20px; text-wrap: balance;
}
h2:first-of-type { border-top: none; padding-top: 0; }
hr + h2 { margin-top: 24px; padding-top: 0; border-top: none; }
h3 {
  font-size: 15.5px; font-weight: 750; margin: 40px 0 14px;
  letter-spacing: -0.01em; text-wrap: balance;
}
h3.reqid {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px; letter-spacing: .06em; color: var(--accent);
  font-weight: 700; margin: 0;
}
p { margin: 0 0 14px; max-width: 74ch; }
ul, ol { margin: 0 0 16px; padding-left: 22px; max-width: 74ch; }
li { margin-bottom: 6px; }
li > ul, li > ol { margin-top: 6px; }
strong { font-weight: 750; }
a { color: var(--accent); }

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .86em; background: var(--accent-soft); color: var(--accent);
  padding: 1px 5px; border-radius: 4px;
}
pre {
  background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
  padding: 16px 18px; overflow-x: auto; margin: 0 0 20px;
  font-size: 12.5px; line-height: 1.65;
}
pre code { background: none; color: var(--ink); padding: 0; font-size: inherit; }

blockquote {
  margin: 0 0 20px; padding: 14px 20px; border-left: 3px solid var(--accent);
  background: var(--accent-soft); border-radius: 0 8px 8px 0; max-width: 74ch;
}
blockquote p:last-child { margin-bottom: 0; }

hr { border: none; border-top: 1px solid var(--rule-soft); margin: 40px 0; }

/* ── 표 ───────────────────────────────────────────── */
.tablewrap { overflow-x: auto; margin: 0 0 22px; -webkit-overflow-scrolling: touch; }
table {
  border-collapse: collapse; width: 100%; min-width: 460px;
  font-size: 13.5px; font-variant-numeric: tabular-nums;
  background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
}
th, td { text-align: left; vertical-align: top; padding: 9px 13px; border-bottom: 1px solid var(--rule-soft); line-height: 1.6; }
th { background: var(--rule-soft); font-weight: 700; font-size: 12.5px; color: var(--muted); white-space: nowrap; }
tbody tr:last-child td { border-bottom: none; }
td code { font-size: 12px; }

/* ── 요구사항 블록 ─────────────────────────────────── */
.req {
  background: var(--surface); border: 1px solid var(--rule); border-left: 3px solid var(--accent);
  border-radius: 0 10px 10px 0; padding: 20px 24px; margin: 0 0 12px;
  box-shadow: var(--shadow);
}
.req.second { border-left-color: var(--second); }
.reqhead {
  display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  padding-bottom: 12px; margin-bottom: 16px; border-bottom: 1px solid var(--rule-soft);
}
.reqname { font-size: 16px; font-weight: 800; letter-spacing: -0.015em; flex: 1 1 260px; }
.chip {
  font-size: 11px; font-weight: 700; letter-spacing: .04em; border-radius: 999px;
  padding: 2px 9px; background: var(--rule-soft); color: var(--muted); white-space: nowrap;
}
.chip.stage { background: var(--accent-soft); color: var(--accent); }
.chip.stage.second { background: var(--second-soft); color: var(--second); }
.chip.owner { border: 1px dashed var(--rule); background: none; color: var(--faint); }

.field { display: grid; grid-template-columns: 74px 1fr; gap: 14px; margin: 0 0 14px; max-width: none; }
.field:last-child { margin-bottom: 0; }
.field > .lab {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10.5px; letter-spacing: .1em; color: var(--faint);
  padding-top: 6px; text-transform: uppercase;
}
.field > .val { min-width: 0; }
.field > .val > :last-child { margin-bottom: 0; }
.field > .val p, .field > .val ul, .field > .val ol { max-width: 70ch; }

@media (max-width: 640px) {
  .wrap { padding: 36px 18px 80px; }
  .toc ol { columns: 1; }
  .req { padding: 16px 16px; }
  .field { grid-template-columns: 1fr; gap: 2px; }
  .field > .lab { padding-top: 0; }
}

footer {
  margin-top: 72px; padding-top: 22px; border-top: 1px solid var(--rule);
  color: var(--faint); font-size: 12.5px;
}

@media print {
  body { background: #fff; font-size: 10pt; }
  .toc, .req { box-shadow: none; }
  .req, table, blockquote, pre { break-inside: avoid; }
  h2, h3 { break-after: avoid; }
}
"""


def _fields_to_blocks(chunk: str) -> str:
    """`<p><strong>명칭</strong> …</p>` 묶음을 라벨 + 내용 두 칸으로 바꾼다."""
    pattern = re.compile(
        r"<p><strong>(" + "|".join(map(re.escape, FIELDS)) + r")</strong>\s*(.*?)</p>",
        re.S,
    )

    marks: list[tuple[int, int, str, str]] = [
        (m.start(), m.end(), m.group(1), m.group(2).strip()) for m in pattern.finditer(chunk)
    ]
    if not marks:
        return chunk

    out = [chunk[: marks[0][0]]]
    for i, (_, end, label, inline) in enumerate(marks):
        tail = marks[i + 1][0] if i + 1 < len(marks) else len(chunk)
        body = (f"<p>{inline}</p>" if inline else "") + chunk[end:tail]
        out.append(
            f'<div class="field"><div class="lab">{label}</div>'
            f'<div class="val">{body}</div></div>'
        )
    return "".join(out)


def _meta(cells: list[str]) -> dict:
    """머리표의 라벨/값 쌍을 뽑는다. 담당 칸은 비어 있는 것이 정상이다."""
    return {cells[i]: (cells[i + 1] if i + 1 < len(cells) else "") for i in range(0, len(cells), 2)}


def build_requirements(body: str) -> str:
    """머리표(`분류 | … | 담당`)만 있는 표를 찾아 뒤따르는 문단과 함께 카드로 묶는다.

    표를 정규식 하나로 통째로 잡지 않는다. 셀이 여덟 칸이라 중첩 반복이 생기고,
    본문이 있는 표(목록표)에서 되짚기가 폭발한다. 표의 시작과 끝만 찾아 자른다.
    """
    pieces: list[str] = []
    cursor = 0
    pos = 0
    while True:
        start = body.find("<table>", pos)
        if start < 0:
            break
        close = body.find("</table>", start)
        if close < 0:
            break
        close += len("</table>")
        pos = close

        table = body[start:close]
        cells = [
            re.sub(r"<[^>]+>", "", c).strip()
            for c in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)
        ]
        if not cells or cells[0] != "분류":
            continue
        # 머리표는 본문이 비어 있다. 값이 든 표(목록표 등)는 건드리지 않는다.
        rows = "".join(re.findall(r"<td[^>]*>(.*?)</td>", table, re.S))
        if re.sub(r"<[^>]+>|\s", "", rows):
            continue

        meta = _meta(cells)
        stage = meta.get("단계", "").strip() or "1차"
        is_second = "2차" in stage
        rid = meta.get("고유번호", "")
        kind = meta.get("분류", "")

        # 다음 머리표도 경계다. 한 절에 요구사항 둘이 붙어 있는 경우가 있다.
        stop = re.search(
            r"<hr\s*/?>|<h[123][ >]|<table>\s*<thead>\s*<tr>\s*<th>분류</th>",
            body[close:],
        )
        end = close + (stop.start() if stop else len(body) - close)
        chunk = body[close:end]

        name_m = re.search(r"<p><strong>명칭</strong>\s*(.*?)</p>", chunk, re.S)
        name = name_m.group(1).strip() if name_m else rid
        if name_m:
            chunk = chunk.replace(name_m.group(0), "", 1)

        second = " second" if is_second else ""
        pieces.append(body[cursor:start])
        pieces.append(
            '<div class="req%s" id="%s"><div class="reqhead">'
            '<h3 class="reqid">%s</h3><div class="reqname">%s</div>'
            '<span class="chip">%s</span>'
            '<span class="chip stage%s">%s</span>'
            '<span class="chip owner">담당 —</span></div>%s</div>'
            % (second, html.escape(rid), html.escape(rid), name, html.escape(kind),
               second, html.escape(stage), _fields_to_blocks(chunk))
        )
        cursor = end
        pos = end

    pieces.append(body[cursor:])
    return "".join(pieces)


def main() -> None:
    text = io.open(SRC, encoding="utf-8").read()
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "attr_list"])

    # 표제는 별도 조판으로 뽑아 쓴다.
    body = re.sub(r"<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)
    body = re.sub(r"<p>FA용 보험 상담 AI · 1차 오픈 2026-10-01</p>\s*", "", body, count=1)

    body = build_requirements(body)

    # 남은 h3(IA-…만 있는 제목)은 묶음 표제로만 남긴다.
    body = re.sub(r"<h3>((?:IA-[A-Z]+-\d+)(?:\s*·\s*IA-[A-Z]+-\d+)*)</h3>", "", body)

    # 목차 — h2에 앵커를 달고 목록을 만든다.
    toc: list[tuple[str, str, str]] = []

    def anchor(m):
        raw = re.sub(r"<[^>]+>", "", m.group(1))
        num, sep, rest = raw.partition(". ")
        if not sep:  # 「참고」처럼 번호가 없는 절
            num, rest = "", raw
        slug = "sec-" + (num.strip().replace(".", "-") or re.sub(r"\W+", "", raw))
        toc.append((slug, num.strip(), rest.strip()))
        return f'<h2 id="{slug}">{m.group(1)}</h2>'

    body = re.sub(r"<h2>(.*?)</h2>", anchor, body, flags=re.S)

    # 표는 자기 안에서만 가로로 흐르게 한다.
    body = re.sub(r"<table>", '<div class="tablewrap"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)

    items = "".join(
        f'<li><a href="#{s}">'
        + (f'<span class="n">{n}</span>' if n else "")
        + f"{html.escape(t)}</a></li>"
        for s, n, t in toc
    )

    page = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Insurance AI 요구사항 정의서</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="eyebrow">요구사항 정의서 · 1차 오픈 2026-10-01</div>
    <h1>Insurance AI</h1>
    <p class="subtitle">FA용 보험 상담 AI — 요구사항 38건 (1차 33 · 2차 5)</p>
  </header>
  <nav class="toc">
    <div class="toc-h">목차</div>
    <ol>{items}</ol>
  </nav>
  {body}
  <footer>
    주식회사 아이에프에이 AX팀 · 2026-08-14 작성 · 담당 칸은 협의 후 채웁니다.<br>
    화면 속 고객명 · 대화는 가상이며 상품명은 시드 데이터 기준입니다.
  </footer>
</div>
</body>
</html>
"""
    io.open(OUT, "w", encoding="utf-8").write(page)
    cards = page.count('class="req')
    print(f"{OUT} — 목차 {len(toc)}개, 요구사항 카드 {cards}개")


if __name__ == "__main__":
    main()
