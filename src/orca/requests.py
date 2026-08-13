"""미등록 약관 요청 기록.

약관은 처음부터 전부 등록하지 않는다. 우선 100건 규모로 시작하고,
없는 약관은 역질문으로 **상품명과 가입 시점을 확정한 뒤** 요청으로 남긴다.

역질문을 미등록 상품에도 끝까지 하는 이유가 여기 있다.
상품명만으로는 어느 판을 등록해야 하는지 알 수 없다.
가입 시점까지 받아야 등록 대상이 하나로 정해진다.

쌓인 요청은 빈도순으로 다음 등록 배치의 우선순위가 된다.
즉 등록 목록이 추측이 아니라 실제 FA 수요로 정해진다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .versioning import ApproxDate


@dataclass(frozen=True)
class TermsRequest:
    """등록되지 않은 약관에 대한 조회 요청 한 건."""

    product_name: str
    insurer: str = ""
    product_id: str | None = None
    """상품 마스터에 있으나 인덱스에 없는 경우에만 채워진다.
    마스터에도 없으면 None이고, product_name은 FA가 말한 이름 그대로다."""

    contract_date: ApproxDate | None = None
    edition_label: str | None = None
    """판이 특정된 경우 그 판. 등록 요청 시 어느 판인지 지정하는 데 쓴다."""

    question: str = ""
    """원 질문. 어떤 맥락에서 필요했는지 남긴다."""

    @property
    def key(self) -> tuple[str, str, int | None]:
        """집계 기준: 상품 + 가입 연도.

        같은 상품이라도 가입 연도가 다르면 필요한 판이 다를 수 있어 함께 묶는다.
        """
        name = self.product_id or self.product_name
        return (self.insurer, name, self.contract_date.year if self.contract_date else None)


@dataclass
class RequestLog:
    """요청 누적. 다음 등록 배치를 정하는 근거가 된다.

    운영에서는 DB에 남기고, 여기서는 집계 규칙만 정의한다.
    """

    entries: list[TermsRequest] = field(default_factory=list)

    def record(self, request: TermsRequest) -> None:
        self.entries.append(request)

    def priorities(self, limit: int | None = None) -> list[tuple[TermsRequest, int]]:
        """요청이 많은 순으로 (대표 요청, 건수). 다음에 등록할 약관 목록.

        건수가 같으면 먼저 요청된 것을 앞에 둔다(오래 막혀 있던 것 우선).
        """
        counts = Counter(entry.key for entry in self.entries)
        representative: dict[tuple, TermsRequest] = {}
        order: dict[tuple, int] = {}
        for index, entry in enumerate(self.entries):
            if entry.key not in representative:
                representative[entry.key] = entry
                order[entry.key] = index

        ranked = sorted(counts.items(), key=lambda item: (-item[1], order[item[0]]))
        result = [(representative[key], count) for key, count in ranked]
        return result[:limit] if limit else result

    def unresolved_count(self) -> int:
        return len(self.entries)
