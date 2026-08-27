#!/usr/bin/env bash
# Insurance AI 보험상품 운영 규칙 문서를 HTML -> PDF로 렌더링한다.
# 필요: Noto Sans KR 폰트 설치, Chromium(headless)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/docs/insurance-ai-operating-rules.html"
OUT="$ROOT/docs/Insurance_AI_보험상품_운영규칙_v1.1.pdf"

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in /opt/pw-browsers/chromium-*/chrome-linux/chrome \
           "$(command -v chromium || true)" \
           "$(command -v google-chrome || true)"; do
    [ -x "$c" ] && CHROME="$c" && break
  done
fi
[ -n "$CHROME" ] || { echo "chromium을 찾을 수 없습니다. CHROME=<경로>로 지정하세요." >&2; exit 1; }

"$CHROME" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$OUT" "file://$SRC"

echo "생성 완료: $OUT"
