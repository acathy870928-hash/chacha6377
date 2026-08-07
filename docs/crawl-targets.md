# 수집 대상 사이트 정리 (보험연구원 · 금융감독원)

챗봇 지식베이스(`app/data/*.json`)를 실제 자료로 교체하기 위한 수집 대상 목록입니다.

> ⚠️ **경로 검증 상태**: 아래 URL은 검색 결과로 확인한 것이며, 개발 환경의 네트워크 정책상
> 각 페이지를 직접 열어 DOM 구조까지 확인하지는 못했습니다. 크롤러를 붙이기 전에
> ✅ 표시가 없는 항목은 브라우저로 한 번씩 열어 경로와 목록 구조를 재확인하세요.

---

## 0. 먼저 정할 것 — 근거의 위계

보험 챗봇에서 가장 중요한 결정입니다. **두 사이트는 성격이 완전히 다릅니다.**

| 구분 | 성격 | 챗봇에서의 용도 |
|---|---|---|
| **금융감독원** | 규범 (표준약관·감독규정·분쟁조정례) | 고객 답변의 **근거로 인용 가능** |
| **보험연구원** | 연구기관의 분석·견해 | **배경지식·용어 설명용**. 보장 여부 판단 근거로 인용 금지 |

보험연구원 리포트를 "약관상 이렇습니다"의 근거로 쓰면 잘못된 안내가 됩니다.
수집 시 문서마다 `authority: "regulation" | "research"` 필드를 반드시 붙이고,
`search_policy` 툴이 `regulation` 문서를 우선 반환하도록 설계하세요.

---

## 1. 금융감독원 (fss.or.kr 계열) — 우선순위 높음

### 1-1. 최우선: 표준약관 ★★★

챗봇 답변 정확도에 가장 직접적으로 기여하는 자료입니다.

| 콘텐츠 | 경로 | 비고 |
|---|---|---|
| 금융상품 표준약관 (목록) | `https://www.fss.or.kr/fss/bbs/B0000115/list.do?menuNo=200504` ✅ | 금융소비자보호 › 금융생활 길라잡이 › 금융상품 표준약관 |
| 표준약관 (상세/첨부) | `https://www.fss.or.kr/fss/bbs/B0000115/view.do?nttId={id}&menuNo=200504` ✅ | 첨부파일 **HWP** — 파싱기 필요 |
| 보험상품자료 (업무자료 계열) | `https://www.fss.or.kr/fss/bbs/B0000115/view.do?nttId={id}&menuNo=200143` ✅ | 같은 게시판(B0000115)을 다른 메뉴로 노출 |

수록 약관: 생명보험 / 화재보험 / 질병·상해보험 / **실손의료보험** / 해외여행 실손의료보험 /
배상책임보험 / **자동차보험** / 채무이행보증보험 / 신용보험 / 신원보증보험

> **HWP 주의**: 첨부가 HWP 단일 파일(약 1MB)에 여러 약관이 묶여 있습니다.
> `pyhwp` / `hwp5txt` 또는 LibreOffice 변환 후 약관별로 분할하는 단계가 필요합니다.
> 원문 조항이 필요 없다면 아래 1-4의 국가법령정보센터 API 쪽이 파싱이 훨씬 쉽습니다.

### 1-2. 분쟁조정사례 ★★★

"이런 경우 보험금 받을 수 있나요?" 류 질문의 최고 품질 근거입니다.

| 콘텐츠 | 경로 |
|---|---|
| 분쟁조정사례 / 조정결정례 | `https://www.fss.or.kr/fss/bbs/B0000390/list.do?cl1Cd=02&viewType=BODY` ✅ |
| 민원 유사사례 통합검색 | `https://www.fss.or.kr/fss/minwon/search.jsp?collection=simcase&query={q}` ✅ |
| 금융민원상담 안내 | `https://www.fss.or.kr/fss/main/sub1.do?menuNo=201093` ✅ |

`cl1Cd` 파라미터가 분류코드입니다. 보험 분류만 뽑으려면 목록에서 실제 코드값을 확인하세요.

### 1-3. 보도자료 (제도 변경 추적) ★★

| 콘텐츠 | 경로 | 갱신 |
|---|---|---|
| 보도자료 | `https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218` ✅ | 수시 (일 단위) |
| 보도설명자료 | `https://www.fss.or.kr/fss/bbs/B0000189/list.do?menuNo=200219` ✅ | 수시 |

실손보험 세대 개편, 표준약관 개정처럼 **기존 지식베이스를 무효화하는 변경**을 잡는 용도입니다.
전량 색인보다 "보험" 키워드 필터 + 신규 건만 증분 수집을 권장합니다.

### 1-4. 법규 원문 (보완 경로) ★★

표준약관 HWP 파싱이 부담되면 이쪽이 실용적입니다. **국가법령정보센터는 공식 오픈API를 제공합니다.**

| 콘텐츠 | 경로 |
|---|---|
| 보험업감독업무시행세칙 (표준약관 = 별표15) | `https://law.go.kr/admRulLsInfoP.do?admRulSeq=2200000108045` ✅ |
| 국가법령정보센터 오픈API | `https://open.law.go.kr/LSO/openApi/guideList.do` (별도 신청) |

> 금감원 사이트 밖이지만, 표준약관 원문을 구조화된 형태로 얻는 가장 쉬운 경로라 함께 적습니다.

### 1-5. 소비자 포털 / 공시 ★

| 사이트 | 경로 | 챗봇 활용 |
|---|---|---|
| 파인(FINE) 금융소비자정보포털 | `https://fine.fss.or.kr/` ✅ | 서비스 안내 문구 |
| 파인 서비스 소개 | `https://fine.fss.or.kr/fine/main/contents.do?menuNo=900212` ✅ | "내보험 찾아줌" 등 안내 |
| 내보험 찾아줌 | `https://www.fss.or.kr/main/prc/is/sub/is006.jsp?menuNo=900395` ✅ | 계약 조회 안내 시 연결 |
| 주요서류 및 서식 | `https://www.fss.or.kr/main/prc/is/sub/is012.jsp` ✅ | 청구 서식 안내 |
| 보험회사 종합공시 안내 | `https://www.fss.or.kr/fss/main/contents.do?menuNo=200418` ✅ | 공시 제도 설명 |
| 금융사고 현황 | `https://www.fss.or.kr/fss/bbs/B0000105/list.do?menuNo=200417` ✅ | (참고) |

### 1-6. 통계 / API ★

| 사이트 | 경로 | 비고 |
|---|---|---|
| 금융통계정보시스템(FISIS) | `https://fisis.fss.or.kr/` ✅ | 보험사 재무·경영 통계 |
| FISIS 오픈API 가이드 | `https://fisis.fss.or.kr/page/api-guide.jsp` ✅ | **크롤링 불필요, API 사용** |
| 금융상품 한눈에(finlife) | `https://finlife.fss.or.kr/` ✅ | 상품 비교공시 |
| finlife 오픈API | `https://finlife.fss.or.kr/finlife/main/contents.do?menuNo=700029` ✅ | 예적금·대출·연금저축 중심, **일반 보험상품은 커버리지 제한적** |
| DART 전자공시 | `https://dart.fss.or.kr/` ✅ | 보험사 사업보고서 (오픈API 별도) |

**FISIS와 finlife는 오픈API가 있으므로 HTML 크롤링 대상에서 빼세요.** 안정성·합법성 모두 유리합니다.

---

## 2. 보험연구원 (kiri.or.kr) — 배경지식용

URL 패턴은 두 갈래입니다.
- 보고서: `https://www.kiri.or.kr/report/reportList.do?catId={n}`
- 정기간행물: `https://www.kiri.or.kr/publication/list.do?catId={n}`
- 첨부 다운로드: `https://www.kiri.or.kr/report/downloadFile.do?docId={n}` (PDF)

| 콘텐츠 | catId | 경로 | 확인 |
|---|---|---|---|
| 연구보고서 | 4 | `report/reportList.do?catId=4` | ✅ |
| 정책/경영보고서 (2017년 연구보고서로 통합) | 5 | `report/reportList.do?catId=5` | ✅ 과거자료 |
| CEO Report | 7 | `report/reportList.do?catId=7` | ✅ |
| CEO Brief | 8 | `report/reportList.do?catId=8` | ✅ |
| (미확인 카테고리) | 52 | `report/reportList.do?catId=52` | ⚠️ 존재는 확인, 명칭 미확인 |
| KIRI 리포트 (상위) | parentCatId=13 | `publication/subIntro.do?parentCatId=13` | ✅ |
| KIRI 리포트 하위 | 28, 29 | `publication/list.do?catId=28` / `catId=29` | ⚠️ 명칭 미확인 (이슈분석 계열 추정) |
| 글로벌 이슈 | 30 | `publication/list.do?catId=30` | ✅ |
| 금융보험해설 (종간) | 34 | `publication/list.do?catId=34` | ✅ 종간 — 신규 없음 |
| 해외금융뉴스 (종간) | 36 | `publication/list.do?catId=36` | ✅ 종간 — 신규 없음 |
| 보도자료 상세 | — | `community/materialView.do?bid={n}` | ✅ (목록 경로는 ⚠️ 미확인) |

**"종간"으로 표시된 카테고리는 발행이 끝난 것**이므로 1회 벌크 수집 후 재크롤링에서 제외하세요.

### 챗봇에서의 활용 범위

- ✅ 용어 설명, 제도 배경, 상품 트렌드 설명
- ✅ 상담원 참고용 내부 지식
- ❌ "약관상 보장됩니다/안 됩니다" 판단 근거
- ❌ 보험금 지급 여부 안내

---

## 3. 두 사이트에 없는 것 (별도 확보 필요)

| 필요한 것 | 어디서 |
|---|---|
| 개별 상품 약관 원문 | 각 보험사 상품공시실 / 생명보험협회 `klia.or.kr` / 손해보험협회 `knia.or.kr` |
| 상품 비교공시 | 보험다모아 `e-insmarket.or.kr` (협회 운영) |
| 자사 상품·요율·계약 | 사내 기간계 시스템 |

챗봇이 자사 상품을 안내한다면 **결국 사내 상품 DB가 1순위**입니다.
금감원/보험연구원은 "공통 규범 + 배경지식" 레이어를 채우는 용도입니다.

---

## 4. 수집 시 유의사항

**법적/정책**
- 각 사이트 `robots.txt`와 이용약관을 먼저 확인하세요. 공공기관 자료는 대체로
  **공공누리** 유형이 적용되지만 유형별로 조건(출처표시/변경금지/상업적이용금지)이 다릅니다.
- 보험연구원 보고서는 저작권이 연구원에 있으며 **출처표시가 요구**됩니다.
  챗봇 답변에 인용 시 출처를 함께 노출하도록 설계하세요.
- **상업적 이용 제한**이 걸린 자료를 상용 챗봇에 넣으면 문제가 됩니다. 법무 검토 필요.

**기술**
- 요청 간격을 두세요(권장 1~2초). 동시 요청 금지.
- `User-Agent`에 연락 가능한 식별자를 남기세요.
- 오픈API가 있는 것(FISIS, finlife, 국가법령정보센터, DART)은 **API 우선**.
- HWP·PDF가 많습니다. 텍스트 추출 파이프라인(`pyhwp`, `pdfplumber`)을 먼저 준비하세요.
- 게시판이 `list.do` / `view.do?nttId=` 구조이므로, 목록에서 `nttId`를 수집한 뒤
  상세를 도는 2단계 크롤러가 자연스럽습니다.

**운영**
- 표준약관과 보도자료는 **개정 추적이 핵심**입니다. 문서마다 `수집일`·`개정일`을 저장하고,
  개정 감지 시 해당 지식베이스 항목을 무효화하는 흐름을 만드세요.
- 오래된 약관을 근거로 답하는 것이 가장 위험한 실패 모드입니다.

---

## 5. 기존 데이터 파일과의 매핑

| 현재 목업 | 교체할 소스 |
|---|---|
| `app/data/products.json` 의 `coverage`, `exclusions` | 금감원 표준약관 (1-1) + 사내 상품 DB |
| `app/data/faq.json` | 금감원 분쟁조정사례 (1-2) + 파인 안내 (1-5) |
| `app/data/claim_guides.json` | 금감원 주요서류·서식 (1-5) + 사내 청구 프로세스 |
| (신규) 용어사전·제도 배경 | 보험연구원 리포트 (2) |
| (신규) 제도 변경 알림 | 금감원 보도자료 (1-3) |

수집 규모가 커지면 현재의 키워드 + n-gram 검색(`app/knowledge.py`)으로는 한계가 있습니다.
문서 수가 수천 건을 넘어가면 임베딩 기반 검색으로 교체하세요.
