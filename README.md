# 인슈어런스 AI 페르소나 (Insurance AI Persona)

보험 도메인 AI 어시스턴트의 페르소나를 설계·구현·검증하기 위한 키트입니다.
설정 방법 문서와 바로 쓸 수 있는 페르소나 프롬프트, 실행 예제를 함께 담았습니다.

## 빠르게 시작하기

```bash
pip install anthropic pyyaml
export ANTHROPIC_API_KEY=...

# 사용 가능한 페르소나 확인
python examples/build_persona.py --list

# 조립된 시스템 프롬프트 확인
python examples/build_persona.py claims

# 실제 호출
python examples/run_agent.py --persona claims --input "청구할 때 서류 뭐가 필요한가요?"
```

## 구조

```
docs/
  01-persona-setup-guide.md    설정 방법 — 여기부터 읽으세요
  02-guardrails.md             금지 사항의 근거와 대체 행동
  03-evaluation-checklist.md   배포 전 평가 시나리오
personas/
  _base.md                     공통 베이스 (규제·금지·에스컬레이션)
  consultant.md                상담 안내 — 고객 대면
  claims.md                    보험금 청구·보상 안내 — 고객 대면
  underwriting.md              인수심사 보조 — 사내 전용
  registry.yaml                페르소나 메타 + 런타임 설정 + 금칙어
examples/
  build_persona.py             base + role 조립
  run_agent.py                 Claude API 호출 예제
```

## 설계 원칙 요약

**3레이어 구조** — 베이스(공통 규제) + 역할(업무별 권한) + 런타임 컨텍스트(고객/문서).
앞의 두 레이어는 매 요청 동일하므로 프롬프트 캐시가 걸립니다. 런타임 컨텍스트를
시스템 프롬프트에 섞으면 캐시가 깨지므로 `messages` 쪽에 넣습니다.

**금지 사항이 핵심** — 보험은 규제 산업입니다. "무엇을 말하지 않는가"를 먼저 확정하고
각 금지에 대해 대체 행동을 짝으로 정의합니다. 대표적으로:

- 가입 권유·추천 금지 (모집 행위)
- 지급 여부·심사 결과 확답 금지
- 고지의무 축소 안내 금지
- 보장 설명 시 면책·한도·자기부담금 동반 안내

**프롬프트만으로 강제하지 않는다** — 필수 면책 문구 첨부, 금칙어 검사, 개인정보 마스킹은
애플리케이션 후처리에서 처리합니다. `registry.yaml`의 `banned_phrases`와
`run_agent.py`의 후처리 블록을 참고하세요.

**배포 전 평가 필수** — 압박 테스트("그냥 나올지만 말해줘"), 역할 이탈 유도,
자료 없는 질문에 대한 환각 검증을 통과해야 합니다. 모델을 교체할 때도 전량 재실행합니다.

자세한 내용은 [`docs/01-persona-setup-guide.md`](docs/01-persona-setup-guide.md)를 참고하세요.

## 주의

- `personas/underwriting.md`는 **사내 전용**입니다. 고객 채널에 배포하지 마세요.
- 이 레포의 규제 관련 문구는 설계 참고용입니다. 실제 적용 전 사내 컴플라이언스 검토를 거치세요.
- 약관·지침이 개정되면 페르소나 파일을 갱신하고 평가를 재실행하세요.
