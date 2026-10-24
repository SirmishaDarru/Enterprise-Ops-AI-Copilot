from datetime import datetime, timedelta, timezone
from typing import Annotated
import uuid

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError

hashing = PasswordHash.recommended()
bearer = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def password_hash(password: str) -> str:
    return hashing.hash(password)


def password_matches(password: str, stored: str) -> bool:
    return hashing.verify(password, stored)


def access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "iss": settings.jwt_issuer,
                       "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)},
                      settings.jwt_secret, algorithm="HS256")


def current_user(token: Annotated[str, Depends(bearer)],
                 db: Annotated[Session, Depends(get_db)]) -> User:
    settings = get_settings()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"],
                            issuer=settings.jwt_issuer, options={"require": ["exp", "iat", "sub", "iss"]})
        user_id = uuid.UUID(claims["sub"])
    except (InvalidTokenError, ValueError, KeyError):
        raise ApiError(401, "UNAUTHENTICATED", "Invalid or expired token") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "UNAUTHENTICATED", "Invalid or expired token")
    return user


def require_roles(*roles: str):
    def enforce(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN", "Insufficient permissions")
        return user
    return enforce
