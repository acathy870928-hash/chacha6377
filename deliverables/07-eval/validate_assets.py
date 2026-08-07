"""산출물 정합성 검증.

파일들이 서로를 참조하므로(고지 ID, 금지규칙 ID 등) 한쪽만 고치면
조용히 어긋난다. 이 스크립트는 참조 무결성을 전수 검사한다.

CI에 걸어두면 지식베이스 갱신 시 깨진 참조를 배포 전에 잡을 수 있다.

실행:
    python3 validate_assets.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPLIANCE = ROOT / "04-compliance"
KB = ROOT / "03-knowledge-base"
EVAL = ROOT / "07-eval"

errors: list[str] = []
warnings: list[str] = []


def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{p.name}: JSON 파싱 실패 — {e}")
        return {}


def load_jsonl(p: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"{p.name}:{i}: JSONL 파싱 실패 — {e}")
    return rows


def check_regex_compiles(forbidden: dict) -> None:
    """모든 정규식이 컴파일되는지 확인한다."""
    for rule in forbidden.get("rules", []):
        for pat in rule.get("patterns", []):
            try:
                re.compile(pat)
            except re.error as e:
                errors.append(f"{rule['id']}: 정규식 컴파일 실패 {pat!r} — {e}")


def check_rule_ids_unique(forbidden: dict, disclosures: dict) -> None:
    for name, items, key in [
        ("금지표현", forbidden.get("rules", []), "id"),
        ("필수고지", disclosures.get("disclosures", []), "id"),
    ]:
        ids = [x[key] for x in items]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            errors.append(f"{name}: 중복 ID {sorted(dupes)}")


def check_redteam_references(redteam: list[dict], forbidden: dict) -> None:
    """레드팀 케이스가 참조하는 금지규칙 ID가 실재하는지 확인한다."""
    valid = {r["id"] for r in forbidden.get("rules", [])}
    for case in redteam:
        ref = case.get("related_rule", "")
        for rid in re.findall(r"FB-\d{3}", ref):
            if rid not in valid:
                errors.append(f"{case['id']}: 존재하지 않는 규칙 참조 {rid}")


def check_golden_disclosure_refs(golden: list[dict], disclosures: dict) -> None:
    valid = {d["id"] for d in disclosures.get("disclosures", [])}
    for case in golden:
        blob = json.dumps(case.get("rubric", {}), ensure_ascii=False)
        for did in re.findall(r"DISC-\d{3}", blob):
            if did not in valid:
                errors.append(f"{case['id']}: 존재하지 않는 고지 참조 {did}")


def check_calc_disclosure_refs(disclosures: dict) -> None:
    """pension_calc.py가 참조하는 고지 ID가 실재하는지 확인한다."""
    calc = ROOT / "06-tools" / "pension_calc.py"
    if not calc.exists():
        warnings.append("pension_calc.py 없음 — 건너뜀")
        return
    valid = {d["id"] for d in disclosures.get("disclosures", [])}
    for did in set(re.findall(r'"(DISC-\d{3})"', calc.read_text(encoding="utf-8"))):
        if did not in valid:
            errors.append(f"pension_calc.py: 존재하지 않는 고지 참조 {did}")


def check_redteam_completeness(redteam: list[dict]) -> None:
    required = {"id", "category", "utterance", "expected_behavior", "severity"}
    for case in redteam:
        missing = required - case.keys()
        if missing:
            errors.append(f"{case.get('id', '?')}: 필수 필드 누락 {sorted(missing)}")
        if not case.get("must_not_contain") and not case.get("must_contain_any"):
            warnings.append(
                f"{case.get('id')}: 자동 채점 기준(must_*)이 없어 수동 평가만 가능"
            )


def check_critical_coverage(redteam: list[dict], forbidden: dict) -> None:
    """BLOCK 등급 금지규칙마다 레드팀 케이스가 있는지 확인한다."""
    block_rules = {
        r["id"] for r in forbidden.get("rules", []) if r["severity"] == "BLOCK"
    }
    covered = set()
    for case in redteam:
        covered |= set(re.findall(r"FB-\d{3}", case.get("related_rule", "")))
    uncovered = block_rules - covered
    if uncovered:
        warnings.append(
            f"레드팀 케이스가 없는 BLOCK 규칙: {sorted(uncovered)} — 케이스 추가 권장"
        )


def check_statistics_expiry() -> None:
    """만료된 통계가 있는지 확인한다 (간이 파서 — PyYAML 없이 동작)."""
    stats = KB / "statistics.yaml"
    if not stats.exists():
        warnings.append("statistics.yaml 없음 — 건너뜀")
        return
    text = stats.read_text(encoding="utf-8")
    today = date.today()
    expired = []
    current_id = None
    for line in text.splitlines():
        m_id = re.search(r"id:\s*(STAT-[\w-]+|ASSUM-\d+)", line)
        if m_id:
            current_id = m_id.group(1)
        m_exp = re.search(r'expires_at:\s*"(\d{4}-\d{2}-\d{2})"', line)
        if m_exp:
            exp = date.fromisoformat(m_exp.group(1))
            if exp < today:
                expired.append((current_id, m_exp.group(1)))
    for sid, when in expired:
        errors.append(f"통계 만료: {sid} (expires_at={when}) — 갱신 필요")
    if not expired:
        print(f"  통계 만료 항목 없음 (기준일 {today})")


def check_compliance_approval(forbidden: dict, disclosures: dict) -> None:
    for name, doc in [("금지표현", forbidden), ("필수고지", disclosures)]:
        if not doc.get("meta", {}).get("compliance_approved"):
            warnings.append(
                f"{name}: compliance_approved=false — 준법감시인 승인 전에는 배포 불가"
            )


def main() -> int:
    print("=" * 64)
    print("산출물 정합성 검증")
    print("=" * 64)

    forbidden = load_json(COMPLIANCE / "forbidden-expressions.json")
    disclosures = load_json(COMPLIANCE / "required-disclosures.json")
    redteam = load_jsonl(EVAL / "redteam-cases.jsonl")
    golden = load_jsonl(EVAL / "golden-dataset.jsonl")

    print(f"\n로드: 금지규칙 {len(forbidden.get('rules', []))}건, "
          f"필수고지 {len(disclosures.get('disclosures', []))}건, "
          f"레드팀 {len(redteam)}건, 골든 {len(golden)}건")

    print("\n검사 중...")
    check_regex_compiles(forbidden)
    check_rule_ids_unique(forbidden, disclosures)
    check_redteam_references(redteam, forbidden)
    check_golden_disclosure_refs(golden, disclosures)
    check_calc_disclosure_refs(disclosures)
    check_redteam_completeness(redteam)
    check_critical_coverage(redteam, forbidden)
    check_statistics_expiry()
    check_compliance_approval(forbidden, disclosures)

    print("\n" + "-" * 64)
    if errors:
        print(f"❌ 오류 {len(errors)}건")
        for e in errors:
            print(f"   • {e}")
    else:
        print("✅ 오류 없음")

    if warnings:
        print(f"\n⚠️  경고 {len(warnings)}건")
        for w in warnings:
            print(f"   • {w}")

    print("=" * 64)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
