from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        unique=True,
        index=True,
        nullable=False,
    )

    risk_percent: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )

    max_risk_percent: Mapped[float] = mapped_column(
        Float,
        default=2.0,
        nullable=False,
    )

    preferred_timeframe: Mapped[str] = mapped_column(
        String(20),
        default="15m",
        nullable=False,
    )

    max_open_trades: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    auto_trading_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    require_trade_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
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
