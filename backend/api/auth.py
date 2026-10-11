"""
Token authentication.

Password hashing: PBKDF2-HMAC-SHA256, 600k iterations, per-user salt
(hashlib, stdlib). Tokens: itsdangerous signed values with a TTL, so the
DB stays small and there is no token table to leak. The signing secret
comes from AUTH_SECRET, or is generated once and persisted to
backend/data/.auth_secret — set AUTH_SECRET in production so tokens
survive restarts and across processes.

Stateless tokens mean no server-side logout: clearing the client-side
token is the revocation.
"""

import hashlib
import logging
import os
import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from api import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)

TOKEN_TTL_SECONDS = 7 * 24 * 3600
_PBKDF2_ITERATIONS = 600_000
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


class Credentials(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


def _auth_secret() -> str:
    secret = os.environ.get("AUTH_SECRET", "").strip()
    if secret:
        return secret
    secret_file = db.DATA_DIR / ".auth_secret"
    try:
        if secret_file.exists():
            return secret_file.read_text().strip()
        secret = secrets.token_urlsafe(48)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret)
        return secret
    except OSError as e:
        logger.warning("Could not persist auth secret, tokens will not survive restart: %s", e)
        return secrets.token_urlsafe(48)


_serializer: Optional[URLSafeTimedSerializer] = None


def _get_serializer() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(_auth_secret(), salt="cyberrisk-auth")
    return _serializer


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    ).hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt), expected_hash)


def issue_token(user: dict) -> str:
    return _get_serializer().dumps({"uid": user["id"]})


def user_from_token(token: Optional[str]) -> Optional[dict]:
    """Resolve a bearer token to its user, or None if missing/invalid/expired."""
    if not token:
        return None
    try:
        payload = _get_serializer().loads(token, max_age=TOKEN_TTL_SECONDS)
    except BadSignature:
        return None
    user = db.get_user_by_id(payload["uid"])
    return dict(user) if user else None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    """FastAPI dependency: requires a valid bearer token. Dataset session
    resolution happens in the session middleware (event loop) — a ContextVar
    set inside this dependency would only be visible in its own threadpool
    thread, not in the endpoint's."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Send an Authorization: Bearer <token> header.",
        )
    user = user_from_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token. Please log in again.",
        )
    return user


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(creds: Credentials):
    if not _USERNAME_RE.match(creds.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be 3-64 characters: letters, digits, dot, underscore or hyphen.",
        )
    if db.get_user_by_username(creds.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this username already exists.",
        )
    salt = secrets.token_bytes(16).hex()
    user_id = db.create_user(creds.username, hash_password(creds.password, salt), salt)
    user = db.get_user_by_id(user_id)
    return {"token": issue_token(user), "user": {"id": user["id"], "username": user["username"]}}


@router.post("/login")
def login(creds: Credentials):
    user = db.get_user_by_username(creds.username)
    if user is None or not verify_password(creds.password, user["salt"], user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
        )
    return {"token": issue_token(user), "user": {"id": user["id"], "username": user["username"]}}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    dataset = db.get_active_dataset(user["id"])
    return {
        "id": user["id"],
        "username": user["username"],
        "active_dataset": (
            {
                "session_id": dataset["session_id"],
                "asset_count": dataset["asset_count"],
                "created_at": dataset["created_at"].isoformat() if dataset["created_at"] else None,
            }
            if dataset
            else None
        ),
    }
