"""Analysis tasks: create an explicit task, run it, read the result."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import ANALYSIS_PENDING, ANALYSIS_RUNNING, AnalysisTask, User
from ..schemas import AnalysisBulkDelete, AnalysisCreate
from ..serializers import analysis_detail, analysis_summary
from ..services.analysis import run_analysis_task
from .jobs import owned_job
from .resumes import owned_resume

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


def owned_analysis(db: Session, user: User, analysis_id: int) -> AnalysisTask:
    task = db.get(AnalysisTask, analysis_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分析记录不存在")
    return task


@router.get("")
def list_analyses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    tasks = db.scalars(
        select(AnalysisTask).where(AnalysisTask.user_id == user.id).order_by(AnalysisTask.id.desc())
    ).all()
    return [analysis_summary(task) for task in tasks]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_analysis(
    payload: AnalysisCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Create a new analysis task with frozen snapshots of the current resume and job."""
    resume = owned_resume(db, user, payload.resume_id)
    job = owned_job(db, user, payload.job_id)
    snapshot = (resume.draft.content_md if resume.draft else "") or resume.original_text
    task = AnalysisTask(
        user_id=user.id,
        resume_id=resume.id,
        job_id=job.id,
        resume_snapshot=snapshot,
        job_title_snapshot=job.title,
        job_snapshot=job.description,
        status=ANALYSIS_PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return analysis_summary(task)


@router.post("/{analysis_id}/run")
def run_analysis(
    analysis_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    task = owned_analysis(db, user, analysis_id)
    if task.status == ANALYSIS_RUNNING:
        return {"id": task.id, "status": task.status, "message": "该分析正在进行中"}
    task.status = ANALYSIS_PENDING
    task.error_message = None
    db.commit()
    background.add_task(run_analysis_task, task.id)
    return {"id": task.id, "status": ANALYSIS_PENDING, "message": "已开始分析"}


@router.post("/bulk-delete")
def bulk_delete_analyses(
    payload: AnalysisBulkDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """批量删除分析记录。

    - 只删属于当前账号的记录，别人的 id 一律当作不存在（放进 missing，不泄露是否存在）；
    - 正在执行（running）的任务不删，整批返回 409，避免删掉一半留下不一致的状态；
    - 级联清掉条目、建议与补充记录；**已保存的修改稿与历史版本不受影响**
      （采纳只写过 draft，revisions.analysis_id 是 ON DELETE SET NULL）。
    """
    ids = list(dict.fromkeys(payload.ids))
    tasks = db.scalars(
        select(AnalysisTask).where(AnalysisTask.id.in_(ids), AnalysisTask.user_id == user.id)
    ).all()
    found = {task.id for task in tasks}
    # 只有真正在执行的任务不能删。pending 是「已创建、还没开始跑」，
    # 删掉它时后台任务在 run_analysis_task 里找不到记录会直接返回，不会留下半截数据。
    busy = [task.id for task in tasks if task.status == ANALYSIS_RUNNING]
    if busy:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"分析 #{min(busy)} 还在进行中，请等它结束后再删除。",
        )
    if not tasks:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分析记录不存在")
    deleted = sorted(task.id for task in tasks)
    for task in tasks:
        db.delete(task)
    db.commit()
    return {"deleted": deleted, "missing": [i for i in ids if i not in found]}


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    """删一条分析记录：只删属于当前账号的记录，进行中的任务不允许删。"""
    task = owned_analysis(db, user, analysis_id)
    if task.status == ANALYSIS_RUNNING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "这条分析还在进行中，请等它结束后再删除。"
        )
    db.delete(task)
    db.commit()


@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return analysis_detail(owned_analysis(db, user, analysis_id))
