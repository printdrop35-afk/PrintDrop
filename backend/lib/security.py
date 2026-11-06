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
SESSION_HOURS = 12
COOKIE_NAME = "pd_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_session_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=SESSION_HOURS), "typ": "session"}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "session":
        return None
    return payload.get("sub")


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
