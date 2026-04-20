from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User


def register_user(
    db: Session,
    *,
    email: str,
    username: str,
    password: str,
) -> User:
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError("Email already registered.")

    if db.scalar(select(User).where(User.username == username)) is not None:
        raise ValueError("Username already registered.")

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("User already exists.") from exc

    db.refresh(user)
    return user


def authenticate_user(
    db: Session,
    *,
    identifier: str,
    password: str,
) -> User | None:
    normalized_identifier = identifier.strip()
    email_identifier = normalized_identifier.lower()

    user = db.scalar(
        select(User).where(
            or_(
                User.email == email_identifier,
                User.username == normalized_identifier,
            )
        )
    )

    if user is None:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user
