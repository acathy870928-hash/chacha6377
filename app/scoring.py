"""'기사 신호' 점수 계산.

수집기가 signal 값을 직접 내려주면 그 값을 그대로 쓴다.
없을 때만 아래 규칙으로 보정해 우선 검토 후보를 뽑는다.
사업단 대표 / FA 관점에서 '영업에 바로 쓸 수 있는가'를 기준으로 가중치를 준다.
"""
import re
from datetime import datetime, timedelta

from .db import KST, now_kst

# 영업 현장에서 바로 화제가 되는 주제 (가중치 높음)
HIGH_VALUE = {
    "보험금": 8, "지급": 6, "보상": 6, "면책": 7, "분쟁": 6,
    "약관": 6, "손해사정": 5, "구상": 4,
    "절판": 9, "개정": 7, "신상품": 7, "출시": 5, "인수기준": 6,
    "요율": 5, "보험료": 6, "인상": 6, "인하": 5,
    "세제": 6, "비과세": 7, "연금": 5, "상속": 6, "증여": 6,
    "실손": 8, "간병": 6, "치매": 6, "유병자": 6, "고지의무": 7,
}

# 제도·감독 이슈 (대표가 챙겨야 하는 것)
REGULATORY = {
    "금융감독원": 6, "금감원": 6, "금융위": 6, "당국": 4,
    "제재": 6, "과태료": 5, "징계": 5, "검사": 3,
    "GA": 7, "법인보험대리점": 7, "설계사": 6, "모집": 4,
    "수수료": 7, "시책": 6, "1200%": 8, "불완전판매": 7,
}

# 사고·사기 사례 (교육 자료로 쓰기 좋음)
CASE = {
    "사기": 6, "적발": 5, "혐의": 4, "편취": 6, "고의사고": 6,
    "판결": 5, "소송": 4, "대법원": 5,
}

# 홍보성/의미 낮은 기사 (감점)
NOISE = {
    "봉사": -6, "기부": -5, "후원": -5, "캠페인": -4, "이벤트": -6,
    "임명": -3, "인사": -3, "위촉": -3, "협약": -3, "MOU": -4,
    "사회공헌": -5, "명예의전당": -4,
}

WEIGHTS = {**HIGH_VALUE, **REGULATORY, **CASE, **NOISE}

# 사업단에서 실제로 보는 매체 (신뢰도 보정)
PUBLISHER_BONUS = {
    "보험매일": 4, "보험저널": 3, "한국보험신문": 4, "인슈넷": 2,
    "보험신보": 3, "매일경제": 2, "한국경제": 2, "연합뉴스": 3,
}


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for parser in (
        lambda t: datetime.fromisoformat(t),
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t, "%Y-%m-%d"),
        lambda t: datetime.strptime(t, "%Y.%m.%d"),
    ):
        try:
            dt = parser(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=KST)
        except (ValueError, TypeError):
            continue
    return None


def freshness_bonus(published_at: str) -> int:
    """최신 기사일수록 가산. 오래된 기사는 후보에서 자연히 밀린다."""
    dt = _parse_dt(published_at)
    if dt is None:
        return 0
    age = now_kst() - dt
    if age < timedelta(hours=12):
        return 12
    if age < timedelta(days=1):
        return 9
    if age < timedelta(days=3):
        return 5
    if age < timedelta(days=7):
        return 2
    if age > timedelta(days=30):
        return -8
    return 0


def keyword_hits(text: str) -> list[tuple[str, int]]:
    """점수에 기여한 키워드를 (키워드, 점수)로 반환 — 화면에 근거를 보여주기 위함."""
    hits: list[tuple[str, int]] = []
    for word, weight in WEIGHTS.items():
        if word in text:
            hits.append((word, weight))
    hits.sort(key=lambda x: -abs(x[1]))
    return hits


def compute_signal(
    title: str,
    body: str = "",
    publisher: str = "",
    published_at: str = "",
) -> int:
    """0~99 사이의 '기사 신호' 점수."""
    title = title or ""
    body = body or ""

    score = 40  # 기본 점수

    # 제목에 걸린 키워드는 본문보다 2배 가중
    for _, weight in keyword_hits(title):
        score += weight * 2
    # 본문은 앞부분(리드)만 본다 — 뒤로 갈수록 관련도가 떨어진다
    for _, weight in keyword_hits(body[:1200]):
        score += weight

    score += PUBLISHER_BONUS.get(publisher.strip(), 0)
    score += freshness_bonus(published_at)

    # 너무 짧은 단신은 공유 가치가 낮다
    plain = re.sub(r"\s+", "", body)
    if len(plain) < 200:
        score -= 8
    elif len(plain) > 900:
        score += 3

    return max(0, min(99, int(score)))


def signal_reason(title: str, body: str = "", publisher: str = "") -> str:
    """대표가 '왜 이게 위로 왔지?'를 알 수 있게 한 줄 근거를 만든다."""
    hits = keyword_hits(f"{title} {body[:600]}")
    positives = [w for w, s in hits if s > 0][:3]
    parts = []
    if positives:
        parts.append(" · ".join(positives))
    if PUBLISHER_BONUS.get(publisher.strip()):
        parts.append(publisher.strip())
    return " / ".join(parts) if parts else "일반 기사"
