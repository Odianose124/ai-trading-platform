"""add pending entry execution fields

Revision ID: 8f1c2d3e4e
Revises: 8f1c2d3e4d
"""

from alembic import op
import sqlalchemy as sa


revision = "8f1c2d3e4e"
down_revision = "8f1c2d3e4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_intents",
        sa.Column(
            "order_type",
            sa.String(length=20),
            nullable=False,
            server_default="MARKET",
        ),
    )

    op.add_column(
        "trade_intents",
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default="market",
        ),
    )

    op.add_column(
        "trade_intents",
        sa.Column(
            "pending_order_status",
            sa.String(length=30),
            nullable=False,
            server_default="not_applicable",
        ),
    )

    op.add_column(
        "trade_intents",
        sa.Column(
            "pending_order_placed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "trade_intents",
        sa.Column(
            "filled_position_ticket",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.alter_column(
        "trade_intents",
        "execution_status",
        existing_type=sa.String(length=30),
        type_=sa.String(length=40),
        existing_nullable=False,
    )

    op.alter_column(
        "trade_intents",
        "order_type",
        server_default=None,
    )

    op.alter_column(
        "trade_intents",
        "execution_mode",
        server_default=None,
    )

    op.alter_column(
        "trade_intents",
        "pending_order_status",
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "trade_intents",
        "execution_status",
        existing_type=sa.String(length=40),
        type_=sa.String(length=30),
        existing_nullable=False,
    )

    op.drop_column(
        "trade_intents",
        "filled_position_ticket",
    )

    op.drop_column(
        "trade_intents",
        "pending_order_placed_at",
    )

    op.drop_column(
        "trade_intents",
        "pending_order_status",
    )

    op.drop_column(
        "trade_intents",
        "execution_mode",
    )

    op.drop_column(
        "trade_intents",
        "order_type",
    )