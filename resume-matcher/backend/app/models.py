"""SQLAlchemy models: users, resumes, drafts, jobs, analyses, suggestions, revisions."""
import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# --- match_status values (see docs/题目附件/comparison-guide.md) ---
MATCH_SHOWN = "已体现"
MATCH_ABSENT = "未体现"
MATCH_NEEDS_CHECK = "需要补充确认"
MATCH_STATUSES = (MATCH_SHOWN, MATCH_ABSENT, MATCH_NEEDS_CHECK)

# --- suggestion decision values ---
DECISION_PENDING = "未处理"
DECISION_ACCEPTED = "采纳"
DECISION_IGNORED = "忽略"
DECISIONS = (DECISION_PENDING, DECISION_ACCEPTED, DECISION_IGNORED)

# --- 条目补充状态（在条目上展示，由最新一条补充记录推导） ---
SUPPLEMENT_NONE = "未补充"
SUPPLEMENT_DONE = "已补充"

# --- analysis task status values ---
ANALYSIS_PENDING = "pending"
ANALYSIS_RUNNING = "running"
ANALYSIS_SUCCEEDED = "succeeded"
ANALYSIS_FAILED = "failed"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resumes: Mapped[list["Resume"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    analyses: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Resume(Base):
    """The original resume input. Immutable after creation."""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    original_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="resumes")
    draft: Mapped["ResumeDraft | None"] = relationship(
        back_populates="resume", cascade="all, delete-orphan", uselist=False
    )
    revisions: Mapped[list["Revision"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="Revision.version"
    )
    analyses: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeDraft(Base):
    """The editable working copy. Accepting a suggestion changes only this row."""

    __tablename__ = "resume_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, index=True
    )
    content_md: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    resume: Mapped["Resume"] = relationship(back_populates="draft")


class Job(Base):
    """A saved target position (name + description)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="jobs")


class AnalysisTask(Base):
    """One explicit analysis run, with frozen resume + job snapshots."""

    __tablename__ = "analysis_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    # 删岗位不删分析：分析本身冻结了岗位快照（job_title_snapshot / job_snapshot），
    # 把引用置空即可保住历史，也不会跨简历误伤别人的分析记录。
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resume_snapshot: Mapped[str] = mapped_column(Text)
    job_title_snapshot: Mapped[str] = mapped_column(String(200))
    job_snapshot: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ANALYSIS_PENDING, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="analyses")
    resume: Mapped["Resume"] = relationship(back_populates="analyses")
    items: Mapped[list["AnalysisItem"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="AnalysisItem.position"
    )
    suggestions: Mapped[list["Suggestion"]] = relationship(
        back_populates="analysis", cascade="all, delete-orphan", order_by="Suggestion.position"
    )


class AnalysisItem(Base):
    """One job requirement judged against the resume snapshot."""

    __tablename__ = "analysis_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    requirement_quote: Mapped[str] = mapped_column(Text)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_status: Mapped[str] = mapped_column(String(16), default=MATCH_NEEDS_CHECK)
    reason: Mapped[str] = mapped_column(Text, default="")
    confirmation_question: Mapped[str | None] = mapped_column(Text, nullable=True)

    analysis: Mapped["AnalysisTask"] = relationship(back_populates="items")
    supplements: Mapped[list["ItemSupplement"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemSupplement.id"
    )


class Suggestion(Base):
    """A per-passage rewrite, or a standalone confirmation question."""

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(80), default="")
    original_passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    rewrite_reason: Mapped[str] = mapped_column(Text, default="")
    is_question: Mapped[bool] = mapped_column(default=False)
    decision: Mapped[str] = mapped_column(String(16), default=DECISION_PENDING, index=True)
    applied_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis: Mapped["AnalysisTask"] = relationship(back_populates="suggestions")


class ItemSupplement(Base):
    """用户为「未体现 / 需要补充确认」条目补的一段真实经历（模型只做措辞优化）。

    与 ``Suggestion`` 的区别：``Suggestion`` 是在**已有原文**上做替换，
    ``ItemSupplement`` 是往修改稿里**插入**一段用户新提供的内容，
    所以它记了锚点（插在哪一行之后）和实际插入的文本块，用来保证幂等与可撤销。
    """

    __tablename__ = "item_supplements"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_items.id", ondelete="CASCADE"), index=True
    )
    user_input: Mapped[str] = mapped_column(Text)
    polished_text: Mapped[str] = mapped_column(Text, default="")
    polish_reason: Mapped[str] = mapped_column(Text, default="")
    section: Mapped[str] = mapped_column(String(80), default="")
    anchor_passage: Mapped[str | None] = mapped_column(Text, nullable=True)
    inserted_block: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default=DECISION_PENDING, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item: Mapped["AnalysisItem"] = relationship(back_populates="supplements")


def latest_supplement(item: "AnalysisItem") -> "ItemSupplement | None":
    """条目当前的补充记录：被忽略的不算，其余取最新一条。"""
    rows = [row for row in item.supplements if row.decision != DECISION_IGNORED]
    return max(rows, key=lambda row: row.id) if rows else None


class Revision(Base):
    """An explicitly saved version of the modified resume."""

    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("resume_id", "version", name="uq_revision_resume_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_md: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resume: Mapped["Resume"] = relationship(back_populates="revisions")
