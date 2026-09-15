from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class ManagementProfile(Base):
    """
    Immutable management-rule snapshot attached to one ManagedPosition.

    This record represents the exact management instructions that were
    active when the position became managed. Existing positions must not
    change when future user defaults or management settings change.
    """

    __tablename__ = "management_profiles"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    managed_position_id: Mapped[int] = mapped_column(
        ForeignKey("managed_positions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    profile_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Balanced",
    )

    ai_management_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    break_even_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    break_even_trigger_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    break_even_offset: Mapped[Decimal | None] = mapped_column(
        Numeric(30, 10),
        nullable=True,
    )

    partial_profit_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    partial_1_trigger_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    partial_1_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    partial_2_trigger_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    partial_2_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4),
        nullable=True,
    )

    profit_protection_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    profit_protection_trigger_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    locked_profit_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    trailing_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    trailing_method: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    trailing_activation_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    trailing_distance_r: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8),
        nullable=True,
    )

    invalidation_protection_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    close_on_invalidation: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    max_management_duration_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    snapshot_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    managed_position = relationship(
        "ManagedPosition",
        back_populates="management_profile",
    )