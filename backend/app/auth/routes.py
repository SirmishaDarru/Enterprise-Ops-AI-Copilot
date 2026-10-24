from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.models import User
from app.auth.security import access_token, current_user, password_matches, require_roles
from app.core.db import get_db
from app.core.errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    role: str


def present(user: User) -> UserOut:
    return UserOut(id=str(user.id), email=user.email, role=user.role)


@router.post("/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()],
          db: Annotated[Session, Depends(get_db)], request: Request):
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not password_matches(form.password, user.password_hash) or not user.is_active:
        record(db, actor_id=user.id if user else None, action="auth.login", target_type="user",
               target_id=str(user.id) if user else None, outcome="denied",
               request_id=request.state.request_id)
        db.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    record(db, actor_id=user.id, action="auth.login", target_type="user", target_id=str(user.id),
           outcome="allowed", request_id=request.state.request_id)
    db.commit()
    return {"access_token": access_token(user), "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)]):
    return present(user)


@router.get("/admin-check")
def admin_check(user: Annotated[User, Depends(require_roles("admin"))]):
    return {"message": "Authorized", "user_id": str(user.id)}
