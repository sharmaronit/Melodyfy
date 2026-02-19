"""
auth.py — JWT authentication helpers for BeatFlow AI
Provides:  hash_password, verify_password, create_token, decode_token
FastAPI dependency: get_current_user
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from database import get_db

# ── Config ────────────────────────────────────────────────────────
SECRET_KEY      = os.getenv("JWT_SECRET", "beatflow-secret-changeme-in-prod")
ALGORITHM       = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7   # 7 days

_ph     = PasswordHasher()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ── Password helpers ──────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


# ── JWT helpers ───────────────────────────────────────────────────
def create_access_token(user_id: str, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return {}


# ── FastAPI dependency ────────────────────────────────────────────
def get_current_user(
    token: str | None = Depends(_oauth2),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated User, or raises 401.
    """
    from models import User

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found")
    return user


def get_current_user_optional(
    token: str | None = Depends(_oauth2),
    db: Session = Depends(get_db),
):
    """Returns user if authenticated, else None (for public endpoints)."""
    from models import User

    if not token:
        return None
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active == True).first()
