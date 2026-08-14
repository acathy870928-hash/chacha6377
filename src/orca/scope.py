"""약관 스코프 — 검색하기 전에 「어느 약관인지」를 먼저 확정한다.

## 왜 이것이 첫 단계인가

베테랑 담당자는 조항을 찾기 전에 **어느 약관인지부터 확정한다.**
확정되기 전에는 조항을 찾지 않고, 확정이 안 되면 답을 지어내지 않고 되묻는다.
그다음에야 그 약관 **한 권만** 펼친다.

그런데 「약관을 전부 넣어두고 질문과 닮은 조각을 찾는」 방식에는 이 1단계가 없다.
100권을 잘게 잘라 한 통에 섞어두고 닮은 것을 고른다. 사람으로 치면
책장을 보지 않고 뜯어놓은 페이지 더미에 손을 넣어 더듬는 것이다.

**같은 조건을 사람에게 주면 사람도 못 한다.** 표지를 떼고 본문에서 상품명을 지우고
페이지를 섞어 놓은 뒤 「계단에서 굴러 골절됐는데 보장되나요」라고 물으면
30년 차도 못 맞춘다. 능력이 아니라 조건의 문제다.

## 왜 하필 약관에서 그런가

약관은 **서로 80~90%가 똑같은 책들**이기 때문이다. 상품마다 다른 부분은 10~20%뿐이다.
검색이 하는 일은 「닮은 것 찾기」인데, 대상이 전부 닮아 있으면 아무거나 집어온다.
쌍둥이 100명 중에서 닮은 사람을 찾으라는 것과 같다.

그래서 **약관을 더 넣어도 좋아지지 않는다. 오히려 나빠진다** — 닮은 것이 더 많아진다.
데이터를 늘려서 해결되는 종류의 문제가 아니다.

    사내 규정 · 매뉴얼   서로 완전히 다름      → 넣어두면 답한다
    뉴스 · 리포트        주제가 전부 다름      → 넣어두면 답한다
    제품 매뉴얼(모델별)  일부 겹침             → 주의 필요
    **보험 약관**        **서로 80~90% 동일**  → **안 된다**

## 검색은 「모르겠다」를 출력할 수 없다

이것이 가장 위험한 부분이다. 검색은 구조상 후보를 점수순으로 내놓게 되어 있고,
100권이 다 닮아도 **1등은 반드시 나온다.** 사람은 모르면 「어느 상품이에요?」라고
되묻지만, 검색은 언제나 가장 그럴듯한 것을 자신 있게 내놓는다.
그래서 틀렸을 때 **틀렸다는 신호가 어디에도 남지 않는다.**

약관에서는 「80점짜리 답」이 「답 없음」보다 위험하다.
보장 여부와 지급 금액은 민원 · 분쟁으로 직결된다.

이 모듈이 그 자리를 막는다.

    1. 스코프가 잠기기 전에는 검색을 호출하지 않는다   require_locked()
    2. 스코프 밖 결과는 점수가 아무리 높아도 버린다     confine()
    3. 남는 것이 없으면 「해당 조항 없음」으로 끝낸다    ScopeVerdict.NO_CLAUSE

2번이 핵심이다. 벤더 필터를 믿고 넘기지 않고 **받은 결과를 우리 쪽에서 한 번 더 건다.**
필터가 없거나 헐거우면 다른 상품 조항이 그대로 답변에 실리기 때문이다.

## 되묻지 말고 미리 고르게 한다

1단계를 화면으로 풀 때, 「AI가 되묻는다」보다 **「사용자가 미리 고른다」**가 낫다.
질문이 들어오는 순간 이미 1권으로 좁혀져 있으면 「찾기」 문제 자체가 사라진다.
보험사는 쳐도 되고 누르면 목록이 나열되며, 상품은 검색창에 치면 매칭된다.

    설계사   보험사 → 상품 검색 → (판)          클릭 · 타이핑 2~3번
    고객     계약 연동 → 증권 선택              클릭 0회 (2차)

되묻기(`clarify.py`)는 이 선택을 건너뛰고 바로 물었을 때의 **보완 경로**이지
기본 경로가 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InsuranceLine(Enum):
    """보종. **선택 단계가 아니라 상품 마스터의 분류 속성이다.**

    v1 화면에서는 보험사 → 상품 검색으로 바로 가고 보종을 묻지 않는다.
    상품 검색 결과에 붙는 꼬리표와 목록 필터로만 쓴다.
    """

    LONG_TERM = "long_term"
    """장기 — 건강 · 상해 · 어린이 · 간병 등. 보상 질문이 가장 많이 나온다."""

    AUTO = "auto"
    """자동차."""

    GENERAL = "general"
    """일반 — 화재 · 배상책임 등."""

    INTEGRATED = "integrated"
    """통합."""

    RETIREMENT = "retirement"
    """퇴직연금."""


LINE_LABELS = {
    InsuranceLine.LONG_TERM: "장기",
    InsuranceLine.AUTO: "자동차",
    InsuranceLine.GENERAL: "일반",
    InsuranceLine.INTEGRATED: "통합",
    InsuranceLine.RETIREMENT: "퇴직연금",
}


class ScopeLevel(Enum):
    """얼마나 좁혀졌는가. 순서가 곧 선택 단계다."""

    NONE = 0
    INSURER = 1
    PRODUCT = 2
    EDITION = 3
    """판까지 확정됐다. **여기서만 검색을 건다.**"""


#: 각 단계에서 다음에 고를 것.
_NEXT_STEP = {
    ScopeLevel.NONE: "보험사",
    ScopeLevel.INSURER: "상품",
    ScopeLevel.PRODUCT: "가입 시점(판)",
}


class ScopeNotLocked(RuntimeError):
    """스코프가 잠기지 않은 채 검색을 호출했다.

    예외로 만든 이유는, 이 실수가 **조용히 틀린 답**을 만들기 때문이다.
    호출이 성공해 버리면 다른 상품 조항으로 답하고도 아무도 모른다.
    """


@dataclass(frozen=True)
class TermsScope:
    """지금 어느 약관을 보고 있는지.

    **답변에 항상 이 값을 함께 표시한다.** 어느 약관으로 답했는지 보이지 않으면
    FA는 그 답을 고객에게 옮길 수 없고, 틀렸을 때 무엇이 틀렸는지도 알 수 없다.
    """

    insurer: str = ""
    line: InsuranceLine | None = None
    """보종. 선택 단계가 아니라 상품에 붙는 분류 속성이다. 스코프 수준에 영향이 없다."""
    product_name: str = ""
    product_id: str = ""
    edition_id: str = ""
    edition_label: str = ""
    """「2021.09 시행판」처럼 사람이 읽는 표기."""

    contract_ym: str = ""
    """계약 연 · 월. 판을 정한 근거를 남긴다."""

    @property
    def level(self) -> ScopeLevel:
        if self.edition_id:
            return ScopeLevel.EDITION
        if self.product_id or self.product_name:
            return ScopeLevel.PRODUCT
        if self.insurer:
            return ScopeLevel.INSURER
        return ScopeLevel.NONE

    @property
    def is_locked(self) -> bool:
        """검색을 걸어도 되는 상태인가. **판까지 정해져야 잠긴 것이다.**"""
        return self.level is ScopeLevel.EDITION

    @property
    def next_step(self) -> str | None:
        """다음에 고를 것. 잠겨 있으면 None."""
        return _NEXT_STEP.get(self.level)

    @property
    def key(self) -> tuple[str, str, str]:
        """검색 결과가 이 스코프에 속하는지 판별하는 키."""
        return (self.insurer, self.product_id or self.product_name, self.edition_id)

    @property
    def label(self) -> str:
        """화면에 띄우는 한 줄. 「DB손해보험 · 참좋은동행보험 · 2021.09 시행판」"""
        parts = [p for p in (self.insurer, self.product_name, self.edition_label) if p]
        return " · ".join(parts) if parts else "약관 미지정"

    def with_line(self, line: InsuranceLine) -> TermsScope:
        return TermsScope(
            insurer=self.insurer,
            line=line,
            product_name=self.product_name,
            product_id=self.product_id,
            edition_id=self.edition_id,
            edition_label=self.edition_label,
            contract_ym=self.contract_ym,
        )


def require_locked(scope: TermsScope) -> None:
    """스코프가 잠기지 않았으면 검색을 막는다.

    벤더 호출 직전에 부른다. **막지 않으면 100권을 뒤진 결과가 그대로 답이 된다.**
    """
    if not scope.is_locked:
        raise ScopeNotLocked(
            f"약관이 확정되지 않았습니다 — 다음 단계: {scope.next_step}"
        )


class ScopeVerdict(Enum):
    """스코프로 거른 뒤 남은 상태."""

    FOUND = "found"
    """스코프 안에서 근거를 찾았다."""

    NO_CLAUSE = "no_clause"
    """스코프 안에 해당 조항이 없다. **「없다」이지 「모른다」가 아니다.**

    답변에 「해당 조항 없음」으로 표시한다. 다른 약관 조항으로 대신 답하지 않는다.
    """

    NOT_LOCKED = "not_locked"
    """스코프가 잠기지 않았다. 검색을 걸지 말았어야 한다."""


@dataclass(frozen=True)
class Retrieved:
    """벤더가 돌려준 조각 하나."""

    clause_ref: str
    """「제5조 제2항」처럼 조 · 항 단위 위치."""

    text: str
    score: float
    insurer: str = ""
    product_key: str = ""
    edition_id: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.insurer, self.product_key, self.edition_id)


#: 유사도 하한. 이 아래는 「닮은 것 중 1등」일 뿐이므로 근거로 쓰지 않는다.
DEFAULT_SCORE_FLOOR = 0.35


@dataclass(frozen=True)
class ScopedResult:
    """스코프로 거른 결과. **무엇을 버렸는지도 함께 남긴다.**

    버린 사실을 숨기면 색인 품질이 나빠져도 드러나지 않는다.
    스코프 밖 반환이 계속 나오면 벤더 필터가 동작하지 않는다는 신호다.
    """

    kept: tuple[Retrieved, ...] = ()
    out_of_scope: tuple[Retrieved, ...] = ()
    below_floor: tuple[Retrieved, ...] = ()
    verdict: ScopeVerdict = ScopeVerdict.NO_CLAUSE
    scope: TermsScope = TermsScope()

    @property
    def has_evidence(self) -> bool:
        return self.verdict is ScopeVerdict.FOUND

    def note(self) -> str:
        """운영 로그 · 품질 점검용 한 줄."""
        return (
            f"{self.scope.label} — 채택 {len(self.kept)}"
            f" · 스코프밖 {len(self.out_of_scope)}"
            f" · 점수미달 {len(self.below_floor)}"
        )


def confine(
    hits: list[Retrieved] | tuple[Retrieved, ...],
    scope: TermsScope,
    *,
    score_floor: float = DEFAULT_SCORE_FLOOR,
) -> ScopedResult:
    """검색 결과를 확정된 약관 한 권 안으로 가둔다.

    **벤더 필터를 신뢰하지 않고 받은 쪽에서 한 번 더 건다.** 필터가 없거나
    헐거우면 다른 상품의 조항이 그대로 답변에 실리는데, 약관은 서로 90%가 닮아
    그 사실이 눈에 띄지도 않는다.

    남는 것이 없으면 순위를 낮춰 가며 채우지 않는다. 「해당 조항 없음」이 정답이다.
    """
    if not scope.is_locked:
        return ScopedResult(verdict=ScopeVerdict.NOT_LOCKED, scope=scope)

    kept: list[Retrieved] = []
    out_of_scope: list[Retrieved] = []
    below_floor: list[Retrieved] = []

    for hit in hits:
        if hit.key != scope.key:
            out_of_scope.append(hit)
        elif hit.score < score_floor:
            below_floor.append(hit)
        else:
            kept.append(hit)

    return ScopedResult(
        kept=tuple(sorted(kept, key=lambda h: h.score, reverse=True)),
        out_of_scope=tuple(out_of_scope),
        below_floor=tuple(below_floor),
        verdict=ScopeVerdict.FOUND if kept else ScopeVerdict.NO_CLAUSE,
        scope=scope,
    )


class AnswerBasis(Enum):
    """이 문장이 무엇에 근거했는지. **화면에서 구분해 표시한다.**

    담보 데이터로 답한 것과 약관 원문으로 답한 것을 섞으면,
    외부 데이터가 틀렸을 때 어디까지가 우리 책임인지 가릴 수 없다.
    """

    TERMS = "terms"
    """약관 원문. 조 · 항 위치를 함께 제시한다."""

    COVERAGE_DATA = "coverage_data"
    """보장분석 업체가 준 담보 · 가입금액 데이터. **외부 데이터다.**"""

    GENERAL = "general"
    """보험 일반지식(Micky). 특정 상품에 대한 확정이 아니다."""


BASIS_LABELS = {
    AnswerBasis.TERMS: "약관 원문",
    AnswerBasis.COVERAGE_DATA: "보장 데이터(외부)",
    AnswerBasis.GENERAL: "일반지식",
}


@dataclass(frozen=True)
class CustomerScope:
    """고객 폴더 스코프 — **그 고객의 약관들 안에서만** 찾는다.

    약관북에서 고객 폴더를 열고 질문하면, 검색 범위가 그 고객이 등록한
    약관 집합으로 잠긴다. 단일 스코프(`TermsScope`)가 「한 권」이라면
    이것은 「한 고객의 책장」이다 — 남의 계약 조항이 섞일 자리가 없고,
    담보가 여러 계약에 걸치면 걸리는 계약을 모두 확인할 수 있다.
    """

    customer_id: str
    customer_name: str
    scopes: tuple[TermsScope, ...] = ()

    @property
    def locked(self) -> tuple[TermsScope, ...]:
        """판까지 확정된 약관들. 검색은 이 안에서만 돈다."""
        return tuple(sc for sc in self.scopes if sc.is_locked)

    @property
    def unresolved(self) -> tuple[TermsScope, ...]:
        """판이 아직 정해지지 않은 약관들.

        조용히 빼고 답하면 「그 계약은 확인 안 됐다」는 사실이 사라진다.
        답변에 「미확정 N건 제외」로 밝힌다.
        """
        return tuple(sc for sc in self.scopes if not sc.is_locked)

    @property
    def keys(self) -> frozenset[tuple[str, str, str]]:
        return frozenset(sc.key for sc in self.locked)

    @property
    def is_locked(self) -> bool:
        return bool(self.locked)

    @property
    def label(self) -> str:
        base = f"{self.customer_name} 고객 · 약관 {len(self.locked)}건"
        if self.unresolved:
            base += f" (미확정 {len(self.unresolved)}건 제외)"
        return base


def confine_to_customer(
    hits: list[Retrieved] | tuple[Retrieved, ...],
    customer: CustomerScope,
    *,
    score_floor: float = DEFAULT_SCORE_FLOOR,
) -> ScopedResult:
    """검색 결과를 고객의 약관 집합 안으로 가둔다.

    규칙은 `confine()`과 같다 — 집합 밖은 점수가 높아도 버리고,
    남는 것이 없으면 「해당 조항 없음」으로 끝낸다. 다른 고객의 계약이나
    이 고객이 등록하지 않은 약관의 조항은 근거로 쓰지 않는다.
    """
    if not customer.is_locked:
        return ScopedResult(verdict=ScopeVerdict.NOT_LOCKED)

    allowed = customer.keys
    kept: list[Retrieved] = []
    out_of_scope: list[Retrieved] = []
    below_floor: list[Retrieved] = []

    for hit in hits:
        if hit.key not in allowed:
            out_of_scope.append(hit)
        elif hit.score < score_floor:
            below_floor.append(hit)
        else:
            kept.append(hit)

    return ScopedResult(
        kept=tuple(sorted(kept, key=lambda h: h.score, reverse=True)),
        out_of_scope=tuple(out_of_scope),
        below_floor=tuple(below_floor),
        verdict=ScopeVerdict.FOUND if kept else ScopeVerdict.NO_CLAUSE,
        scope=customer.locked[0] if len(customer.locked) == 1 else TermsScope(),
    )
