from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class MT5TradingAccount(Base):
    __tablename__ = "mt5_trading_accounts"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mt5_login: Mapped[int] = mapped_column(
        nullable=False,
    )

    server: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    account_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="mt5_trading_account",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_mt5_trading_account_user_id",
        ),
        UniqueConstraint(
            "mt5_login",
            "server",
            name="uq_mt5_trading_account_login_server",
        ),
    )