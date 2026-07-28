"""페르소나 조립 스크립트.

registry.yaml 을 읽어 base + role 을 하나의 system prompt 로 합칩니다.
런타임 컨텍스트(고객 정보, RAG 결과)는 여기에 넣지 않습니다 —
프롬프트 캐시를 유지하려면 messages 쪽에 넣어야 합니다.

사용:
    python examples/build_persona.py claims
    python examples/build_persona.py --list
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "personas" / "registry.yaml"


@dataclass
class Persona:
    key: str
    name: str
    audience: str
    system_prompt: str
    model: str
    effort: str
    max_tokens: int
    pii_masking: bool
    output_guard: str | None
    banned_phrases: list[str]

    @property
    def is_internal(self) -> bool:
        return self.audience == "internal"


def load_registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_registry_keys(registry: dict) -> list[str]:
    return list(registry["personas"])


def build(key: str) -> Persona:
    registry = load_registry()

    try:
        spec = registry["personas"][key]
    except KeyError:
        available = ", ".join(list_registry_keys(registry))
        raise SystemExit(f"알 수 없는 페르소나: {key!r} (사용 가능: {available})") from None

    base_text = (REPO_ROOT / registry["base"]).read_text(encoding="utf-8")
    role_text = (REPO_ROOT / spec["file"]).read_text(encoding="utf-8")

    # 조립 순서: base → role. 런타임 컨텍스트는 messages 로 별도 주입.
    system_prompt = "\n\n---\n\n".join([base_text.strip(), role_text.strip()])

    return Persona(
        key=key,
        name=spec["name"],
        audience=spec["audience"],
        system_prompt=system_prompt,
        model=spec["model"],
        effort=spec["effort"],
        max_tokens=spec["max_tokens"],
        pii_masking=spec.get("pii_masking", True),
        output_guard=spec.get("output_guard"),
        banned_phrases=registry.get("banned_phrases", []),
    )


def check_banned_phrases(persona: Persona, text: str) -> list[str]:
    """응답 후처리 검사. output_guard 가 strict 인 페르소나에서 호출하세요."""
    if persona.output_guard != "strict":
        return []
    return [p for p in persona.banned_phrases if p in text]


def main() -> int:
    parser = argparse.ArgumentParser(description="보험 AI 페르소나 조립")
    parser.add_argument("persona", nargs="?", help="페르소나 키 (예: consultant)")
    parser.add_argument("--list", action="store_true", help="사용 가능한 페르소나 목록")
    args = parser.parse_args()

    if args.list or not args.persona:
        registry = load_registry()
        for key, spec in registry["personas"].items():
            scope = "사내 전용" if spec["audience"] == "internal" else "고객 대면"
            print(f"{key:<14} {spec['name']}  [{scope}]")
        return 0

    persona = build(args.persona)
    if persona.is_internal:
        print("# ⚠️ 사내 전용 페르소나입니다. 고객 채널에 배포하지 마세요.\n", file=sys.stderr)
    print(persona.system_prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
