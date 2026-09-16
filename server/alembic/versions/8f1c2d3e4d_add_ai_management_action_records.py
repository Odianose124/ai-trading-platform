"""add persistent ai management action execution records

Revision ID: 8f1c2d3e4d
Revises: 8f1c2d3e4c
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "8f1c2d3e4d"
down_revision = "8f1c2d3e4a5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_management_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mt5_account_id", sa.Integer(), nullable=False),
        sa.Column("managed_position_id", sa.Integer(), nullable=False),
        sa.Column("position_ticket", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("action_key", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="created",
        ),
        sa.Column("requested_volume", sa.Numeric(20, 8), nullable=True),
        sa.Column("requested_stop_loss", sa.Numeric(30, 10), nullable=True),
        sa.Column("partial_close_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("retcode", sa.Integer(), nullable=True),
        sa.Column("retcode_description", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
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
            ["managed_position_id"],
            ["managed_positions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_key",
            name="uq_ai_management_action_key",
        ),
    )

    op.create_index(
        "ix_ai_management_actions_id",
        "ai_management_actions",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_ai_management_actions_user_id",
        "ai_management_actions",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_ai_management_actions_mt5_account_id",
        "ai_management_actions",
        ["mt5_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_ai_management_actions_managed_position_id",
        "ai_management_actions",
        ["managed_position_id"],
        unique=False,
    )

    op.create_index(
        "ix_ai_management_actions_position_ticket",
        "ai_management_actions",
        ["position_ticket"],
        unique=False,
    )

    op.create_index(
        "ix_ai_management_actions_action_key",
        "ai_management_actions",
        ["action_key"],
        unique=True,
    )

    op.create_index(
        "ix_ai_management_actions_status",
        "ai_management_actions",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_management_actions_status",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_action_key",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_position_ticket",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_managed_position_id",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_mt5_account_id",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_user_id",
        table_name="ai_management_actions",
    )

    op.drop_index(
        "ix_ai_management_actions_id",
        table_name="ai_management_actions",
    )

    op.drop_table("ai_management_actions")

