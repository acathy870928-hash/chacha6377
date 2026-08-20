#!/usr/bin/env python3
"""혼자 도는 샘플 HTML 을 만든다.

실제 앱의 CSS 를 그대로 끼워 넣기 때문에, 이 파일에서 보이는 화면은
서버에 올렸을 때와 같은 모습이다. 화면을 고치면 이 스크립트를 다시 돌리면 된다.

  python3 demo/build_sample.py
  → demo/ifanews-어드민-샘플.html
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "demo" / "template.html"
OUT = ROOT / "demo" / "ifanews-어드민-샘플.html"

# public.css 는 FA 화면 안에서만 쓴다. 페이지 전체를 건드리는 규칙은 빼야
# 어드민 화면이 망가지지 않는다 (특히 다크모드 블록과 body 배경).
DROP_SELECTORS = {
    ":root", "html", "*", "body",
    ".center-page", ".notfound", ".notfound h1", ".notfound p",
}


def strip_global_rules(css: str) -> str:
    """페이지 전역에 영향을 주는 규칙과 다크모드 블록을 걷어낸다."""
    # @media 블록 통째로 제거 (중첩 중괄호까지 세면서)
    out = []
    i = 0
    while i < len(css):
        if css.startswith("@media", i):
            depth = 0
            j = css.index("{", i)
            depth = 1
            j += 1
            while j < len(css) and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            i = j
            continue
        out.append(css[i])
        i += 1
    css = "".join(out)

    # 남은 최상위 규칙 중 전역 선택자를 제거
    kept = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = match.group(1).strip()
        selector = re.sub(r"/\*.*?\*/", "", selector, flags=re.S).strip()
        if not selector:
            continue
        parts = [s.strip() for s in selector.split(",")]
        if all(p in DROP_SELECTORS for p in parts):
            continue
        kept.append(f"{selector} {{{match.group(2)}}}")
    return "\n".join(kept)


ARTICLES = [
    {
        "slug": "38f8jiss",
        "title": "실손보험 청구 전산화 2단계 시행…의원급 확대",
        "publisher": "한국금융신문", "published": "2026-08-20",
        "origin": "https://www.fins.co.kr/news/articleView.html?idxno=109694",
        "signal": 80, "why": "실손 · 보험금 · 개정",
        "audience": "fa", "status": "candidate", "picked": True,
        "point": "청구 간소화 = 고객 접점 늘어납니다. 이번 주 상담 오프닝으로 쓰세요.",
        "body": "실손보험 청구 전산화가 의원급으로 확대된다. 보험금 청구 절차가 간소화되면서 가입자 편의가 높아질 전망이다.",
        "paragraphs": [
            "이 자리에는 수집기가 가져온 기사 본문이 문단 그대로 들어갑니다. 지금 보시는 문장은 글자 크기와 줄 간격을 확인하시라고 넣어둔 예시입니다.",
            "본문 외에는 아무것도 넣지 않았습니다. 배너도, 관련기사 목록도, 자동재생 영상도 없습니다. FA가 이동 중에 한 손으로 읽어야 하기 때문입니다.",
            "맨 아래에는 원문 링크만 둡니다. 더 보고 싶은 사람은 그때 언론사 페이지로 넘어가면 됩니다.",
        ],
    },
    {
        "slug": "4ktpqvoe",
        "title": "법규 위반 차량 노려 ‘쾅’…20대 일당, 고의사고로 보험금 3억원 편취",
        "publisher": "한국보험신문", "published": "2026-08-20",
        "origin": "https://www.insnews.co.kr/news/articleView.html?idxno=92282",
        "signal": 74, "why": "보험금 · 편취 · 고의사고",
        "audience": "rep", "status": "candidate", "picked": False, "point": "",
        "body": "보험사기 혐의로 20대 일당이 적발됐다. 고의사고를 반복해 보험금을 편취한 혐의다.",
        "paragraphs": [
            "이 자리에는 수집기가 가져온 기사 본문이 문단 그대로 들어갑니다. 보험사기 유형 기사는 FA 교육 자료로 자주 쓰여서 신호 점수를 높게 잡아두었습니다.",
            "본문 외에는 아무것도 넣지 않습니다. 맨 아래 원문 링크만 둡니다.",
        ],
    },
    {
        "slug": "pw31mkzq",
        "title": "보험업감독규정 일부개정안 규정변경 예고",
        "publisher": "금융위원회", "published": "2026-08-20",
        "origin": "https://www.fsc.go.kr",
        "signal": 71, "why": "금융위 · 개정 · 약관",
        "audience": "rep", "status": "candidate", "picked": False, "point": "",
        "summaryOnly": True,
        "body": "금융위원회는 보험업감독규정 일부개정안을 규정변경 예고했다. 자세한 내용은 첨부파일을 참고하시기 바랍니다.",
        "paragraphs": [],
    },
    {
        "slug": "kzueoi7i",
        "title": "폭염에 온열질환 급증…보험 보장 범위는",
        "publisher": "동아일보", "published": "2026-08-20",
        "origin": "https://www.donga.com/news/Health/article/all/20260820/134510009/1",
        "signal": 66, "why": "보장 범위 · 실손",
        "audience": "fa", "status": "candidate", "picked": True, "point": "",
        "body": "온열질환 관련 문의가 늘면서 보장 범위를 두고 확인이 필요하다는 지적이 나온다.",
        "paragraphs": [
            "이 자리에는 수집기가 가져온 기사 본문이 문단 그대로 들어갑니다.",
            "계절 이슈 기사는 상담 때 말 꺼내기 좋은 소재라 FA용으로 잡아두었습니다.",
        ],
    },
    {
        "slug": "phsryp4d",
        "title": "NH농협손해보험, 축사 화재 인수 점검 실시",
        "publisher": "한국보험신문", "published": "2026-08-19",
        "origin": "https://www.insnews.co.kr/news/articleView.html?idxno=92260",
        "signal": 54, "why": "인수기준",
        "audience": "rep", "status": "candidate", "picked": False, "point": "",
        "body": "축사 화재 관련 인수 기준을 점검한다고 밝혔다.",
        "paragraphs": [
            "이 자리에는 수집기가 가져온 기사 본문이 문단 그대로 들어갑니다.",
            "인수기준 관련 기사는 영업 현장에 바로 영향을 주기 때문에 우선 검토 후보로 올라옵니다.",
        ],
    },
    {
        "slug": "tsp8q7jo",
        "title": "지자체가 지원하는 배상책임보험…민간보험엔 사각지대 있을까",
        "publisher": "한국보험신문", "published": "2026-08-19",
        "origin": "https://www.insnews.co.kr/news/articleView.html?idxno=92142",
        "signal": 53, "why": "배상책임 · 보장 공백",
        "audience": "rep", "status": "candidate", "picked": False, "point": "",
        "body": "지자체 지원 배상책임보험과 민간보험 사이의 보장 공백을 짚었다.",
        "paragraphs": [
            "이 자리에는 수집기가 가져온 기사 본문이 문단 그대로 들어갑니다.",
            "보장 공백을 짚는 기사는 상담 화법으로 연결하기 좋아, 대표가 한 줄 코멘트를 붙여 내보내기 좋은 유형입니다.",
        ],
    },
    {
        "slug": "hn28djwm",
        "title": "○○생명 임직원 연탄 나눔 봉사활동 실시",
        "publisher": "보험매일", "published": "2026-08-18",
        "origin": "",
        "signal": 27, "why": "일반 기사",
        "audience": "fa", "status": "candidate", "picked": False, "point": "",
        "body": "사회공헌 캠페인의 일환으로 봉사활동을 펼쳤다.",
        "paragraphs": [
            "홍보성 기사는 신호 점수에서 감점되어 아래로 내려갑니다. 이런 기사를 걸러내라고 점수를 매깁니다.",
        ],
    },
]


def main() -> None:
    admin_css = (ROOT / "app" / "static" / "admin.css").read_text(encoding="utf-8")
    public_css = strip_global_rules(
        (ROOT / "app" / "static" / "public.css").read_text(encoding="utf-8"))

    data = "const ARTICLES = " + json.dumps(ARTICLES, ensure_ascii=False, indent=2) + ";"

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__ADMIN_CSS__", admin_css)
    html = html.replace("__PUBLIC_CSS__", public_css)
    html = html.replace("__DATA__", data)

    OUT.write_text(html, encoding="utf-8")
    print(f"만들었습니다: {OUT.relative_to(ROOT)}  ({len(html):,} 바이트, 기사 {len(ARTICLES)}건)")


if __name__ == "__main__":
    main()
