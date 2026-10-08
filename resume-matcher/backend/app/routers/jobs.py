"""Target position storage."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import AnalysisTask, Job, User
from ..schemas import JobCreate, JobUpdate
from ..serializers import job_out

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def owned_job(db: Session, user: User, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "岗位不存在")
    return job


@router.get("")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    jobs = db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.id.desc())).all()
    return [job_out(job) for job in jobs]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    job = Job(user_id=user.id, title=payload.title.strip(), description=payload.description.strip())
    if not job.title or not job.description:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "岗位名称和岗位描述都不能为空")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.get("/{job_id}")
def get_job(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    return job_out(owned_job(db, user, job_id))


@router.put("/{job_id}")
def update_job(
    job_id: int,
    payload: JobUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """小幅修改岗位，不必新建再删旧的。

    边界：已有分析记录保存的是**发起时的岗位快照**（含岗位名），
    改岗位不会回写历史记录；只有之后的「新建分析任务」才用新描述。
    """
    job = owned_job(db, user, job_id)
    title = payload.title.strip()
    description = payload.description.strip()
    if not title or not description:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "岗位名称和岗位描述都不能为空")
    job.title = title
    job.description = description
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.get("/{job_id}/deletion-preview")
def job_deletion_preview(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """删岗位的确认弹窗：会影响多少条分析（这些分析不会被删，只是不再指向该岗位）。"""
    job = owned_job(db, user, job_id)
    analysis_count, resume_count = db.execute(
        select(func.count(AnalysisTask.id), func.count(func.distinct(AnalysisTask.resume_id))).where(
            AnalysisTask.job_id == job.id
        )
    ).one()
    return {
        "title": job.title,
        "analysis_count": int(analysis_count or 0),
        "resume_count": int(resume_count or 0),
    }


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> None:
    """删岗位。用它的分析记录会保留（job_id 置空），岗位名走分析自己的快照。"""
    owned_job(db, user, job_id)
    result = db.execute(delete(Job).where(Job.id == job_id, Job.user_id == user.id))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "岗位不存在")
    db.commit()
