"""Resume storage: immutable original, editable draft, saved revisions, export."""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import (
    ANALYSIS_RUNNING,
    DECISION_ACCEPTED,
    AnalysisTask,
    ItemSupplement,
    Resume,
    ResumeDraft,
    Revision,
    Suggestion,
    User,
)
from ..schemas import DraftUpdate, ResumeCreate, ResumeUpdate, RevisionCreate
from ..serializers import analysis_summary, resume_summary, revision_out

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\s]+')


def owned_resume(db: Session, user: User, resume_id: int) -> Resume:
    """Fetch a resume that belongs to ``user`` or fail with 404 (never leaks existence)."""
    resume = db.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    return resume


@router.get("")
def list_resumes(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    resumes = db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.id.desc())
    ).all()
    return [resume_summary(resume) for resume in resumes]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_resume(
    payload: ResumeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    title = payload.title.strip()
    original = payload.original_text.strip()
    if not title or not original:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "简历名称和简历正文都不能为空")
    resume = Resume(user_id=user.id, title=title, original_text=payload.original_text)
    resume.draft = ResumeDraft(content_md=payload.original_text)
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return resume_summary(resume)


@router.get("/{resume_id}")
def get_resume(
    resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    resume = owned_resume(db, user, resume_id)
    data = resume_summary(resume)
    data["revisions"] = [revision_out(r) for r in sorted(resume.revisions, key=lambda r: r.version)]
    data["analyses"] = [
        analysis_summary(a) for a in sorted(resume.analyses, key=lambda a: a.id, reverse=True)
    ]
    return data


@router.put("/{resume_id}")
def update_resume(
    resume_id: int,
    payload: ResumeUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """编辑简历素材本身：标题，以及（可选的）原稿正文。

    两个刻意的边界，都要在界面上讲清楚：

    - **历史分析用的是发起时冻结的快照**，改原稿不会影响已有的分析结果与判断；
    - 新分析的输入是「修改稿 or 原稿」（见 ``create_analysis``），所以只改原稿时，
      若这份简历已有修改稿，分析看到的仍是旧内容——这正是 ``reset_draft`` 的用途：
      显式勾选才会把修改稿重置成新原稿。已保存的 revisions 一律不动。

    「原稿只读」约束的是**系统与模型**：任何分析、采纳、补充流程都不许改它；
    用户本人显式确认后修改自己的素材，不在此列。
    """
    resume = owned_resume(db, user, resume_id)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "简历名称不能为空")
    resume.title = title

    if payload.original_text is not None:
        original = payload.original_text.strip()
        if not original:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "简历正文不能为空")
        resume.original_text = original
        if payload.reset_draft:
            if resume.draft is None:
                resume.draft = ResumeDraft(content_md=original)
                db.add(resume.draft)
            else:
                resume.draft.content_md = original

    db.commit()
    db.refresh(resume)
    return resume_summary(resume)


@router.put("/{resume_id}/draft")
def update_draft(
    resume_id: int,
    payload: DraftUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    resume = owned_resume(db, user, resume_id)
    if resume.draft is None:
        resume.draft = ResumeDraft(content_md=payload.content_md)
        db.add(resume.draft)
    else:
        resume.draft.content_md = payload.content_md
    db.commit()
    db.refresh(resume)
    latest = max((r.version for r in resume.revisions), default=0)
    saved = next((r for r in resume.revisions if r.version == latest), None)
    return {
        "draft_content": resume.draft.content_md,
        "draft_dirty": (saved is None) or (saved.content_md != resume.draft.content_md),
    }


@router.get("/{resume_id}/revisions")
def list_revisions(
    resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    resume = owned_resume(db, user, resume_id)
    return [revision_out(r) for r in sorted(resume.revisions, key=lambda r: r.version, reverse=True)]


@router.post("/{resume_id}/revisions", status_code=status.HTTP_201_CREATED)
def save_revision(
    resume_id: int,
    payload: RevisionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Explicitly save the current working draft as a new revision."""
    resume = owned_resume(db, user, resume_id)
    content = resume.draft.content_md if resume.draft else resume.original_text
    if not content.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "修改稿为空，无法保存")
    version = max((r.version for r in resume.revisions), default=0) + 1
    revision = Revision(
        resume_id=resume.id, version=version, content_md=content, note=payload.note.strip()
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision_out(revision)


@router.get("/{resume_id}/export")
def export_resume(
    resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Return the markdown of the latest saved revision (never the model commentary).

    工作稿只要和最近保存的版本不一致，就先把它存成一个新版本再导出，
    这样“下载到的就是你当前看到的内容”，不会出现导出旧版本的意外。
    """
    resume = owned_resume(db, user, resume_id)
    draft_content = resume.draft.content_md if resume.draft else ""
    revisions = sorted(resume.revisions, key=lambda r: r.version)
    latest = revisions[-1] if revisions else None
    if latest is None or latest.content_md != draft_content:
        if not draft_content.strip():
            raise HTTPException(status.HTTP_409_CONFLICT, "修改稿为空，无法导出")
        latest = Revision(
            resume_id=resume.id,
            version=max((r.version for r in revisions), default=0) + 1,
            content_md=draft_content,
            note="导出前自动保存",
        )
        db.add(latest)
        db.commit()
        db.refresh(latest)
    safe_title = _UNSAFE_FILENAME.sub("-", resume.title).strip("-") or "resume"
    return {
        "filename": f"{safe_title}-修改稿-v{latest.version}.md",
        "content": latest.content_md,
        "revision_version": latest.version,
        "saved_at": latest.created_at,
        "draft_dirty": False,
    }


def _running_analysis_count(db: Session, resume_id: int) -> int:
    """真正在执行的任务数。

    只数 running：pending 是「已创建、还没开始跑」，它不会写任何数据，
    删简历时把它一起级联掉是安全的（后台任务找不到记录会直接返回）。
    早期这里把 pending 也算进来，结果是「建了任务没跑」会永久挡住删除。
    """
    count = db.scalar(
        select(func.count())
        .select_from(AnalysisTask)
        .where(
            AnalysisTask.resume_id == resume_id,
            AnalysisTask.status == ANALYSIS_RUNNING,
        )
    )
    return int(count or 0)


@router.get("/{resume_id}/deletion-preview")
def resume_deletion_preview(
    resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """删除确认弹窗要用的计数：采纳过的建议、分析条数、已保存版本数、进行中的任务。"""
    resume = owned_resume(db, user, resume_id)
    analysis_ids = select(AnalysisTask.id).where(AnalysisTask.resume_id == resume.id)
    adopted_suggestions = db.scalar(
        select(func.count())
        .select_from(Suggestion)
        .where(
            Suggestion.analysis_id.in_(analysis_ids),
            Suggestion.decision == DECISION_ACCEPTED,
        )
    )
    adopted_supplements = db.scalar(
        select(func.count())
        .select_from(ItemSupplement)
        .where(
            ItemSupplement.analysis_id.in_(analysis_ids),
            ItemSupplement.decision == DECISION_ACCEPTED,
        )
    )
    return {
        "title": resume.title,
        "adopted_suggestions": int(adopted_suggestions or 0),
        "adopted_supplements": int(adopted_supplements or 0),
        "analysis_count": len(resume.analyses),
        "revision_count": len(resume.revisions),
        "running_analysis_count": _running_analysis_count(db, resume_id),
    }


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    """删掉简历及其全部从属数据：草稿、已保存版本、分析、建议、补充。

    级联删除交给数据库的外键规则完成（这几张表都是 ON DELETE CASCADE），不手写递归，
    避免漏表；删除语句本身也带上 user_id，越权时一行都匹配不到。
    """
    resume = owned_resume(db, user, resume_id)
    running = _running_analysis_count(db, resume_id)
    if running:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"这份简历还有 {running} 个分析任务正在进行，等它结束或稍后再删除。",
        )
    result = db.execute(delete(Resume).where(Resume.id == resume_id, Resume.user_id == user.id))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "简历不存在")
    db.commit()
