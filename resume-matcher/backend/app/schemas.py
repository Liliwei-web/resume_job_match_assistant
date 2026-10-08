"""Pydantic request/response schemas."""
import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ResumeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    original_text: str = Field(min_length=1)


class ResumeUpdate(BaseModel):
    """编辑简历素材。

    ``original_text`` 省略＝只改标题（保持原行为）；给了就用它覆盖原稿正文。
    ``reset_draft`` 只在同时给了 ``original_text`` 时才有意义：把修改稿重置成新原稿，
    因为新分析的输入取的是「修改稿 or 原稿」，不重置的话改了原稿也看不到效果。
    已保存的 revisions 任何情况下都不动。
    """

    title: str = Field(min_length=1, max_length=200)
    original_text: str | None = None
    reset_draft: bool = False


class DraftUpdate(BaseModel):
    content_md: str


class RevisionCreate(BaseModel):
    note: str = Field(default="", max_length=200)


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)


class JobUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)


class AnalysisCreate(BaseModel):
    resume_id: int
    job_id: int


class AnalysisBulkDelete(BaseModel):
    """批量删除分析记录。上限 200 条，避免一次请求把整张表扫一遍。"""

    ids: list[int] = Field(min_length=1, max_length=200)


class DecisionRequest(BaseModel):
    decision: str


class SupplementRequest(BaseModel):
    """补充「未体现 / 需要补充确认」条目时提交的真实经历。

    ``requirement_quote`` / ``confirmation_question`` 由后端按 ``item_id`` 从库里取，
    客户端即使传了也会被忽略（pydantic 默认丢弃未声明的字段），避免被伪造。
    """

    analysis_id: int
    item_id: int
    text: str = Field(min_length=1, max_length=4000)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str


class ResumeSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: dt.datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    created_at: dt.datetime


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    note: str
    created_at: dt.datetime


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    section: str
    original_passage: str | None
    suggested_passage: str | None
    rewrite_reason: str
    is_question: bool
    decision: str


class AnalysisItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    requirement_quote: str
    evidence_quote: str | None
    match_status: str
    reason: str
    confirmation_question: str | None


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resume_id: int
    job_id: int | None
    job_title_snapshot: str
    status: str
    error_message: str | None
    model_name: str
    created_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
