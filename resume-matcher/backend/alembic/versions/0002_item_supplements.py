"""item supplements: user-provided experience for 未体现 / 需要补充确认 条目

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_supplements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("analysis_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("polished_text", sa.Text(), nullable=False),
        sa.Column("polish_reason", sa.Text(), nullable=False),
        sa.Column("section", sa.String(length=80), nullable=False),
        sa.Column("anchor_passage", sa.Text(), nullable=True),
        sa.Column("inserted_block", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_item_supplements_analysis_id", "item_supplements", ["analysis_id"])
    op.create_index("ix_item_supplements_item_id", "item_supplements", ["item_id"])
    op.create_index("ix_item_supplements_decision", "item_supplements", ["decision"])


def downgrade() -> None:
    op.drop_table("item_supplements")
