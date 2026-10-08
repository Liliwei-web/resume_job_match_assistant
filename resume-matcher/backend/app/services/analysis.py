"""Run analyses and apply user decisions to the working draft."""
import logging

from .. import llm
from ..config import get_settings
from ..db import SessionLocal
from ..models import (
    ANALYSIS_FAILED,
    ANALYSIS_RUNNING,
    ANALYSIS_SUCCEEDED,
    DECISION_ACCEPTED,
    DECISIONS,
    AnalysisItem,
    AnalysisTask,
    Suggestion,
    utcnow,
)
from .grounding import normalize_items, normalize_polish

logger = logging.getLogger(__name__)


class SuggestionConflict(RuntimeError):
    """Raised when a decision cannot be applied to the current draft."""


def _suggestion_row(analysis_id: int, position: int, suggestion: dict) -> Suggestion:
    return Suggestion(
        analysis_id=analysis_id,
        position=position,
        section=suggestion["section"],
        original_passage=suggestion["original_passage"],
        suggested_passage=suggestion["suggested_passage"],
        rewrite_reason=suggestion["rewrite_reason"],
        is_question=suggestion["is_question"],
    )


def run_analysis_task(analysis_id: int) -> None:
    """Execute one analysis task in its own session (used as a background job)."""
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, analysis_id)
        if task is None:
            return

        task.status = ANALYSIS_RUNNING
        task.started_at = utcnow()
        task.error_message = None
        db.commit()

        try:
            payload = llm.request_analysis(
                task.resume_snapshot, task.job_title_snapshot, task.job_snapshot
            )
            items = normalize_items(payload["items"], task.resume_snapshot, task.job_snapshot)
            if not items:
                raise llm.LLMError("模型输出无法与岗位描述和简历原文对应，请重试")
            # 与岗位要求无关的表达优化建议：口语化的句子即使不对应任何要求也要能被改写。
            used = {
                suggestion["original_passage"]
                for item in items
                for suggestion in item["suggestions"]
                if suggestion["original_passage"]
            }
            polish = normalize_polish(payload.get("polish"), task.resume_snapshot, used)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user through the task
            logger.warning("analysis %s failed: %s", analysis_id, exc)
            task.status = ANALYSIS_FAILED
            task.error_message = str(exc)[:2000]
            task.finished_at = utcnow()
            db.commit()
            return

        try:
            for existing in list(task.items):
                db.delete(existing)
            for existing in list(task.suggestions):
                db.delete(existing)
            db.flush()

            for position, item in enumerate(items):
                db.add(
                    AnalysisItem(
                        analysis_id=task.id,
                        position=position,
                        requirement_quote=item["requirement_quote"],
                        evidence_quote=item["evidence_quote"],
                        match_status=item["match_status"],
                        reason=item["reason"],
                        confirmation_question=item["confirmation_question"],
                    )
                )

            position = 0
            for item in items:
                for suggestion in item["suggestions"]:
                    db.add(_suggestion_row(task.id, position, suggestion))
                    position += 1
            for suggestion in polish:
                db.add(_suggestion_row(task.id, position, suggestion))
                position += 1

            task.model_name = get_settings().llm_model
            task.status = ANALYSIS_SUCCEEDED
            task.finished_at = utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001 - persistence failure
            db.rollback()
            task = db.get(AnalysisTask, analysis_id)
            if task is not None:
                task.status = ANALYSIS_FAILED
                task.error_message = f"分析结果保存失败：{exc}"[:2000]
                task.finished_at = utcnow()
                db.commit()
    finally:
        db.close()


def fail_stale_tasks() -> int:
    """Mark tasks left in a running state (for example after a container restart)."""
    from sqlalchemy import select

    db = SessionLocal()
    try:
        stale = db.scalars(select(AnalysisTask).where(AnalysisTask.status == ANALYSIS_RUNNING)).all()
        for task in stale:
            task.status = ANALYSIS_FAILED
            task.error_message = "分析在服务重启时被中断，请重试。"
            task.finished_at = utcnow()
        if stale:
            db.commit()
        return len(stale)
    finally:
        db.close()


def apply_decision(db, suggestion: Suggestion, decision: str) -> Suggestion:
    """Accept / ignore / reset one suggestion. Only the draft is ever modified."""
    if decision not in DECISIONS:
        raise ValueError("无效的处理状态")

    draft = suggestion.analysis.resume.draft
    if draft is None:
        raise SuggestionConflict("该简历缺少修改稿，无法应用建议")

    if decision == suggestion.decision:
        return suggestion  # idempotent: repeated clicks never insert content twice

    original = suggestion.original_passage or ""
    suggested = suggestion.suggested_passage or ""
    content = draft.content_md or ""

    if suggestion.is_question or not suggested:
        # Confirmation questions never touch the resume body.
        suggestion.decision = decision
        suggestion.applied_at = utcnow() if decision == DECISION_ACCEPTED else None
        db.commit()
        return suggestion

    if decision == DECISION_ACCEPTED:
        if original not in content:
            raise SuggestionConflict(
                "原段落未在当前修改稿中找到（可能已被手动编辑），请手动修改或先撤销相关编辑。"
            )
        draft.content_md = content.replace(original, suggested, 1)
    elif suggestion.decision == DECISION_ACCEPTED:
        # 撤销（回到“未处理”）与“忽略”走同一条还原路径：只要之前采纳过，
        # 就把改写后的文本按字面换回原段落。否则状态回退了，正文却仍是改写稿。
        if suggested not in content:
            raise SuggestionConflict(
                "该建议的改写结果未在当前修改稿中找到（可能已被手动编辑），无法自动撤销。"
            )
        draft.content_md = content.replace(suggested, original, 1)

    draft.updated_at = utcnow()
    suggestion.decision = decision
    suggestion.applied_at = utcnow() if decision == DECISION_ACCEPTED else None
    db.commit()
    return suggestion
