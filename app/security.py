from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import logging
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

logger = logging.getLogger("ham.security")
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
DUMMY_HASH = password_hasher.hash("not-a-real-password")
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
MIN_PASSWORD_LENGTH = 12


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_equal(left: str | None, right: str | None) -> bool:
    return bool(left and right and hmac.compare_digest(left, right))


def lockout_deadline() -> datetime:
    return utcnow() + timedelta(minutes=LOCKOUT_MINUTES)