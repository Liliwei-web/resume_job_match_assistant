"""Login / logout / current user."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import COOKIE_NAME, get_current_user, get_db
from ..models import User
from ..schemas import LoginRequest
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_payload(user: User) -> dict:
    return {"id": user.id, "username": user.username, "display_name": user.display_name}


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user.id),
        httponly=True,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return _user_payload(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _user_payload(user)
