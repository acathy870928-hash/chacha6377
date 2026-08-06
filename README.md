# chacha6377 — 마크다운 변환기

브라우저에서 바로 동작하는 **Markdown ↔ HTML 변환기**입니다. 서버가 필요 없고,
입력한 내용은 어디로도 전송되지 않습니다(모든 변환은 클라이언트에서 처리).

## 기능

- **MD → HTML**: 실시간 미리보기 + 변환된 HTML 소스 보기
- **HTML → MD**: 붙여넣은 HTML을 마크다운으로 역변환
- 파일 열기 / 드래그 앤 드롭 (`.md`, `.markdown`, `.txt`, `.html`)
- 결과 복사(`Ctrl/⌘+Enter`), 다운로드(`Ctrl/⌘+S`)
- 다크 모드, 입력 내용·설정 자동 저장(localStorage)
- 의존성 0 — 순수 정적 파일이라 어떤 정적 호스팅에도 올릴 수 있습니다

### 지원하는 마크다운 문법

제목(ATX·Setext), 문단, 강조/기울임/취소선, 인라인 코드, 펜스·들여쓰기 코드 블록,
인용구, 순서 있는/없는/중첩 목록, 체크박스 목록, 표(정렬 포함), 수평선,
링크·이미지·참조 링크·자동 링크, 백슬래시 이스케이프, 하드 줄바꿈.

### 옵션

| 옵션 | 설명 |
| --- | --- |
| 줄바꿈을 `<br>`로 | 한 줄 개행을 그대로 줄바꿈으로 렌더링 (GFM 방식) |
| 원본 HTML 허용 | 입력에 포함된 HTML 태그를 이스케이프하지 않고 그대로 출력 |

기본값은 두 옵션 모두 꺼짐입니다. 입력의 HTML은 이스케이프되고 `javascript:` 같은
실행 가능한 URL은 차단되므로, 신뢰할 수 없는 문서를 붙여넣어도 안전합니다.
`원본 HTML 허용`을 켜면 이 보호가 해제되니 본인이 작성한 문서에만 사용하세요.

`다운로드`는 MD → HTML 모드에서 기본 스타일이 포함된 완전한 HTML 문서로 저장하고,
`코드` 탭과 `복사`는 변환된 HTML 조각을 그대로 제공합니다.

## 실행

정적 파일이므로 `index.html`을 브라우저로 열기만 해도 동작합니다.
로컬 서버로 확인하려면:

```bash
npm start          # http://localhost:8080
```

## 클라우드 배포 (GitHub Pages)

`main` 브랜치에 푸시하면 `.github/workflows/pages.yml` 이 테스트 후 자동 배포합니다.
최초 1회만 저장소 설정이 필요합니다:

1. GitHub 저장소 → **Settings → Pages**
2. **Build and deployment → Source** 를 **GitHub Actions** 로 변경
3. `main` 에 푸시하면 `https://acathy870928-hash.github.io/chacha6377/` 에 게시됩니다

Netlify, Vercel, Cloudflare Pages 등에 올릴 때도 빌드 명령 없이 저장소 루트를
그대로 게시하면 됩니다.

## 테스트

```bash
npm run test:unit      # 변환기 단위 테스트 (Node만 필요)
npm install            # 브라우저 테스트용 playwright 설치
npm test               # 단위 + 브라우저 테스트
```

브라우저 테스트는 HTML → MD 변환과 페이지 동작(모드 전환, 실시간 렌더링,
왕복 변환)을 실제 Chromium에서 확인합니다. playwright가 없으면 건너뜁니다.

## 구조

```
index.html                  UI
assets/style.css            스타일 (라이트/다크)
assets/markdown.js          Markdown → HTML 변환기
assets/html-to-markdown.js  HTML → Markdown 변환기
assets/app.js               UI 로직 (파일 입출력, 미리보기, 저장)
scripts/serve.js            로컬 정적 서버
tests/                      단위 테스트 · 브라우저 테스트
```

두 변환기는 UMD 형태라 Node에서도 그대로 쓸 수 있습니다:

```js
const { markdownToHtml } = require('./assets/markdown.js');
markdownToHtml('# 제목');   // '<h1 id="제목">제목</h1>'
```
