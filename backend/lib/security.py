"""Passwords, session JWTs and HMAC-signed file links. Secrets come from backend/.env only."""

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"
# Sessions last until explicit logout (no time limit, user's choice). The browser cookie is renewed on use;
# logout bumps users.session_version, which revokes every token issued before it.
COOKIE_MAX_AGE = 400 * 24 * 3600  # browsers cap cookie lifetime at 400 days; renewed on each /auth/me
COOKIE_NAME = "pd_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_session_token(user_id: str, session_version: int = 0) -> str:
    payload = {"sub": user_id, "iat": datetime.now(timezone.utc), "typ": "session", "sv": session_version}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_session_token(token: str) -> tuple[str, int] | None:
    """(user_id, session_version) — the version must still match the user's to be valid."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "session" or not payload.get("sub"):
        return None
    return payload["sub"], int(payload.get("sv", 0))


def new_secret_token() -> str:
    return secrets.token_urlsafe(32)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sign_file_link(doc_id: str, ttl_seconds: int = 300) -> tuple[int, str]:
    exp = int(time.time()) + ttl_seconds
    sig = hmac.new(JWT_SECRET.encode(), f"file:{doc_id}:{exp}".encode(), hashlib.sha256).hexdigest()
    return exp, sig


def verify_file_link(doc_id: str, exp: int, sig: str) -> bool:
    if exp < int(time.time()):
        return False
    expected = hmac.new(JWT_SECRET.encode(), f"file:{doc_id}:{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
