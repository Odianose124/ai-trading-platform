from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class AIManagementAction(Base):
    """
    Persistent execution record for an AI trade-management action.

    Each record represents one controlled management attempt against
    an already-reconciled managed MT5 position.
    """

    __tablename__ = "ai_management_actions"

    __table_args__ = (
        UniqueConstraint(
            "action_key",
            name="uq_ai_management_action_key",
        ),
        Index(
            "ix_ai_management_actions_status",
            "status",
        ),
    )

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

    managed_position_id: Mapped[int] = mapped_column(
        ForeignKey("managed_positions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    position_ticket: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    decision: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    action_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="created",
    )

    requested_volume: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    requested_stop_loss: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    partial_close_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    retcode: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    retcode_description: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    message: Mapped[str | None] = mapped_column(
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

    user = relationship("User")

    mt5_account = relationship("MT5TradingAccount")

    managed_position = relationship(
        "ManagedPosition",
    )
