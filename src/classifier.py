"""제도 뉴스 / 상품·홍보 기사 자동 분류기.

여기서 내리는 결론은 어디까지나 '초벌'이다.
자동제외된 기사도 검수 화면에 남아 있고, 담당자가 언제든 되살릴 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .models import (
    Article,
    STATUS_AUTO_LOWREL,
    STATUS_AUTO_PROMO,
    STATUS_PENDING,
)

DEFAULT_FILTER_CONFIG = Path("config/filters.yaml")

# 제목은 본문보다 기사 성격을 잘 드러내므로 가중치를 더 준다.
TITLE_WEIGHT = 2.0
BODY_WEIGHT = 1.0
# 같은 단어가 본문에 여러 번 나와도 점수가 무한정 오르지 않도록 상한을 둔다.
MAX_BODY_HITS = 3


@dataclass
class Verdict:
    status: str
    policy_score: float
    promo_score: float
    matched_policy: list[str]
    matched_promo: list[str]
    reason: str
    dropped: bool = False  # 저장조차 하지 않을 기사


class Classifier:
    def __init__(self, config: dict):
        self.cfg = config
        th = config.get("thresholds", {})
        self.policy_min = float(th.get("policy_min", 3.0))
        self.promo_min = float(th.get("promo_min", 3.0))
        self.override_margin = float(th.get("policy_override_margin", 3.0))
        self.policy_keywords: dict[str, float] = config.get("policy_keywords", {}) or {}
        self.promo_keywords: dict[str, float] = config.get("promo_keywords", {}) or {}
        self.title_patterns = [
            re.compile(p) for p in (config.get("promo_title_patterns") or [])
        ]
        self.force_review = list(config.get("force_review_keywords") or [])
        self.drop_keywords = list(config.get("drop_keywords") or [])

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_FILTER_CONFIG) -> "Classifier":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(data)

    # ── 점수 계산 ─────────────────────────────────────────────────
    @staticmethod
    def _score(text: str, keywords: dict[str, float], weight: float, cap: int):
        total = 0.0
        hits: list[str] = []
        if not text:
            return total, hits
        lowered = text.lower()
        for word, w in keywords.items():
            count = lowered.count(word.lower())
            if count:
                total += float(w) * weight * min(count, cap)
                hits.append(word)
        return total, hits

    def classify(
        self,
        article: Article,
        *,
        source_weight: float = 1.0,
        always_review: bool = False,
    ) -> Verdict:
        title = article.title or ""
        body = f"{article.summary}\n{article.content}"
        haystack = f"{title}\n{body}"

        for word in self.drop_keywords:
            if word in title:
                return Verdict(
                    status=STATUS_AUTO_LOWREL,
                    policy_score=0.0,
                    promo_score=0.0,
                    matched_policy=[],
                    matched_promo=[],
                    reason=f"수집 제외 키워드 '{word}' 가 제목에 있음",
                    dropped=True,
                )

        p_title, p_hits_t = self._score(title, self.policy_keywords, TITLE_WEIGHT, 1)
        p_body, p_hits_b = self._score(body, self.policy_keywords, BODY_WEIGHT, MAX_BODY_HITS)
        policy_score = (p_title + p_body) * source_weight

        m_title, m_hits_t = self._score(title, self.promo_keywords, TITLE_WEIGHT, 1)
        m_body, m_hits_b = self._score(body, self.promo_keywords, BODY_WEIGHT, MAX_BODY_HITS)
        promo_score = m_title + m_body

        pattern_hits = [p.pattern for p in self.title_patterns if p.search(title)]
        promo_score += 3.0 * len(pattern_hits)

        matched_policy = sorted(set(p_hits_t) | set(p_hits_b))
        matched_promo = sorted(set(m_hits_t) | set(m_hits_b))

        policy_score = round(policy_score, 2)
        promo_score = round(promo_score, 2)

        # 규제기관 보도자료 등은 홍보 필터를 태우지 않는다.
        if always_review:
            return Verdict(
                STATUS_PENDING,
                policy_score,
                promo_score,
                matched_policy,
                matched_promo,
                "규제기관 원문 소스 → 홍보 필터 미적용, 검수 대기",
            )

        forced = [w for w in self.force_review if w in haystack]
        if forced:
            return Verdict(
                STATUS_PENDING,
                policy_score,
                promo_score,
                matched_policy,
                matched_promo,
                f"강제 검수 키워드: {', '.join(forced[:3])}",
            )

        if promo_score >= self.promo_min:
            # 홍보 문구가 있어도 제도 내용이 확실히 앞서면 검수 대기로 올린다.
            if policy_score - promo_score >= self.override_margin:
                return Verdict(
                    STATUS_PENDING,
                    policy_score,
                    promo_score,
                    matched_policy,
                    matched_promo,
                    f"홍보 신호({promo_score})보다 제도 신호({policy_score})가 우세",
                )
            hits = ", ".join((matched_promo + pattern_hits)[:4]) or "제목 패턴"
            return Verdict(
                STATUS_AUTO_PROMO,
                policy_score,
                promo_score,
                matched_policy,
                matched_promo,
                f"상품·홍보 신호 감지: {hits}",
            )

        if policy_score < self.policy_min:
            return Verdict(
                STATUS_AUTO_LOWREL,
                policy_score,
                promo_score,
                matched_policy,
                matched_promo,
                f"제도 관련 신호 부족 (policy_score {policy_score} < {self.policy_min})",
            )

        return Verdict(
            STATUS_PENDING,
            policy_score,
            promo_score,
            matched_policy,
            matched_promo,
            f"제도 신호 {policy_score}점: {', '.join(matched_policy[:4])}",
        )

    def apply(self, article: Article, **kwargs) -> Verdict:
        """분류 결과를 기사 객체에 반영한다."""
        verdict = self.classify(article, **kwargs)
        article.policy_score = verdict.policy_score
        article.promo_score = verdict.promo_score
        article.matched_policy = verdict.matched_policy
        article.matched_promo = verdict.matched_promo
        article.auto_reason = verdict.reason
        article.status = verdict.status
        if article.category == "미분류":
            article.category = guess_category(article)
        return verdict


# ── 분류 태그 추정 ────────────────────────────────────────────────
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("실손의료보험", ("실손", "비급여", "도수치료", "실손24", "청구 전산화")),
    ("판매채널·수수료", ("판매수수료", "1200%", "분급", "GA", "설계사", "비교공시", "승환")),
    ("건전성·회계", ("K-ICS", "킥스", "지급여력", "IFRS17", "기본자본", "해지율", "계리")),
    ("자동차보험", ("자동차보험", "경상환자", "한방", "자기부담금", "車보험")),
    ("보험사기·소비자보호", ("보험사기", "민원", "소비자보호", "불완전판매", "설명의무")),
    ("세제·연금", ("세액공제", "세제", "연금저축", "IRP", "비과세")),
    ("상품규제", ("표준약관", "상품설계기준", "무저해지", "배타적사용권", "상품심사")),
]


def guess_category(article: Article) -> str:
    haystack = f"{article.title}\n{article.summary}\n{article.content[:1500]}"
    best, best_hits = "미분류", 0
    for name, words in _CATEGORY_RULES:
        hits = sum(1 for w in words if w.lower() in haystack.lower())
        if hits > best_hits:
            best, best_hits = name, hits
    if best_hits == 0:
        return "기타 제도" if article.policy_score >= 3 else "미분류"
    return best
