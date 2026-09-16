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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("trade_intents")}

    with op.batch_alter_table("trade_intents") as batch_op:
        if "order_type" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "order_type",
                    sa.String(length=20),
                    nullable=False,
                    server_default="MARKET",
                )
            )

        if "execution_mode" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "execution_mode",
                    sa.String(length=20),
                    nullable=False,
                    server_default="market",
                )
            )

        if "pending_order_status" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "pending_order_status",
                    sa.String(length=30),
                    nullable=False,
                    server_default="not_applicable",
                )
            )

        if "pending_order_placed_at" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "pending_order_placed_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                )
            )

        if "filled_position_ticket" not in existing_columns:
            batch_op.add_column(
                sa.Column(
                    "filled_position_ticket",
                    sa.Integer(),
                    nullable=True,
                )
            )

        batch_op.alter_column(
            "execution_status",
            existing_type=sa.String(length=30),
            type_=sa.String(length=40),
            existing_nullable=False,
        )

        batch_op.alter_column("order_type", server_default=None)
        batch_op.alter_column("execution_mode", server_default=None)
        batch_op.alter_column("pending_order_status", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("trade_intents") as batch_op:
        batch_op.alter_column(
            "execution_status",
            existing_type=sa.String(length=40),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
        batch_op.drop_column("filled_position_ticket")
        batch_op.drop_column("pending_order_placed_at")
        batch_op.drop_column("pending_order_status")
        batch_op.drop_column("execution_mode")
        batch_op.drop_column("order_type")
