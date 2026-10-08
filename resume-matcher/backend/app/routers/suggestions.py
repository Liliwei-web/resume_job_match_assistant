"""Accept / ignore a suggestion. Only the working draft is ever modified."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Suggestion, User
from ..schemas import DecisionRequest
from ..serializers import suggestion_out
from ..services.analysis import SuggestionConflict, apply_decision

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


@router.post("/{suggestion_id}/decision")
def decide(
    suggestion_id: int,
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    suggestion = db.get(Suggestion, suggestion_id)
    if suggestion is None or suggestion.analysis.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "修改建议不存在")
    try:
        apply_decision(db, suggestion, payload.decision.strip())
    except SuggestionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    draft = suggestion.analysis.resume.draft
    draft_content = draft.content_md if draft else ""
    latest_revision = suggestion.analysis.resume.revisions
    saved = max((r.version for r in latest_revision), default=None)
    saved_content = next((r.content_md for r in latest_revision if r.version == saved), None)
    return {
        "suggestion": suggestion_out(suggestion),
        "draft_content": draft_content,
        "draft_dirty": saved_content is None or saved_content != draft_content,
    }
