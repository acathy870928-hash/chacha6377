# 보험 제도 변경 뉴스 파이프라인

보험 뉴스에서 **상품 홍보·기업 소식을 걷어내고 제도·정책 변경 기사만** 추려
챗봇에 넣을 마크다운으로 만드는 도구입니다.

```
 1단계 수집          2단계 담당자 확인          3단계 MD 변환
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ RSS·보도자료 │ → │ 웹 UI 에서        │ → │ output/articles  │
│ 자동 1차 분류│   │ 승인 / 반려 / 수정│   │ index · bundle   │
└──────────────┘   └──────────────────┘   └──────────────────┘
   collect              review                  export
```

자동 분류는 어디까지나 **초벌**입니다. MD로 나가는 건 담당자가 승인한 기사뿐이고,
자동 제외된 기사도 검수 화면에 남아 언제든 되살릴 수 있습니다.

---

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 바로 돌려보기

네트워크 없이 전 과정을 확인할 수 있는 샘플이 들어 있습니다.

```bash
python -m src.cli seed      # 샘플 10건 적재 (제도 7 / 홍보 3)
python -m src.cli review    # http://127.0.0.1:5000 에서 검수
python -m src.cli export    # 승인 건만 output/ 에 마크다운으로
```

결과 예시는 [`examples/output/`](examples/output/) 에 있습니다.

---

## 1단계 · 기사 수집

```bash
python -m src.cli collect                  # 전체 소스 수집
python -m src.cli collect --source 보험신보  # 특정 소스만
python -m src.cli collect --no-body        # 본문 원문은 안 받고 요약만 (빠름)
python -m src.cli doctor                   # 소스 URL·선택자 점검
```

수집 대상은 [`config/sources.yaml`](config/sources.yaml) 에서 켜고 끕니다.
보험 전문지 RSS와 금융위·금감원 보도자료 목록이 기본으로 들어 있습니다.
언론사 사이트가 개편되면 RSS 주소가 바뀌므로, 처음 세팅할 때 `doctor` 로 먼저 확인하세요.

수집된 기사는 `data/articles.json` 한 파일에 쌓이고, 아래 규칙으로 1차 분류됩니다.

| 판정 | 뜻 | 예 |
|---|---|---|
| **검수 대기** | 제도 뉴스 후보 | "금융위, 보험업법 시행령 개정안 입법예고" |
| **자동제외(홍보)** | 상품 출시·이벤트·수상·인사 | "○○생명, 신상품 출시…가입 시 경품 증정" |
| **자동제외(관련성)** | 제도와 무관 | 시황·연예·부고 |

판정 기준:

- **제도 점수** — `보험업법`, `시행령`, `감독규정`, `입법예고`, `1200%룰`, `5세대 실손` 등에 가중치
- **홍보 점수** — `출시`, `이벤트`, `경품`, `사은품`, `수상`, `봉사활동`, `MOU` 등에 가중치
- 제목은 본문보다 2배 가중
- 홍보 점수가 높아도 **제도 점수가 확실히 앞서면 살립니다**
  (예: "◇◇생명, 표준약관 개정 반영해 실손 전환 안내" → 검수 대기)
- 금융위·금감원 보도자료는 `always_review: true` 라 홍보 필터를 아예 태우지 않습니다

키워드와 임계값은 전부 [`config/filters.yaml`](config/filters.yaml) 에 있습니다.
운영하면서 오분류가 보이면 이 파일만 고치면 됩니다.

## 2단계 · 담당자 확인

```bash
python -m src.cli review              # http://127.0.0.1:5000
python -m src.cli review --port 8080
```

- **상태 탭** — 검수 대기 / 승인 / 반려 / 자동제외(홍보) / 자동제외(관련성)
- **목록에서 바로** 승인·반려, 체크박스로 일괄 처리
- **상세 화면**에서 제목·요약을 다듬고, 분류·시행일·태그·메모를 입력
  → 여기 입력한 값이 그대로 MD의 front matter가 됩니다
- 자동 판정 근거(어떤 키워드가 걸렸는지)가 화면에 표시돼 왜 걸러졌는지 바로 보입니다
- 상단에 담당자 이름을 넣어 두면 모든 처리에 기록됩니다

**재수집해도 담당자가 내린 판단은 덮어쓰지 않습니다.** 이미 승인/반려한 기사는
본문만 보강되고 상태·메모·분류는 그대로 유지됩니다.

## 3단계 · MD 변환

```bash
python -m src.cli export        # 또는 검수 화면의 'MD 변환 실행' 버튼
```

승인 건만 세 가지 형태로 나갑니다.

| 산출물 | 용도 |
|---|---|
| `output/articles/*.md` | 기사 1건 = 파일 1개. **RAG 청크 단위로 권장** |
| `output/index.md` | 분류별 목차. 사람이 훑어보는 용도 |
| `output/bundle/insurance-policy-news.md` | 단일 파일 통합본. 통째로 넣을 때 |

각 파일은 YAML front matter를 달고 나가서, 챗봇이 메타데이터로 필터링할 수 있습니다.

```markdown
---
title: "GA 설계사도 1200%룰 적용…보험 판매수수료제도 개편 시행"
doc_id: 88a922614deb1f85
source: "보험신보"
url: "https://www.insweek.co.kr/news/articleView.html?idxno=71554"
published_at: "2026-07-01"
effective_date: "2026-07-01"
category: "판매채널·수수료"
tags: ["판매채널·수수료"]
doc_type: 보험제도변경뉴스
reviewed_by: "김담당"
---

# GA 설계사도 1200%룰 적용…보험 판매수수료제도 개편 시행

**출처** 보험신보 · **보도일** 2026-07-01 · **시행일** 2026-07-01 · **분류** 판매채널·수수료

## 요약
...
## 담당자 메모
...
## 본문
...
## 원문
<https://...>
```

승인을 취소하면 다음 `export` 때 해당 MD가 자동으로 지워지므로,
챗봇 지식베이스에 반려된 기사가 남지 않습니다.

---

## 운영 루틴 예시

```bash
# 매일 아침
python -m src.cli collect     # 밤사이 기사 수집
python -m src.cli review      # 담당자가 검수 (보통 10~20건)
python -m src.cli export      # 승인분 MD 변환
python -m src.cli stats       # 현황 확인

# 챗봇 지식베이스에 반영
rsync -a --delete output/articles/ /path/to/chatbot/knowledge/insurance/
```

`collect` 는 cron 으로 돌리고 `review` 만 사람이 하는 구성을 권합니다.

```cron
0 7 * * 1-5 cd /path/to/repo && .venv/bin/python -m src.cli collect >> logs/collect.log 2>&1
```

## 분류 태그

`실손의료보험` · `판매채널·수수료` · `건전성·회계` · `자동차보험` ·
`보험사기·소비자보호` · `세제·연금` · `상품규제` · `기타 제도` · `미분류`

자동 추정 후 담당자가 상세 화면에서 바꿀 수 있습니다.
항목을 늘리려면 `src/models.py` 의 `CATEGORIES` 와
`src/classifier.py` 의 `_CATEGORY_RULES` 를 함께 수정하세요.

## 테스트

```bash
python -m tests.test_pipeline    # 49건, 네트워크 불필요
```

## 파일 구조

```
config/sources.yaml       수집 소스 (RSS·보도자료 목록)
config/filters.yaml       제도/홍보 판정 키워드·임계값
src/collect.py            1단계 수집
src/classifier.py         자동 1차 분류
src/review_app.py         2단계 검수 웹 UI
src/export_md.py          3단계 MD 변환
src/store.py              JSON 저장소 (담당자 판단 보존)
src/cli.py                CLI 진입점
data/articles.json        검수 큐 (git 미포함)
data/seed_articles.json   시연용 샘플
output/                   MD 산출물 (git 미포함)
examples/output/          산출물 예시
docs/                     2026 보험 제도 변경 참고 자료
```

## 주의

- 수집 대상 매체의 `robots.txt` 와 이용약관을 확인하고 쓰세요.
  기본 수집량은 보수적으로 잡혀 있습니다(소스당 40건, 최근 30일).
- 기사 본문에는 저작권이 있습니다. 사내 챗봇 등 내부 활용 범위를 넘어
  재배포할 계획이라면 각 매체의 이용 허락을 먼저 받으세요.
- `data/seed_articles.json` 의 `demo.example` 항목은 필터 동작 확인용 **가상 예시**입니다.
