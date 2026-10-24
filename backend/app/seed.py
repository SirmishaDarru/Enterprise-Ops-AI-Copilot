"""Explicit local-only seed. Supply credentials through environment, never in source."""
import argparse
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import password_hash
from app.core.config import get_settings
from app.core.db import get_engine


def main() -> None:
    parser = argparse.ArgumentParser(description='Seed local demo identities')
    parser.add_argument('--reset-password', action='store_true',
                        help='Set DEMO_PASSWORD on all four existing local demo accounts')
    args = parser.parse_args()
    if get_settings().app_env != "development":
        raise SystemExit("Seeding is restricted to APP_ENV=development")
    password = os.getenv("DEMO_PASSWORD")
    if not password or len(password) < 12:
        raise SystemExit("Set DEMO_PASSWORD to a unique value of at least 12 characters")
    with Session(get_engine()) as db:
        for role in ("viewer", "responder", "approver", "admin"):
            email = f"{role}@local.example"
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(User(email=email, role=role, password_hash=password_hash(password)))
            elif args.reset_password:
                user.password_hash = password_hash(password)
        db.commit()
    print('Local demo users ready' + ('; passwords reset' if args.reset_password else ''))


if __name__ == "__main__":
    main()
