"""add managed positions and management profile snapshots

Revision ID: 7c4d9e2a61b3
Revises: 3be397041ce9
Create Date: 2026-09-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4d9e2a61b3"
down_revision: Union[str, Sequence[str], None] = "3be397041ce9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("managed_positions"):
        op.create_table(
            "managed_positions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("mt5_account_id", sa.Integer(), nullable=False),
            sa.Column("trade_intent_id", sa.Integer(), nullable=True),
            sa.Column("broker_symbol", sa.String(length=50), nullable=False),
            sa.Column("position_ticket", sa.Integer(), nullable=False),
            sa.Column("order_ticket", sa.Integer(), nullable=True),
            sa.Column("deal_ticket", sa.Integer(), nullable=True),
            sa.Column("direction", sa.String(length=10), nullable=False),
            sa.Column("volume", sa.Numeric(20, 8), nullable=False),
            sa.Column("entry_price", sa.Numeric(30, 10), nullable=False),
            sa.Column("current_price", sa.Numeric(30, 10), nullable=True),
            sa.Column("stop_loss", sa.Numeric(30, 10), nullable=True),
            sa.Column("take_profit", sa.Numeric(30, 10), nullable=True),
            sa.Column("initial_stop_loss", sa.Numeric(30, 10), nullable=True),
            sa.Column("initial_risk_distance", sa.Numeric(30, 10), nullable=True),
            sa.Column(
                "status",
                sa.String(length=30),
                nullable=False,
                server_default="open",
            ),
            sa.Column(
                "profit_loss",
                sa.Numeric(30, 10),
                nullable=False,
                server_default="0",
            ),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "last_reconciled_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["mt5_account_id"],
                ["mt5_trading_accounts.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["trade_intent_id"],
                ["trade_intents.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("position_ticket"),
            sa.UniqueConstraint(
                "mt5_account_id",
                "position_ticket",
                name="uq_managed_position_account_ticket",
            ),
        )

        op.create_index(
            "ix_managed_positions_id",
            "managed_positions",
            ["id"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_user_id",
            "managed_positions",
            ["user_id"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_mt5_account_id",
            "managed_positions",
            ["mt5_account_id"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_trade_intent_id",
            "managed_positions",
            ["trade_intent_id"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_broker_symbol",
            "managed_positions",
            ["broker_symbol"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_position_ticket",
            "managed_positions",
            ["position_ticket"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_order_ticket",
            "managed_positions",
            ["order_ticket"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_deal_ticket",
            "managed_positions",
            ["deal_ticket"],
            unique=False,
        )

        op.create_index(
            "ix_managed_positions_status",
            "managed_positions",
            ["status"],
            unique=False,
        )

    if not _table_exists("management_profiles"):
        op.create_table(
            "management_profiles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("managed_position_id", sa.Integer(), nullable=False),
            sa.Column(
                "profile_name",
                sa.String(length=50),
                nullable=False,
                server_default="Balanced",
            ),
            sa.Column(
                "ai_management_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "break_even_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "break_even_trigger_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "break_even_offset",
                sa.Numeric(30, 10),
                nullable=True,
            ),
            sa.Column(
                "partial_profit_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "partial_1_trigger_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "partial_1_percent",
                sa.Numeric(10, 4),
                nullable=True,
            ),
            sa.Column(
                "partial_2_trigger_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "partial_2_percent",
                sa.Numeric(10, 4),
                nullable=True,
            ),
            sa.Column(
                "profit_protection_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "profit_protection_trigger_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "locked_profit_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "trailing_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "trailing_method",
                sa.String(length=30),
                nullable=True,
            ),
            sa.Column(
                "trailing_activation_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "trailing_distance_r",
                sa.Numeric(20, 8),
                nullable=True,
            ),
            sa.Column(
                "invalidation_protection_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "close_on_invalidation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "max_management_duration_minutes",
                sa.Integer(),
                nullable=True,
            ),
            sa.Column(
                "snapshot_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["managed_position_id"],
                ["managed_positions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "managed_position_id",
                name="uq_management_profile_managed_position_id",
            ),
        )

        op.create_index(
            "ix_management_profiles_id",
            "management_profiles",
            ["id"],
            unique=False,
        )

        op.create_index(
            "ix_management_profiles_managed_position_id",
            "management_profiles",
            ["managed_position_id"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("management_profiles"):
        op.drop_index(
            "ix_management_profiles_managed_position_id",
            table_name="management_profiles",
        )

        op.drop_index(
            "ix_management_profiles_id",
            table_name="management_profiles",
        )

        op.drop_table("management_profiles")

    if _table_exists("managed_positions"):
        op.drop_index(
            "ix_managed_positions_status",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_deal_ticket",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_order_ticket",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_position_ticket",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_broker_symbol",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_trade_intent_id",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_mt5_account_id",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_user_id",
            table_name="managed_positions",
        )

        op.drop_index(
            "ix_managed_positions_id",
            table_name="managed_positions",
        )

        op.drop_table("managed_positions")