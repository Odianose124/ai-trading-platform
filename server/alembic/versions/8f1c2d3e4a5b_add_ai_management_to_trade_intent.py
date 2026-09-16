"""add ai management choice to trade intents

Revision ID: 8f1c2d3e4a5b
Revises: 7c4d9e2a61b3
Create Date: 2026-09-15
"""

from alembic import op
import sqlalchemy as sa


revision = "8f1c2d3e4a5b"
down_revision = "7c4d9e2a61b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_management_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.drop_column("ai_management_enabled")