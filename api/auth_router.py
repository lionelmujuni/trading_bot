"""
Authentication router — JWT + Google OAuth + encrypted credential storage.

Endpoints (all under /auth prefix):
  POST /auth/register          — bcrypt password, create user, return JWT
  POST /auth/login             — verify password, return JWT
  POST /auth/google            — verify Google ID token, upsert user, return JWT
  GET  /auth/me                — decode JWT → return user profile
  POST /auth/credentials       — save Fernet-encrypted exchange credentials
  GET  /auth/credentials/{ex}  — return masked keys for an exchange
  DELETE /auth/credentials/{ex} — remove stored credentials
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core import config
from core.database import Database

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_DAYS = 7

# ── Singletons ────────────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_security = HTTPBearer(auto_error=True)
_db = Database()

# ── JWT helpers ───────────────────────────────────────────────────────────────


def _create_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=_JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire},
        config.JWT_SECRET_KEY,
        algorithm=_JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises HTTP 401 on failure."""
    try:
        return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[_JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """FastAPI dependency — returns the decoded JWT payload."""
    return decode_token(credentials.credentials)


# ── Fernet encryption helpers ─────────────────────────────────────────────────


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(config.CREDENTIAL_ENCRYPTION_KEY.encode())


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class RegisterBody(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginBody(BaseModel):
    email: str
    password: str


class GoogleBody(BaseModel):
    id_token: str


class CredentialBody(BaseModel):
    exchange: str
    api_key: str
    private_key: str


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    """Create a new account with email/password. Returns a JWT."""
    if _db.get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    password_hash = _pwd_context.hash(body.password)
    user_id = _db.create_user(
        email=body.email,
        name=body.name or body.email.split("@")[0],
        password_hash=password_hash,
    )
    token = _create_token(user_id, body.email)
    return {
        "token": token,
        "user": {"id": user_id, "email": body.email, "name": body.name or body.email.split("@")[0]},
    }


@router.post("/login")
async def login(body: LoginBody):
    """Verify email/password and return a JWT."""
    user = _db.get_user_by_email(body.email)
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not _pwd_context.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _create_token(user["id"], user["email"])
    return {
        "token": token,
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
    }


@router.post("/google")
async def google_login(body: GoogleBody):
    """
    Verify a Google ID token (issued by @react-oauth/google) and upsert the user.
    Requires GOOGLE_CLIENT_ID to be set in .env.
    """
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured — add GOOGLE_CLIENT_ID=<your-id> to .env",
        )
    try:
        from google.oauth2 import id_token as _google_id_token
        from google.auth.transport import requests as _google_requests

        idinfo = _google_id_token.verify_oauth2_token(
            body.id_token,
            _google_requests.Request(),
            config.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Google token invalid: {exc}")

    google_id = idinfo["sub"]
    email = idinfo.get("email", "")
    name = idinfo.get("name", email.split("@")[0] if email else "User")

    user = _db.get_user_by_google_id(google_id) or _db.get_user_by_email(email)
    if user:
        _db.update_user_google_id(user["id"], google_id)
        user_id, email, name = user["id"], user["email"], user["name"]
    else:
        user_id = _db.create_user(email=email, name=name, google_id=google_id)

    token = _create_token(user_id, email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name}}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    user_id = int(current_user["sub"])
    user = _db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "email": user["email"], "name": user["name"]}


@router.post("/credentials", status_code=201)
async def save_credentials(
    body: CredentialBody,
    current_user: dict = Depends(get_current_user),
):
    """Save Fernet-encrypted exchange credentials for the authenticated user."""
    if not config.CREDENTIAL_ENCRYPTION_KEY:
        raise HTTPException(status_code=500, detail="Encryption key not configured")
    user_id = int(current_user["sub"])
    _db.save_user_credentials(
        user_id=user_id,
        exchange=body.exchange,
        api_key_encrypted=encrypt_credential(body.api_key),
        private_key_encrypted=encrypt_credential(body.private_key),
    )
    return {"saved": True, "exchange": body.exchange}


@router.get("/credentials/{exchange}")
async def get_credentials(
    exchange: str,
    current_user: dict = Depends(get_current_user),
):
    """Return masked API key info for the requested exchange."""
    user_id = int(current_user["sub"])
    row = _db.get_user_credentials_raw(user_id, exchange)
    if not row:
        raise HTTPException(status_code=404, detail=f"No credentials stored for {exchange}")
    api_key = decrypt_credential(row["api_key_encrypted"])
    masked = api_key[:6] + "••••" + api_key[-4:] if len(api_key) > 10 else "••••"
    return {"exchange": exchange, "api_key_masked": masked}


@router.delete("/credentials/{exchange}", status_code=204)
async def delete_credentials(
    exchange: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove stored credentials for an exchange."""
    user_id = int(current_user["sub"])
    _db.delete_user_credentials(user_id, exchange)
