"""미등록 약관 요청 기록과 등록 후보 산정.

약관은 처음부터 전부 등록하지 않는다. 우선 100건 규모로 시작하고,
없는 약관은 역질문으로 **상품명과 가입 시점을 확정한 뒤** 요청으로 남긴다.

역질문을 미등록 상품에도 끝까지 하는 이유가 여기 있다.
상품명만으로는 어느 판을 등록해야 하는지 알 수 없다.
가입 시점까지 받아야 등록 대상이 하나로 정해진다.

## 등록에는 비용이 든다

벤더에 약관을 등록할 때 비용이 발생한다. 따라서 요청이 왔다고 자동으로 등록하지 않는다.

  - 쌓인 요청은 **등록 후보**가 될 뿐이고, 승인 단계를 거친다.
  - 우선순위는 단순 요청 건수가 아니라 **비용 대비 수요**로 정한다.
    판 하나를 등록해 몇 명의 FA가 얼마나 풀리는지가 기준이다.
  - 요청한 FA에게 「등록하겠다」고 약속하지 않는다. 접수와 검토까지만 알린다.

비용 단위는 **판(edition)**이다. 같은 상품이라도 판마다 따로 등록해야 하므로,
실손처럼 판이 많은 상품은 전체 등록이 비현실적이고 요청이 몰린 판만 골라 넣는다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum

from .versioning import ApproxDate


class RequestStatus(Enum):
    """요청 처리 상태. 등록이 유료이므로 접수와 등록 사이에 승인이 있다."""

    RECEIVED = "received"
    """접수됨. 아직 등록 여부가 정해지지 않았다."""

    APPROVED = "approved"
    """등록하기로 승인됨. 비용 집행 대상."""

    REGISTERED = "registered"
    """등록 · 임베딩 완료. 아직 검수 전이므로 알림을 보내지 않는다."""

    VERIFIED = "verified"
    """원 질문으로 검수 통과. 이 시점에 요청자에게 알린다."""

    DECLINED = "declined"
    """등록하지 않기로 함. 사유와 함께 요청자에게 알린다."""

    UNAVAILABLE = "unavailable"
    """약관 자체를 확보할 수 없음(상품 오인, 공시 미존재 등)."""


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
    """원 질문.

    두 가지 용도가 있다.
      1. 등록 후 검수 — 이 질문을 다시 돌려 근거 조항이 실제로 나오는지 확인한다.
      2. 알림 — 「요청하신 약관이 등록되었습니다」만 보내면 FA는 무엇을 물었는지
         기억하지 못한다. 원 질문을 함께 보여 맥락을 복구한다.
    """

    requester_id: str = ""
    """요청한 FA. 등록 완료 시 알림 대상이 되고, 유료 요청이면 청구 대상이다."""

    customer_id: str = ""
    customer_name: str = ""
    """이 약관이 필요한 고객. 등록이 끝나면 이 고객의 약관북 폴더에 들어간다.

    비워져 있으면 등록 후 폴더 배치를 할 수 없으므로,
    고객 컨텍스트가 있는 상담에서는 반드시 채워서 접수한다.
    """

    billable: bool = False
    """이 요청이 요청자 부담인지.

    초기 등록분(회사 부담)에 없는 약관은 요청한 FA가 비용을 부담한다.
    따라서 **접수 전에 비용을 고지하고 동의를 받아야** 한다.
    """

    price: int | None = None
    """고지한 등록 비용. 동의 시점의 금액을 그대로 남긴다(사후 단가 변경과 무관하게)."""

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

    def subscribers(self, key: tuple[str, str, int | None]) -> list[str]:
        """해당 약관을 기다리는 FA 목록. 등록 완료 알림 대상이다.

        같은 FA가 여러 번 물었어도 한 번만 알린다.
        """
        seen: list[str] = []
        for entry in self.entries:
            if entry.key == key and entry.requester_id and entry.requester_id not in seen:
                seen.append(entry.requester_id)
        return seen

    def questions_for(self, key: tuple[str, str, int | None]) -> list[str]:
        """해당 약관으로 답해야 했던 질문들.

        등록 후 검수에 그대로 쓴다. 이 질문들에 근거 조항이 나와야 등록이 끝난 것이다.
        """
        return [e.question for e in self.entries if e.key == key and e.question]

    def pending_keys(self) -> set[tuple[str, str, int | None]]:
        """이미 접수돼 확보가 진행 중인 약관.

        **중복 과금을 막는 데 쓴다.** 같은 약관을 다른 FA가 이미 요청했다면
        두 번째 FA에게 다시 비용을 받지 않는다. 등록된 약관은 전사가 함께 쓰므로
        같은 것을 두 번 사는 셈이 된다.
        """
        return {e.key for e in self.entries}

    def candidates(self) -> list[RegistrationCandidate]:
        """등록 후보. 같은 약관(보험사 + 상품 + 가입 연도)에 대한 요청을 묶는다.

        묶는 단위가 곧 비용 단위다. 판 하나를 등록하면 그 판을 기다린 요청이 함께 풀린다.
        """
        grouped: dict[tuple[str, str, int | None], list[TermsRequest]] = {}
        for entry in self.entries:
            grouped.setdefault(entry.key, []).append(entry)

        result: list[RegistrationCandidate] = []
        for key, entries in grouped.items():
            first = entries[0]
            requesters: list[str] = []
            for entry in entries:
                if entry.requester_id and entry.requester_id not in requesters:
                    requesters.append(entry.requester_id)
            result.append(
                RegistrationCandidate(
                    key=key,
                    product_name=first.product_name,
                    insurer=first.insurer,
                    product_id=first.product_id,
                    edition_label=first.edition_label,
                    contract_year=key[2],
                    request_count=len(entries),
                    requester_count=len(requesters),
                    questions=[e.question for e in entries if e.question],
                )
            )
        return result

    def unresolved_count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class RegistrationCandidate:
    """등록을 검토할 약관 하나. 요청 여러 건이 묶인 결과다."""

    key: tuple[str, str, int | None]
    product_name: str
    insurer: str
    product_id: str | None
    edition_label: str | None
    contract_year: int | None
    request_count: int
    requester_count: int
    questions: list[str]

    @property
    def demand(self) -> int:
        """수요 점수.

        **요청 건수보다 요청한 FA 수를 무겁게 본다.**
        한 사람이 열 번 물어본 것보다 열 사람이 한 번씩 물어본 쪽이
        조직 전체로 더 자주 막히고 있다는 뜻이다.
        요청자 정보가 없는 경우를 대비해 건수도 함께 반영한다.
        """
        return self.requester_count * 3 + self.request_count

    @property
    def is_identified(self) -> bool:
        """상품 마스터에서 식별된 요청인지.

        마스터에도 없는 이름은 오타일 수 있으므로 자동 승인 대상에서 뺀다.
        """
        return self.product_id is not None


def select_within_budget(
    candidates: list[RegistrationCandidate],
    *,
    editions_budget: int,
    min_requesters: int = 2,
) -> tuple[list[RegistrationCandidate], list[RegistrationCandidate]]:
    """예산 안에서 등록할 후보를 고른다. (승인, 보류) 순으로 돌려준다.

    등록이 유료이므로 두 단계로 거른다.

      1. **최소 수요 미달은 제외한다.** 요청자가 `min_requesters`명 미만이면
         비용을 들일 근거가 약하다. 오타로 들어온 이름도 여기서 걸린다.
      2. 남은 후보를 수요 순으로 예산만큼 담는다.

    판 하나당 비용이 같다고 보므로 예산은 판 수로 센다.
    단가가 상품 · 판에 따라 다르면 이 함수 대신 비용을 인자로 받는 형태로 바꾼다.
    """
    eligible = [
        c for c in candidates if c.requester_count >= min_requesters and c.is_identified
    ]
    held = [c for c in candidates if c not in eligible]

    eligible.sort(key=lambda c: (-c.demand, c.product_name))
    approved = eligible[:editions_budget]
    held.extend(eligible[editions_budget:])

    held.sort(key=lambda c: (-c.demand, c.product_name))
    return approved, held
