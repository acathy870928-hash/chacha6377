"""환경 변수 기반 설정."""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """의존성 없이 .env 를 읽어 os.environ 에 채운다(이미 있는 값은 유지)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


BASE_DIR = Path(__file__).resolve().parent.parent
_load_dotenv(BASE_DIR / ".env")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")
INGEST_API_KEY = os.environ.get("INGEST_API_KEY", "dev-ingest-key")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "news.db"))

# 사업단 이름 (브리핑 제목/푸터에 노출)
ORG_NAME = os.environ.get("ORG_NAME", "사업단")

SESSION_COOKIE = "cc_admin"
