from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.trading_account_service import create_trading_account


def get_user_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return db.execute(statement).scalar_one_or_none()


def create_user(db: Session, user_data: UserCreate) -> User:
    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    create_trading_account(db, user.id)

    return user