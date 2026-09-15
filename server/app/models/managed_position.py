from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ManagedPosition(Base):
    """
    Database representation of an actual MT5 position that this application
    has successfully reconciled and taken responsibility for managing.
    """

    __tablename__ = "managed_positions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mt5_account_id: Mapped[int] = mapped_column(
        ForeignKey("mt5_trading_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    trade_intent_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_intents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    broker_symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    position_ticket: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        unique=True,
        index=True,
    )

    order_ticket: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    deal_ticket: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )

    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    volume: Mapped[Decimal] = mapped_column(
        Numeric(20, 8),
        nullable=False,
    )

    entry_price: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
    )

    current_price: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    take_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    initial_stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    initial_risk_distance: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="open",
        index=True,
    )

    profit_loss: Mapped[Decimal] = mapped_column(
        Numeric(30, 10),
        nullable=False,
        default=Decimal("0"),
    )

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    user = relationship(
        "User",
        backref="managed_positions",
    )

    mt5_account = relationship(
        "MT5TradingAccount",
        backref="managed_positions",
    )

    trade_intent = relationship(
        "TradeIntent",
        backref="managed_positions",
    )

    management_profile = relationship(
        "ManagementProfile",
        back_populates="managed_position",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "mt5_account_id",
            "position_ticket",
            name="uq_managed_position_account_ticket",
        ),
    )