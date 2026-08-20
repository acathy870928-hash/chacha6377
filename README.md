# 사업단 뉴스 브리핑

수집된 보험 기사 중에서 **사업단 대표가 고른 것만** 단톡방으로 내보내는 도구입니다.

```
수집기(RSS · URL · 외부 API)
      ↓
우선 검토 후보  ─ 기사 신호 점수 순으로 정렬
      ↓
대표가 체크박스로 선택 + 한 줄 코멘트
      ↓
공유 링크 1개 생성  →  카톡 단톡방에 붙여넣기
      ↓
FA가 링크를 누르면 → 기사 목록 → 제목 누르면 본문
```

기사 페이지에는 **제목과 본문만** 나옵니다. 광고·배너·관련기사 없이 읽기만 됩니다.

## 빠르게 띄워보기

```bash
pip install -r requirements.txt
cp .env.example .env          # ADMIN_PASSWORD, INGEST_API_KEY, PUBLIC_BASE_URL 수정
python3 scripts/seed.py       # 샘플 기사 4건 투입 (화면 확인용)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`http://localhost:8000/admin` 으로 들어가 `.env` 의 `ADMIN_PASSWORD` 로 로그인합니다.

## 화면

| 주소 | 누가 보나 | 내용 |
|---|---|---|
| `/admin` | 사업단 대표 | 우선 검토 후보 목록, 선택, 브리핑 생성 |
| `/admin/share/{code}` | 사업단 대표 | 공유 링크 + 카톡에 붙여넣을 문구 |
| `/admin/briefings` | 사업단 대표 | 지금까지 보낸 브리핑과 조회수 |
| `/b/{code}` | FA (카톡에서 열림) | 기사 목록 |
| `/a/{slug}` | FA (카톡에서 열림) | 제목 + 본문 |

어드민의 **사업단 대표용 / FA용** 탭으로 대상을 나눠서 관리합니다.
`both`(공통)로 들어온 기사는 양쪽 탭에 모두 보입니다.

## 기사 넣는 방법 3가지

### 1. RSS 수집기 (내장)

`feeds.json` 에 매체를 적어두고 돌립니다.

```bash
python3 scripts/collect.py
```

어드민의 **RSS 지금 수집** 버튼도 같은 일을 합니다.
서버에 설치하면 **매일 아침 7시(한국 시간)** 에 자동으로 돕니다 —
대표가 출근해서 볼 때 후보가 쌓여 있도록 잡아둔 시각입니다.
주기를 바꾸려면 `deploy/news-collect.timer` 의 `OnCalendar` 한 줄만 고치면 됩니다.

**등록된 매체**

| 매체 | 기본 대상 | 성격 |
|---|---|---|
| 보험매일 · 보험저널 · 한국보험신문 | 공통 | 업계 일간지 |
| 시사저널e 금융 | 공통 | 금융 일반 |
| 금융위원회 | 대표용 | 보도자료 · 제도/감독 |
| 보건복지부 | 대표용 | 보도자료 · 건강보험/요양 |
| 행정안전부 | 대표용 | 보도자료 · 재난/배상책임 |

매체마다 `audience` 를 정해두면 수집될 때부터 해당 탭으로 들어갑니다.
정부 보도자료는 대표가 챙길 내용이라 `rep` 로 잡아뒀습니다.

**RSS 주소 확인 — 처음 설치하면 이걸 먼저 돌리세요**

```bash
python3 scripts/check_feeds.py --fix
```

매체별로 주소가 살아 있는지 실제로 받아서 확인하고, 틀렸으면 **홈페이지를 뒤져 RSS 주소를 찾아
`feeds.json` 에 써넣습니다.** 정부 사이트처럼 주소를 비워둔 곳도 이 명령으로 채워집니다.
못 찾은 매체는 이름을 알려주니 직접 확인하시면 됩니다.

**요약만 주는 매체**

정부 보도자료는 RSS 가 요약 몇 줄만 줍니다. 이런 매체는 `"summary_only": true` 로 적어두면
원문을 긁으러 가지 않습니다. 기사 페이지에는 **"요약"이라고 표시하고 원문 링크를 크게** 띄웁니다 —
요약을 전문인 것처럼 보여주지 않습니다. (공백 제외 300자 미만이면 요약으로 봅니다.)

RSS 요약이 짧은 일반 매체는 원문 페이지에서 본문을 다시 긁어옵니다.
본문이 안 잡히면 `app/collector.py` 의 `_ARTICLE_HINTS` 에 해당 매체의 패턴을 추가하세요.

### 2. 기사 링크 붙여넣기

어드민 상단 입력창에 기사 URL을 넣으면 제목·본문·발행일·언론사를 자동으로 가져옵니다.
대표가 어디선가 받은 링크를 그대로 넣는 용도입니다.

```bash
# 여러 개를 한 번에
python3 scripts/add_urls.py --audience rep https://... https://...

# seed/pinned_urls.json 에 적어둔 목록을 통째로
python3 scripts/add_urls.py

# 그중 FA용만
python3 scripts/add_urls.py --only fa
```

`seed/pinned_urls.json` 에 **미리 지정해둔 기사 5건**(대표용 3건 · FA용 2건)이 들어 있습니다.
항목마다 `audience` 를 적어두는 구조라, 링크를 추가할 때 대상을 같이 지정하면 됩니다.
서버를 띄운 뒤 위 명령을 한 번 돌리면 제목·본문·언론사·발행일을 가져와 후보로 등록됩니다.

### 3. 기존 수집기 연동 (`POST /api/ingest`)

이미 돌고 있는 수집기가 있으면 여기로 밀어 넣으면 됩니다.

```bash
curl -X POST https://news.example.com/api/ingest \
  -H "X-API-Key: $INGEST_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"articles":[{
        "source_id": "insnews-92282",
        "title": "실손보험 청구 전산화 2단계 시행",
        "body": "기사 본문 전체...",
        "publisher": "한국보험신문",
        "origin_url": "https://www.insnews.co.kr/news/articleView.html?idxno=92282",
        "published_at": "2026-08-20 09:00:00",
        "audience": "rep"
      }]}'
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `title` | ✅ | 기사 제목 |
| `body` | | 본문. 없으면 제목만 나옵니다 |
| `source_id` | | 중복 방지 키. 없으면 `origin_url` 을 씁니다 |
| `publisher` | | 언론사명 |
| `origin_url` | | 원문 주소 |
| `published_at` | | `YYYY-MM-DD HH:MM:SS` |
| `signal` | | 0~99. **안 주면 자동 계산** |
| `audience` | | `rep`(대표용) / `fa`(FA용) / `both`(기본) |

응답: `{"created": 1, "updated": 0, "failed": 0, "errors": []}`

## 기사 신호 점수

수집기가 `signal` 을 주면 그 값을 그대로 씁니다.
안 주면 `app/scoring.py` 가 계산합니다 — 기준은 **"영업 현장에 바로 쓸 수 있는가"** 입니다.

- 보험금·면책·약관·실손·절판·인수기준 → 크게 가산
- 금감원·GA·수수료·불완전판매 → 가산 (대표가 챙겨야 하는 것)
- 보험사기·판결 사례 → 가산 (FA 교육 자료로 쓰기 좋음)
- 봉사·기부·MOU·인사 → 감점 (홍보성 기사)
- 최신 기사일수록 가산, 한 달 넘으면 감점

제목에 걸린 키워드는 본문보다 2배로 칩니다.
가중치는 `HIGH_VALUE` / `REGULATORY` / `CASE` / `NOISE` 딕셔너리에서 바로 고칠 수 있습니다.

후보 목록에는 점수와 함께 **왜 올라왔는지** 키워드가 같이 표시됩니다.

## 카톡에서 잘 보이게 하려면

- `.env` 의 `PUBLIC_BASE_URL` 을 **바깥에서 접속 가능한 실제 주소**로 맞추세요.
  이 값이 공유 링크와 OG 태그에 들어갑니다. `localhost` 로 두면 FA 폰에서 안 열립니다.
- 브리핑·기사 페이지에는 `og:title` / `og:description` 이 들어 있어
  카톡에 링크를 붙이면 제목과 요약이 미리보기로 뜹니다.
- 기사 주소(`/a/xxxxxxxx`)는 짧은 영문 코드입니다.
  한글 제목을 URL에 쓰면 카톡에서 퍼센트 인코딩돼 주소가 길어지기 때문입니다.
- 공유 화면의 **문구 전체 복사** 를 쓰면 제목 목록과 링크가 한 덩어리로 복사됩니다.

## 서버에 올리기

저장소가 비공개라 서버에서 바로 받을 수 없습니다. 소스를 서버에 올린 뒤 실행합니다.

```bash
sudo bash /경로/chacha6377/deploy/install.sh
```

파이썬 환경, nginx, HTTPS 인증서, 자동 재시작, 매일 아침 수집까지 한 번에 잡습니다.
서버 시간대도 한국 시간으로 맞춥니다.
다시 실행해도 **기사 DB(`data/`)와 설정(`.env`)은 건드리지 않습니다** — 갱신용으로도 같은 명령을 씁니다.

토큰이 있으면 서버에서 바로 받아올 수도 있습니다.

```bash
sudo GITHUB_TOKEN=ghp_xxxx bash install.sh
```

서버 준비부터 도메인 연결, 백업, 문제 해결까지는 **[deploy/README.md](deploy/README.md)** 에
윈도우 사용자 기준으로 적어두었습니다.

## 운영 메모

- 데이터는 `DB_PATH`(기본 `./data/news.db`) SQLite 파일 하나에 들어갑니다. 백업은 이 파일만 복사하면 됩니다.
- 어드민은 `ADMIN_PASSWORD` 하나로 잠급니다. 공개 페이지(`/b`, `/a`)는 링크를 아는 사람이면 봅니다 —
  링크가 곧 열쇠이므로 대외비 내용은 넣지 마세요.
- 브리핑별 조회수가 `/admin/briefings` 에 표시됩니다. FA들이 실제로 읽는지 확인용입니다.
- 배포 시에는 리버스 프록시(nginx 등) 뒤에 두고 HTTPS를 붙이세요. 카톡 인앱 브라우저는 http 링크에 경고를 띄웁니다.
