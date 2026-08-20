# 업무 플로우 진행 상황 챗봇

조기 퇴근하거나 자리를 비운 뒤에도 **"내 업무가 지금 어느 단계까지 갔는지"** 를 챗봇에게 물어보고, 필요하면 진행 상태를 바로 기록할 수 있게 만든 도구입니다.

- 답변 엔진: **Claude API** (도구 호출 방식 — 모든 사실은 DB 조회 결과로만 답합니다)
- 데이터: **앱 자체 SQLite DB** (외부 시스템 연동 없이 바로 동작)
- 사용 창구: **Microsoft Teams 봇** + **웹 UI** (Teams 승인 전에도 웹으로 바로 사용)

```
        Teams 앱 ─┐
                  ├─→ Express 서버 ─→ Claude (도구 호출) ─→ SQLite (업무·단계·이력)
        웹 UI  ───┘
```

## 무엇을 물어볼 수 있나

| 질문 | 챗봇이 하는 일 |
|---|---|
| `오늘 현황 알려줘` | 진행중·지연·오늘/이번주 마감 건수와 지금 손대야 할 목록 |
| `A사 계약 건 어디까지 갔어?` | 전체 단계 중 현재 위치, 담당자, 진행률, 지연 여부, 최근 이력 |
| `내가 퇴근한 뒤에 바뀐 거 있어?` | 지정 시점 이후의 모든 변경 이력 |
| `지연된 업무만 보여줘` | 마감이 지난 진행중 업무 |
| `노트북 발주 건 팀장 승인 완료로 바꿔줘` | 단계 상태 변경 + 다음 단계 자동 착수 |
| `C사 NDA 건 새로 등록해줘` | 표준 플로우 템플릿대로 단계 생성 |

업무를 애매하게 부르면(`그 계약 건`) 후보를 보여주고 어느 건인지 되묻습니다. 기록에 없는 내용은 지어내지 않고 "기록에 없습니다"라고 답하도록 지시돼 있습니다.

## 빠른 시작

```bash
npm install
cp .env.example .env        # ANTHROPIC_API_KEY 입력
npm run db:seed             # 샘플 플로우 4종 + 예시 업무 5건
npm run dev                 # http://127.0.0.1:3978
```

API 키 없이 DB·도구 계층만 확인하려면:

```bash
npm run selftest            # 임시 DB로 15개 항목 점검 (실제 데이터 건드리지 않음)
```

## 데이터 구조

| 테이블 | 역할 |
|---|---|
| `flow_templates` / `flow_template_steps` | 업무 유형별 표준 플로우와 단계별 표준 소요일(SLA) |
| `tasks` | 개별 업무 건 (담당자, 요청자, 마감일, 우선순위, 상태) |
| `task_steps` | 그 업무의 실제 단계별 상태 (대기/진행중/완료/보류/생략) |
| `task_events` | 모든 변경 이력 — "자리 비운 사이 뭐가 바뀌었나"의 근거 |

샘플로 들어가는 표준 플로우: **신규 계약 검토 · 구매 발주 · 월간 정산 · 고객 이슈 대응**.
실제 업무에 맞게 `src/db/seed.ts` 의 `TEMPLATES` 를 고치고 `npm run db:reset` 하면 됩니다.

동작 규칙 두 가지:
- 어떤 단계를 **완료**로 바꾸면 다음 대기 단계가 자동으로 진행중이 되고, 모든 단계가 끝나면 업무도 완료 처리됩니다.
- **현재 단계**는 "아직 끝나지 않은 가장 앞선 단계"입니다. 보류된 단계가 있으면 그 단계가 현재 위치로 잡힙니다.

## 챗봇이 쓰는 도구 (9개)

`get_work_summary` · `list_tasks` · `get_task_progress` · `get_recent_activity` · `list_flow_templates` · `create_task` · `update_step_status` · `update_task_status` · `add_note`

정의는 `src/chat/tools.ts` 한 곳에 모여 있습니다. 도구를 추가하면 챗봇이 바로 쓸 수 있습니다.

## Teams 연결

`teams-app/README.md` 의 5단계를 따라 Azure Bot 등록 → 메시징 엔드포인트(`https://<서버>/api/messages`) 설정 → 앱 패키지 업로드를 하면 됩니다.
`MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD` 가 비어 있으면 Teams 엔드포인트는 자동으로 비활성되고 웹 UI만 동작합니다.

Teams에서는 `초기화`(대화 맥락 비우기), `도움말` 명령을 쓸 수 있습니다.

## 접근 제어

- 웹 UI/API는 기본적으로 **127.0.0.1 접속만** 허용합니다.
- 사내망 등에 열려면 `.env` 에 `BOT_WEB_ACCESS_TOKEN` 을 설정하고 `BOT_HOST=0.0.0.0` 으로 띄운 뒤, `http://<서버>:3978/?token=<토큰>` 으로 접속하세요. (토큰은 브라우저에 저장됩니다.)
- Teams 엔드포인트는 Bot Framework 가 서명한 요청만 통과합니다.

업무 데이터가 담기는 서비스이므로, 사외에 노출할 때는 HTTPS 종단(리버스 프록시)과 사내 인증을 앞에 두는 것을 권합니다.

## 명령어

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버 (파일 변경 시 자동 재시작) |
| `npm run build` / `npm start` | 빌드 후 실행 |
| `npm run db:seed` | 샘플 데이터 추가 (기존 업무가 있으면 건너뜀) |
| `npm run db:reset` | 전체 초기화 후 샘플 재생성 |
| `npm run selftest` | API 키 없이 도구 계층 점검 |
| `npm run typecheck` | 타입 검사 |

## 설정값

전부 `.env` 로 조정합니다 (`.env.example` 참고). 자주 건드릴 만한 것:

- `BOT_DEFAULT_OWNER` — "내 업무"의 기본 담당자. DB의 `owner` 값과 맞춰야 합니다.
- `BOT_EFFORT` — `low`(기본, 빠르고 저렴) / `medium` / `high`. 단순 조회 위주면 `low` 로 충분합니다.
- `BOT_MAX_HISTORY_TURNS` — 대화 맥락 유지 턴 수.

## 알려진 사항

- `botbuilder` 가 의존하는 `uuid` 구버전 때문에 `npm audit` 에 moderate 경고 7건이 뜹니다. Microsoft 공식 SDK의 전이 의존성이라 직접 고칠 수 없고, Teams를 쓰지 않는다면 `botbuilder` 를 빼도 나머지는 그대로 동작합니다.
- 대화 맥락은 메모리에만 있어 서버를 재시작하면 초기화됩니다. 업무 데이터는 SQLite에 영구 저장됩니다.
