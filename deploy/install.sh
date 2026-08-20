#!/usr/bin/env bash
# 우분투 서버에 '사업단 뉴스 브리핑'을 설치한다.
#
#   sudo bash install.sh
#
# 물어보는 것: 도메인, 관리자 비밀번호, 사업단 이름.
# 나머지(파이썬, nginx, HTTPS 인증서, 자동 재시작, 30분마다 수집)는 알아서 잡는다.
# 여러 번 다시 돌려도 안전하다.

set -euo pipefail

REPO="${REPO:-https://github.com/acathy870928-hash/chacha6377.git}"
BRANCH="${BRANCH:-claude/kakaotalk-chatbot-news-sharing-rg091w}"
APP_DIR="/srv/news-briefing"
APP_USER="news"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say()  { printf "\n\033[1;32m▶ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }
die()  { printf "\n\033[1;31m✗ %s\033[0m\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "sudo 를 붙여서 실행해 주세요:  sudo bash install.sh"
command -v apt-get >/dev/null || die "우분투(또는 데비안) 서버에서 실행해 주세요."

# ---------------------------------------------------------------- 입력받기

read -rp "도메인 (예: news.mysaeopdan.co.kr / 없으면 그냥 엔터): " DOMAIN
DOMAIN="${DOMAIN// /}"

while :; do
  read -rsp "관리자 비밀번호 (대표님이 어드민에 로그인할 때 씁니다): " ADMIN_PW; echo
  [[ ${#ADMIN_PW} -ge 8 ]] || { warn "8자 이상으로 정해 주세요."; continue; }
  read -rsp "한 번 더: " ADMIN_PW2; echo
  [[ "$ADMIN_PW" == "$ADMIN_PW2" ]] && break
  warn "두 번 입력한 비밀번호가 다릅니다."
done

read -rp "사업단 이름 (화면과 브리핑 제목에 나옵니다) [사업단]: " ORG
ORG="${ORG:-사업단}"

if [[ -n "$DOMAIN" ]]; then
  read -rp "HTTPS 인증서를 자동으로 발급할까요? 도메인이 이 서버를 가리키고 있어야 합니다. [Y/n]: " WANT_TLS
  WANT_TLS="${WANT_TLS:-Y}"
else
  WANT_TLS="n"
fi

# ---------------------------------------------------------------- 설치

say "필요한 프로그램을 받는 중입니다 (몇 분 걸립니다)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git rsync nginx ufw curl openssl

say "서비스 전용 계정을 만듭니다"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"

say "프로그램 파일을 준비합니다"

# 저장소가 비공개라서 서버에서 그냥 내려받을 수 없다. 세 가지 경우를 처리한다.
#   1) 이 스크립트가 통째로 올린 소스 안에 들어 있다  → 그 파일을 그대로 쓴다 (기본)
#   2) 이미 설치돼 있고 git 정보가 남아 있다           → git 으로 갱신
#   3) GITHUB_TOKEN 을 넘겨줬다                        → 토큰으로 clone
SRC_DIR=""
if [[ -f "$SCRIPT_DIR/../requirements.txt" && -f "$SCRIPT_DIR/../app/main.py" ]]; then
  SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

if [[ -n "$SRC_DIR" && "$SRC_DIR" == "$APP_DIR" ]]; then
  echo "  이미 설치 위치에 있습니다: $APP_DIR"

elif [[ -n "$SRC_DIR" ]]; then
  echo "  올려주신 파일을 씁니다: $SRC_DIR"
  mkdir -p "$APP_DIR"
  # data/ 와 .env 는 기존 것을 지켜야 한다. 기사와 비밀번호가 거기 들어 있다.
  rsync -a --delete \
        --exclude='.git' --exclude='.venv' --exclude='data' --exclude='.env' \
        "$SRC_DIR"/ "$APP_DIR"/

elif [[ -d "$APP_DIR/.git" ]]; then
  echo "  git 으로 갱신합니다"
  if ! git ls-remote --exit-code --heads "$REPO" "$BRANCH" >/dev/null 2>&1; then
    warn "작업 브랜치가 없어 기본 브랜치를 씁니다 (병합된 것으로 보입니다)"
    BRANCH="$(git ls-remote --symref "$REPO" HEAD | awk '/^ref:/ {sub("refs/heads/","",$2); print $2}')"
    [[ -n "$BRANCH" ]] || die "저장소에서 브랜치를 찾지 못했습니다."
  fi
  git -C "$APP_DIR" fetch origin "$BRANCH" --quiet
  git -C "$APP_DIR" checkout -B "$BRANCH" "origin/$BRANCH" --quiet
  git -C "$APP_DIR" reset --hard "origin/$BRANCH" --quiet

elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
  echo "  토큰으로 내려받습니다"
  rm -rf "$APP_DIR"
  git clone --branch "$BRANCH" --quiet \
      "https://x-access-token:${GITHUB_TOKEN}@${REPO#https://}" "$APP_DIR"

else
  die "프로그램 파일을 찾지 못했습니다.

  이 저장소는 비공개라 서버에서 바로 받을 수 없습니다. 둘 중 하나로 하세요.

  (1) 소스를 통째로 서버에 올린 뒤, 그 안의 스크립트를 실행
      sudo bash /경로/chacha6377/deploy/install.sh

  (2) GitHub 토큰을 넘겨서 실행
      sudo GITHUB_TOKEN=ghp_xxxx bash install.sh

  자세한 순서는 deploy/README.md 에 있습니다."
fi

say "파이썬 환경을 준비합니다"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

say "설정 파일을 만듭니다"
if [[ -n "$DOMAIN" ]]; then
  SCHEME="http"; [[ "$WANT_TLS" =~ ^[Yy]$ ]] && SCHEME="https"
  BASE_URL="$SCHEME://$DOMAIN"
else
  BASE_URL="http://$(curl -fsS --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')"
  warn "도메인이 없어 IP 주소로 설정했습니다: $BASE_URL"
fi

# 이미 만들어둔 API 키가 있으면 그대로 둔다 — 수집기 설정을 다시 바꾸지 않아도 되게
INGEST_KEY="$(grep -oP '(?<=^INGEST_API_KEY=).*' "$APP_DIR/.env" 2>/dev/null || true)"
[[ -n "$INGEST_KEY" ]] || INGEST_KEY="$(openssl rand -hex 24)"

cat > "$APP_DIR/.env" <<ENVEOF
ADMIN_PASSWORD=$ADMIN_PW
INGEST_API_KEY=$INGEST_KEY
PUBLIC_BASE_URL=$BASE_URL
DB_PATH=$APP_DIR/data/news.db
ORG_NAME=$ORG
ENVEOF
chmod 600 "$APP_DIR/.env"

mkdir -p "$APP_DIR/data"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

say "서버가 꺼져도 다시 켜지도록 등록합니다"
install -m 644 "$APP_DIR/deploy/news-briefing.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/news-collect.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/news-collect.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now news-briefing.service
systemctl enable --now news-collect.timer

say "웹 서버를 연결합니다"
SERVER_NAME="${DOMAIN:-_}"
sed "s/DOMAIN/$SERVER_NAME/" "$APP_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/news-briefing
ln -sf /etc/nginx/sites-available/news-briefing /etc/nginx/sites-enabled/news-briefing
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

say "방화벽을 엽니다"
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 'Nginx Full' >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

if [[ "$WANT_TLS" =~ ^[Yy]$ && -n "$DOMAIN" ]]; then
  say "HTTPS 인증서를 발급합니다"
  apt-get install -y -qq certbot python3-certbot-nginx
  if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect; then
    say "HTTPS 적용 완료"
  else
    warn "인증서 발급에 실패했습니다. 도메인이 이 서버를 가리키는지 확인한 뒤 아래를 다시 실행하세요:"
    warn "  sudo certbot --nginx -d $DOMAIN"
  fi
fi

say "첫 기사를 수집합니다"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/collect.py" || \
  warn "수집에 실패했습니다. feeds.json 의 RSS 주소를 확인해 주세요."

# ---------------------------------------------------------------- 안내

cat <<DONEEOF

────────────────────────────────────────────────
 설치가 끝났습니다.

  대표님 화면   $BASE_URL/admin
  비밀번호      방금 정하신 것

  수집기 연동용 API 키
    $INGEST_KEY

 자주 쓰는 명령
   sudo systemctl restart news-briefing     다시 켜기
   sudo journalctl -u news-briefing -f      기록 보기
   sudo systemctl list-timers news-collect  다음 수집 시각
   sudo bash $APP_DIR/deploy/install.sh     설정 다시 잡기

 백업할 파일은 이거 하나입니다
   $APP_DIR/data/news.db
────────────────────────────────────────────────

DONEEOF
