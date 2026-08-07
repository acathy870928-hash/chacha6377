# 보험 상담 챗봇

Claude(Opus 5) 기반 보험사 고객 상담 챗봇입니다. FastAPI 백엔드에서 SSE 스트리밍과
툴 사용(tool use)을 처리하고, 정적 웹 채팅 UI를 함께 제공합니다.

## 기능

| 기능 | 구현 |
|---|---|
| 약관·상품·FAQ Q&A | `search_policy` 툴로 근거 문서를 검색한 뒤 답변 (환각 방지) |
| 보험료 견적 | `calculate_premium` 툴로 결정론적 계산 (모델이 암산하지 않음) |
| 보험금 청구 안내 | `get_claim_guide` 툴로 유형별 서류·절차·처리기간 안내 |
| 보유 계약 조회 | `lookup_contract` 툴 (데모용 목업 데이터) |
| 상담원 연결 | `escalate_to_agent` 툴로 티켓 발급 |
| 상품 목록 | `list_products` 툴 |

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY 입력 (없어도 실행됩니다)
python -m app.main            # 또는: uvicorn app.main:app --reload
```

브라우저에서 http://localhost:8000 접속.

> **API 키가 없으면** 규칙 기반 폴백 모드로 동작합니다. 키워드 매칭 + 동일한 툴 로직을
> 사용하므로 자연어 이해력은 제한적이지만 전체 흐름(스트리밍 UI, 지식 검색, 보험료 계산)은
> 그대로 시연·테스트할 수 있습니다. 상단 배지에서 현재 모드를 확인할 수 있습니다.

## 테스트

```bash
pytest          # 43 passed — API 키 없이 실행됩니다
```

## 구조

```
app/
  main.py        FastAPI 라우트, SSE 스트리밍 응답
  chat.py        Claude 대화 루프 (스트리밍 + 툴 수동 루프)
  fallback.py    API 키 없을 때 쓰는 규칙 기반 엔진
  tools.py       툴 스키마 + 실행 로직 (순수 함수, 단독 테스트 가능)
  knowledge.py   약관·FAQ 검색 (키워드 + 문자 n-gram 스코어링)
  prompts.py     시스템 프롬프트 (캐싱을 위해 요청마다 불변)
  sessions.py    인메모리 세션 저장소 (TTL·용량 제한, 안전한 이력 절단)
  config.py      환경 변수 설정
  data/          상품·FAQ·청구안내·계약 목업 데이터 (JSON)
static/          채팅 웹 UI (의존성 없는 순수 HTML/CSS/JS)
tests/           pytest
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/chat` | `{session_id, message}` → SSE 스트림 |
| `POST` | `/api/reset` | `{session_id}` → 대화 이력 삭제 |
| `GET` | `/api/health` | 상태 및 현재 모드(claude/fallback) |
| `GET` | `/api/products` | 상품 목록 |

SSE 이벤트 형태:

```jsonc
{"type": "text",        "text": "응답 조각"}
{"type": "tool_use",    "name": "calculate_premium", "input": {...}}
{"type": "tool_result", "name": "calculate_premium", "is_error": false}
{"type": "done"}
{"type": "error",       "message": "사용자에게 보여줄 메시지"}
```

## 설정

| 환경 변수 | 기본값 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (없음) | 없으면 폴백 모드 |
| `CHATBOT_MODEL` | `claude-opus-5` | 사용 모델 |
| `CHATBOT_EFFORT` | `low` | `low`/`medium`/`high`/`xhigh`/`max` |
| `CHATBOT_MAX_TOKENS` | `8000` | 응답 최대 토큰 |
| `CHATBOT_MAX_TOOL_ROUNDS` | `6` | 한 턴에 허용할 툴 호출 라운드 수 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 서버 바인딩 |

## 구현 노트

- **스트리밍 + 툴**: SDK의 `tool_runner` 대신 수동 루프를 사용합니다. 툴 호출을 UI에
  실시간으로 노출하고 라운드 수를 직접 제한하기 위해서입니다.
- **effort**: 챗봇은 지연이 중요하므로 기본값을 `low`로 두었습니다. Opus 5는 낮은
  effort에서도 품질이 충분하며, 복잡한 상담 위주라면 `medium`으로 올리세요.
- **프롬프트 캐싱**: 시스템 프롬프트에 `cache_control`을 걸어 툴 정의와 함께 캐싱합니다.
  프롬프트에 날짜·세션 ID 같은 가변 값을 넣으면 캐시가 깨집니다.
- **이력 절단**: `tool_use` 블록과 짝이 되는 `tool_result`가 분리되면 API가 400을
  반환하므로, 세션 절단은 항상 사용자 텍스트 메시지 경계에서만 수행합니다.
- **thinking**: Opus 5는 thinking이 기본 활성이며 응답 content를 (thinking 블록 포함)
  변형 없이 그대로 이력에 되돌려 줍니다.

## 실서비스 적용 전 반드시 필요한 작업

이 저장소는 데모/프로토타입입니다. 다음은 구현되어 있지 않습니다.

- **본인인증**: `lookup_contract`가 모델이 넘긴 이름·생년월일을 그대로 신뢰합니다.
  실제로는 인증된 세션에서 얻은 고객 ID로만 조회해야 하며, 모델 입력을 신뢰하면 안 됩니다.
- **데이터 소스**: 상품·약관·FAQ·계약이 모두 JSON 목업입니다. 실제 약관 DB/기간계 연동 필요.
- **세션 저장소**: 프로세스 메모리에만 저장됩니다. Redis 등으로 교체하고 개인정보 보관
  정책에 맞춘 TTL·암호화가 필요합니다.
- **감사 로그·컴플라이언스**: 상담 내용 보관, 불완전판매 방지 문구, 금융 규제 검토 필요.
- **레이트 리밋 / 인증**: `/api/chat`에 인증과 호출 제한이 없습니다.
