"""Password hashing, session tokens and a small in-memory rate limiter.

Passwords: scrypt from the Python standard library (memory-hard KDF), with a random 16-byte
salt per password. Stored format: scrypt$n$r$p$salt_b64$hash_b64. Verification uses a
constant-time comparison.

Sessions: a random 256-bit token is sent to the browser in an HttpOnly cookie; only its
SHA-256 hash is stored in the database, so a database leak does not reveal usable tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
from collections import defaultdict, deque

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
MIN_PASSWORD = 10
COMMON = {"password12", "1234567890", "qwertyuiop", "password123", "iloveyou12", "letmein123", "welcome123", "admin12345"}


def password_problems(password: str, email: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD:
        problems.append(f"Use at least {MIN_PASSWORD} characters.")
    if len(password) > 200:
        problems.append("Use at most 200 characters.")
    if password.lower() in COMMON:
        problems.append("This password is too common.")
    local = email.split("@")[0].lower()
    if local and len(local) >= 4 and local in password.lower():
        problems.append("Do not include your email name in the password.")
    if len(set(password)) < 5:
        problems.append("Use a more varied mix of characters.")
    return problems


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# A fixed hash used to spend the same time on unknown emails as on wrong passwords
# (reduces account-enumeration via response timing).
DUMMY_HASH = hash_password(secrets.token_hex(16))


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def normalise_email(email: str) -> str:
    return email.strip().lower()


class RateLimiter:
    """Sliding-window limiter kept in process memory.

    Suitable for a single server process. With several workers or servers, use a shared store
    (e.g. Redis) or the reverse proxy's rate limiting instead.
    """

    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        """Record an attempt; return False if the limit is exceeded."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


limiter = RateLimiter()
