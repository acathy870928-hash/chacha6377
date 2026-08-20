"""어드민 세션 쿠키 (서명된 값 하나, 외부 의존성 없음)."""
import hashlib
import hmac
import secrets
import time

from .config import ADMIN_PASSWORD

_SECRET = hashlib.sha256(f"cc-news::{ADMIN_PASSWORD}".encode()).digest()
MAX_AGE = 60 * 60 * 24 * 14  # 2주


def make_token() -> str:
    issued = str(int(time.time()))
    sig = hmac.new(_SECRET, issued.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{issued}.{sig}"


def verify_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    issued, _, sig = token.partition(".")
    expected = hmac.new(_SECRET, issued.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return (time.time() - int(issued)) < MAX_AGE
    except ValueError:
        return False


def check_password(candidate: str) -> bool:
    return secrets.compare_digest(candidate or "", ADMIN_PASSWORD)
