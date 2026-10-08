"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resumes_user_id", "resumes", ["user_id"])

    op.create_table(
        "resume_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_id", sa.Integer(), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_resume_drafts_resume_id", "resume_drafts", ["resume_id"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])

    op.create_table(
        "analysis_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_id", sa.Integer(), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resume_snapshot", sa.Text(), nullable=False),
        sa.Column("job_title_snapshot", sa.String(length=200), nullable=False),
        sa.Column("job_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_analysis_tasks_user_id", "analysis_tasks", ["user_id"])
    op.create_index("ix_analysis_tasks_resume_id", "analysis_tasks", ["resume_id"])
    op.create_index("ix_analysis_tasks_job_id", "analysis_tasks", ["job_id"])
    op.create_index("ix_analysis_tasks_status", "analysis_tasks", ["status"])

    op.create_table(
        "analysis_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("requirement_quote", sa.Text(), nullable=False),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("match_status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confirmation_question", sa.Text(), nullable=True),
    )
    op.create_index("ix_analysis_items_analysis_id", "analysis_items", ["analysis_id"])

    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=80), nullable=False),
        sa.Column("original_passage", sa.Text(), nullable=True),
        sa.Column("suggested_passage", sa.Text(), nullable=True),
        sa.Column("rewrite_reason", sa.Text(), nullable=False),
        sa.Column("is_question", sa.Boolean(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suggestions_analysis_id", "suggestions", ["analysis_id"])
    op.create_index("ix_suggestions_decision", "suggestions", ["decision"])

    op.create_table(
        "revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("resume_id", sa.Integer(), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("resume_id", "version", name="uq_revision_resume_version"),
    )
    op.create_index("ix_revisions_resume_id", "revisions", ["resume_id"])


def downgrade() -> None:
    op.drop_table("revisions")
    op.drop_table("suggestions")
    op.drop_table("analysis_items")
    op.drop_table("analysis_tasks")
    op.drop_table("jobs")
    op.drop_table("resume_drafts")
    op.drop_table("resumes")
    op.drop_table("users")
