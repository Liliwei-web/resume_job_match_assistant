"""analysis_tasks.job_id becomes nullable with ON DELETE SET NULL

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

删岗位不再连带删除用它跑过的分析：分析在创建时已经冻结了岗位快照
（``job_title_snapshot`` / ``job_snapshot``），把引用置空就能保住历史，
也不会因为删一个岗位而删掉别的简历的分析记录。
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Postgres 给列级外键的默认名字（已在库里核对过）。
FK_NAME = "analysis_tasks_job_id_fkey"


def upgrade() -> None:
    op.alter_column("analysis_tasks", "job_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint(FK_NAME, "analysis_tasks", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME, "analysis_tasks", "jobs", ["job_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    # 回到 NOT NULL 之前必须先清掉 job_id 为空的行，这一步会丢数据，只用于回退开发环境。
    op.execute("DELETE FROM analysis_tasks WHERE job_id IS NULL")
    op.drop_constraint(FK_NAME, "analysis_tasks", type_="foreignkey")
    op.create_foreign_key(
        FK_NAME, "analysis_tasks", "jobs", ["job_id"], ["id"], ondelete="CASCADE"
    )
    op.alter_column("analysis_tasks", "job_id", existing_type=sa.Integer(), nullable=False)
