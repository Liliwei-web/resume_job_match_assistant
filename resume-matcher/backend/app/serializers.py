"""Response serialisation helpers (plain dicts keep the API explicit)."""
from .models import (
    DECISION_ACCEPTED,
    MATCH_STATUSES,
    SUPPLEMENT_DONE,
    SUPPLEMENT_NONE,
    AnalysisItem,
    AnalysisTask,
    ItemSupplement,
    Job,
    Resume,
    Revision,
    Suggestion,
    latest_supplement,
)


def revision_out(revision: Revision) -> dict:
    return {
        "id": revision.id,
        "version": revision.version,
        "note": revision.note,
        "content_md": revision.content_md,
        "created_at": revision.created_at,
        "analysis_id": revision.analysis_id,
    }


def suggestion_out(suggestion: Suggestion) -> dict:
    return {
        "id": suggestion.id,
        "position": suggestion.position,
        "section": suggestion.section,
        "original_passage": suggestion.original_passage,
        "suggested_passage": suggestion.suggested_passage,
        "rewrite_reason": suggestion.rewrite_reason,
        "is_question": suggestion.is_question,
        "decision": suggestion.decision,
        "applied_at": suggestion.applied_at,
    }


def item_out(item: AnalysisItem) -> dict:
    supplement = latest_supplement(item)
    return {
        "id": item.id,
        "position": item.position,
        "requirement_quote": item.requirement_quote,
        "evidence_quote": item.evidence_quote,
        "match_status": item.match_status,
        "reason": item.reason,
        "confirmation_question": item.confirmation_question,
        "supplement": supplement_out(supplement) if supplement else None,
        "supplement_state": supplement_state(supplement),
    }


def supplement_out(supplement: ItemSupplement) -> dict:
    return {
        "id": supplement.id,
        "analysis_id": supplement.analysis_id,
        "item_id": supplement.item_id,
        "user_input": supplement.user_input,
        "polished_text": supplement.polished_text,
        "polish_reason": supplement.polish_reason,
        "section": supplement.section,
        "decision": supplement.decision,
        "created_at": supplement.created_at,
        "applied_at": supplement.applied_at,
    }


def supplement_state(supplement: ItemSupplement | None) -> str:
    """条目上展示的补充状态：未补充 / 待处理 / 已补充（被忽略的算未补充）。"""
    if supplement is None:
        return SUPPLEMENT_NONE
    return SUPPLEMENT_DONE if supplement.decision == DECISION_ACCEPTED else "待处理"


def analysis_summary(task: AnalysisTask) -> dict:
    """分析记录的摘要。

    status_counts / adopted_suggestion_count 只做只读统计，供工作台的匹配概览使用，
    不参与任何判定逻辑：三态计数直接来自落库的 match_status，不是重新算出来的分数。
    """
    status_counts = {status: 0 for status in MATCH_STATUSES}
    for item in task.items:
        if item.match_status in status_counts:
            status_counts[item.match_status] += 1
    return {
        "id": task.id,
        "resume_id": task.resume_id,
        "job_id": task.job_id,
        "job_title": task.job_title_snapshot,
        "status": task.status,
        "error_message": task.error_message,
        "model_name": task.model_name,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "item_count": len(task.items),
        "suggestion_count": len(task.suggestions),
        "status_counts": status_counts,
        "adopted_suggestion_count": sum(
            1 for s in task.suggestions if s.decision == DECISION_ACCEPTED
        ),
    }


def analysis_detail(task: AnalysisTask) -> dict:
    data = analysis_summary(task)
    data["resume_snapshot"] = task.resume_snapshot
    data["job_snapshot"] = task.job_snapshot
    data["items"] = [item_out(item) for item in task.items]
    data["suggestions"] = [suggestion_out(s) for s in task.suggestions]
    return data


def resume_summary(resume: Resume) -> dict:
    revisions = sorted(resume.revisions, key=lambda r: r.version)
    latest = revisions[-1] if revisions else None
    return {
        "id": resume.id,
        "title": resume.title,
        "created_at": resume.created_at,
        "original_text": resume.original_text,
        "draft_content": resume.draft.content_md if resume.draft else "",
        "revision_count": len(revisions),
        "latest_revision": revision_out(latest) if latest else None,
    }


def job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "description": job.description,
        "created_at": job.created_at,
    }
