"""Read-only local evaluation summary; PostgreSQL fixture runs only from CLI."""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.models import User
from app.auth.security import require_roles
from app.evaluation.run import evaluate

router = APIRouter(prefix='/evaluation', tags=['evaluation'])


@router.get('/offline')
def offline(_user: Annotated[User, Depends(require_roles('admin'))]):
    return evaluate('offline')
