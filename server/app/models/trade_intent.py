from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class TradeIntent(Base):
    __tablename__ = "trade_intents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    broker_symbol: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    # User-requested entry price.
    # This remains authoritative for pending entries.
    signal_entry_price: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    # Actual broker fill price.
    # NULL while a pending order is waiting.
    execution_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    stop_loss: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    take_profit: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    risk_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    ai_management_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    preview_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ready_for_confirmation",
    )

    confirmation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
    )

    execution_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="not_executed",
    )

    # MARKET
    # BUY_LIMIT
    # BUY_STOP
    # SELL_LIMIT
    # SELL_STOP
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MARKET",
    )

    # market
    # pending
    execution_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="market",
    )

    # not_applicable
    # placed
    # filled
    # cancelled
    # rejected
    pending_order_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="not_applicable",
    )

    pending_order_placed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    filled_position_ticket: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    signal_price_deviation_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    margin_required: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    free_margin: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    order_ticket: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    deal_ticket: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    retcode: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    retcode_description: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    confirmation_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    execution_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )