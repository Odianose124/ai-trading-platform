from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    timeframe: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )

    open_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    open: Mapped[Decimal] = mapped_column(
        Numeric(30, 12),
        nullable=False,
    )

    high: Mapped[Decimal] = mapped_column(
        Numeric(30, 12),
        nullable=False,
    )

    low: Mapped[Decimal] = mapped_column(
        Numeric(30, 12),
        nullable=False,
    )

    close: Mapped[Decimal] = mapped_column(
        Numeric(30, 12),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(30, 12),
        nullable=False,
    )

    trade_count: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "open_time",
            name="uq_candle_symbol_timeframe_open_time",
        ),
    )