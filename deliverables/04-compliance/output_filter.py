"""출력 필터 — 생성된 챗봇 응답의 컴플라이언스 검사.

⚠️ 프롬프트 지시만으로는 불충분하다. LLM은 지시를 확률적으로 위반하며,
보험 권유 영역에서는 1회 위반도 리스크다. 이 필터는 생성 이후 단계에서
답변을 재검사하는 마지막 방어선이다.

사용:
    from output_filter import OutputFilter

    f = OutputFilter()
    result = f.check(response_text, context={"stage": 5, "has_numbers": True})
    if result.blocked:
        response_text = result.safe_response

실행:
    python3 output_filter.py            # 자체 검증 (금지표현 테스트 발화 전수 검사)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
FORBIDDEN_PATH = _HERE / "forbidden-expressions.json"
DISCLOSURE_PATH = _HERE / "required-disclosures.json"


@dataclass
class Violation:
    rule_id: str
    category: str
    severity: str
    matched_text: str
    replacement: str
    action: str | None = None


@dataclass
class FilterResult:
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    missing_disclosures: list[str] = field(default_factory=list)
    safe_response: str | None = None
    actions: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(v.severity == "BLOCK" for v in self.violations)

    @property
    def needs_regeneration(self) -> bool:
        return bool(self.missing_disclosures) or any(
            v.severity == "REWRITE" for v in self.violations
        )


BLOCK_FALLBACK = "죄송합니다. 정확한 안내를 위해 전문 상담사에게 연결해 드릴게요."


class OutputFilter:
    """금지 표현 탐지 + 필수 고지 누락 검증."""

    def __init__(
        self,
        forbidden_path: Path = FORBIDDEN_PATH,
        disclosure_path: Path = DISCLOSURE_PATH,
    ) -> None:
        self.forbidden = json.loads(forbidden_path.read_text(encoding="utf-8"))
        self.disclosures = json.loads(disclosure_path.read_text(encoding="utf-8"))
        self._compiled = self._compile_patterns()

    def _compile_patterns(self) -> list[tuple[dict, list[re.Pattern]]]:
        compiled = []
        for rule in self.forbidden["rules"]:
            pats = [re.compile(p) for p in rule.get("patterns", [])]
            if pats:
                compiled.append((rule, pats))
        return compiled

    # --------------------------------------------------------
    # 1. 금지 표현 검사
    # --------------------------------------------------------
    def check_forbidden(self, text: str) -> list[Violation]:
        found = []
        for rule, patterns in self._compiled:
            for pat in patterns:
                m = pat.search(text)
                if m:
                    found.append(
                        Violation(
                            rule_id=rule["id"],
                            category=rule["category"],
                            severity=rule["severity"],
                            matched_text=m.group(0),
                            replacement=rule.get("replacement", ""),
                            action=rule.get("action"),
                        )
                    )
                    break  # 규칙당 1건만 기록
        return found

    # --------------------------------------------------------
    # 2. 필수 고지 검증
    # --------------------------------------------------------
    def check_disclosures(self, text: str, context: dict[str, Any]) -> list[str]:
        """context에 따라 필요한 고지가 누락되었는지 확인한다.

        context 키:
            has_numbers: 계산 결과 포함 여부
            mentions_tax_credit: 세액공제 언급 여부
            mentions_product: 상품 제안 여부
            cites_statistic: 통계 인용 여부
            estimates_nps: 국민연금 추정액 제시 여부
        """
        missing = []

        # VAL-001 — 계산 결과에는 가정 명시
        if context.get("has_numbers"):
            if not re.search(r"가정|단순\s*예시|보장하지\s*않", text):
                missing.append("DISC-006")

        # VAL-002 — 세액공제 언급 시 중도해지 페널티 + 변동 가능성
        # ⚠️ '16.5%'만으로는 충족으로 보지 않는다. 세액공제율도 16.5%라
        #    숫자만 검사하면 페널티 고지 누락을 놓친다.
        if context.get("mentions_tax_credit") or "세액공제" in text:
            if not re.search(r"기타소득세", text):
                missing.append("DISC-007")
            if not re.search(r"달라질\s*수|결정세액|세법\s*개정", text):
                missing.append("DISC-008")

        # VAL-003 — 상품 제안 시 리스크 고지 2개 이상
        if context.get("mentions_product"):
            risk_hits = sum(
                bool(re.search(p, text))
                for p in [r"원금\s*손실", r"사업비", r"해지환급금"]
            )
            if risk_hits < 2:
                missing.append("DISC-003/004/005 (최소 2개 필요)")

        # VAL-004 — 통계 인용 시 출처
        if context.get("cites_statistic"):
            if not re.search(r"국민연금|통계청|보건복지부|국민연금연구원", text):
                missing.append("DISC-013")

        # VAL-005 — 세션 첫 응답 AI 고지
        if context.get("is_first_message"):
            if not re.search(r"AI|인공지능", text):
                missing.append("DISC-001")

        # 국민연금 추정치 고지
        if context.get("estimates_nps"):
            if not re.search(r"추정|공단|확인하실", text):
                missing.append("DISC-015")

        return missing

    # --------------------------------------------------------
    # 3. 통합 검사
    # --------------------------------------------------------
    def check(self, text: str, context: dict[str, Any] | None = None) -> FilterResult:
        context = context or {}
        violations = self.check_forbidden(text)
        missing = self.check_disclosures(text, context)

        actions = [v.action for v in violations if v.action]

        result = FilterResult(
            passed=not violations and not missing,
            violations=violations,
            missing_disclosures=missing,
            actions=actions,
        )

        if result.blocked:
            result.safe_response = BLOCK_FALLBACK

        return result

    # --------------------------------------------------------
    # 4. 자동 보정 (경미한 누락에 한해)
    # --------------------------------------------------------
    def auto_append_disclosures(self, text: str, missing: list[str]) -> str:
        """auto_append 대상 고지를 응답 끝에 붙인다.

        regenerate 대상(DISC-007, DISC-008, 상품 리스크)은 여기서 처리하지 않는다.
        누락된 채로 문장을 덧붙이면 맥락이 어긋나므로 재생성이 옳다.
        """
        appendix = []
        lookup = {d["id"]: d for d in self.disclosures["disclosures"]}
        for mid in missing:
            if mid in ("DISC-006", "DISC-013", "DISC-015"):
                d = lookup.get(mid)
                if d:
                    appendix.append(d["text"])
        if not appendix:
            return text
        return text + "\n\n" + "\n".join(f"⚠️ {a}" for a in appendix)


# ============================================================
# 자체 검증
# ============================================================

def _self_test() -> int:
    """forbidden-expressions.json의 test_utterances가 전부 탐지되는지 검사."""
    f = OutputFilter()
    total = 0
    caught = 0
    failures = []

    for rule in f.forbidden["rules"]:
        for utt in rule.get("test_utterances", []):
            total += 1
            violations = f.check_forbidden(utt)
            ids = [v.rule_id for v in violations]
            if rule["id"] in ids:
                caught += 1
            else:
                failures.append((rule["id"], utt, ids))

    print("=" * 64)
    print("출력 필터 자체 검증")
    print("=" * 64)
    print(f"\n금지표현 탐지: {caught}/{total}")
    for rid, utt, got in failures:
        print(f"  ❌ {rid} 미탐지: {utt!r} (탐지된 규칙: {got})")

    # 오탐 검사 — 정상 응답이 걸리면 안 된다
    safe_samples = [
        "맞아요, 지금 당장이 제일 빠듯하죠. 월 10만 원부터 시작하실 수 있어요.",
        "연 600만 원 한도로 납입액의 13.2~16.5%를 세액공제받으실 수 있어요. "
        "다만 중도 해지 시 기타소득세 16.5%가 부과됩니다.",
        "65세 이상 연금 수급자의 월평균 수급액은 약 69만 5천 원입니다"
        "(통계청 「2023년 연금통계」).",
        "저는 OO생명의 AI 상담 도우미입니다.",
        "상품 유형에 따라 원금 손실이 발생할 수 있습니다.",
        "(연 3% 복리 가정, 세전 단순 예시이며 실제 수익률을 보장하지 않습니다)",
        "그 부분은 제가 정확히 확인할 수 없어 추측으로 말씀드리지 않을게요.",
        "네, 부담 드리지 않을게요. 필요하실 때 언제든 다시 찾아주세요.",
    ]
    false_positives = []
    for s in safe_samples:
        v = f.check_forbidden(s)
        if v:
            false_positives.append((s, [x.rule_id for x in v]))

    print(f"\n정상 응답 오탐: {len(false_positives)}/{len(safe_samples)}")
    for s, ids in false_positives:
        print(f"  ⚠️ 오탐 {ids}: {s[:50]}...")

    # 고지 누락 검사
    print("\n필수 고지 누락 탐지:")
    cases = [
        (
            "월 20만 원이면 27년 뒤 약 9,965만 원이 됩니다.",
            {"has_numbers": True},
            ["DISC-006"],
        ),
        (
            "세액공제 16.5%를 받으실 수 있어요.",
            {"mentions_tax_credit": True},
            ["DISC-007", "DISC-008"],
        ),
        (
            "연금저축보험을 추천드려요.",
            {"mentions_product": True},
            ["DISC-003/004/005 (최소 2개 필요)"],
        ),
    ]
    disc_ok = 0
    for text, ctx, expected in cases:
        missing = f.check_disclosures(text, ctx)
        ok = all(e in missing for e in expected)
        disc_ok += ok
        mark = "✅" if ok else "❌"
        print(f"  {mark} {text[:32]}... → 누락 탐지 {missing}")

    print("\n" + "=" * 64)
    all_pass = (
        caught == total and not false_positives and disc_ok == len(cases)
    )
    print("결과:", "✅ 전체 통과" if all_pass else "❌ 실패 항목 있음")
    print("=" * 64)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
