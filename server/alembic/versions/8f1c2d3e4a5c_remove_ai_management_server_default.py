"""remove ai management server default

Revision ID: 8f1c2d3e4a5c
Revises: 8f1c2d3e4a5b
Create Date: 2026-09-15
"""

from alembic import op


revision = "8f1c2d3e4a5c"
down_revision = "8f1c2d3e4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.alter_column(
            "ai_management_enabled",
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.alter_column(
            "ai_management_enabled",
            server_default="1",
        )