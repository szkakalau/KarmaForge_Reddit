"""Auth endpoints — JWT-based authentication."""

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .deps import get_db, get_current_user
from .models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    user: dict


class TokenData(BaseModel):
    sub: str
    email: str


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _create_token(user_id: str, email: str, secret: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60 * 24 * 7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(req: RegisterRequest, request: Request, session: Session = Depends(get_db)):
    try:
        state = request.app.state.app_state
        existing = session.query(User).filter(User.email == req.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = User(
            email=req.email,
            password_hash=_hash_password(req.password),
            display_name=req.display_name or req.email.split("@")[0],
        )
        session.add(user)
        session.commit()

        token = _create_token(user.id, user.email, state.jwt_secret)
        return AuthResponse(token=token, user={"id": user.id, "email": user.email, "display_name": user.display_name})
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("Registration failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request, session: Session = Depends(get_db)):
    try:
        state = request.app.state.app_state
        user = session.query(User).filter(User.email == req.email).first()
        if not user or not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = _create_token(user.id, user.email, state.jwt_secret)
        return AuthResponse(token=token, user={"id": user.id, "email": user.email, "display_name": user.display_name})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Login failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
