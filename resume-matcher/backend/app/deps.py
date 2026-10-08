"""Shared FastAPI dependencies."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import User
from .security import decode_access_token

COOKIE_NAME = "rm_access_token"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the caller from the auth cookie (or a bearer token for API tests)."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录状态已失效，请重新登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "账号不存在")
    return user
