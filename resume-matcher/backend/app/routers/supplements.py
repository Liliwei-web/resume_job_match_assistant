"""补充「未体现 / 需要补充确认」条目：模型润色用户输入，再把结果写进修改稿。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import llm
from ..deps import get_current_user, get_db
from ..models import AnalysisItem, ItemSupplement, User
from ..schemas import DecisionRequest, SupplementRequest
from ..serializers import item_out, supplement_out
from ..services import supplements as service

router = APIRouter(prefix="/api", tags=["supplements"])


def _draft_state(resume) -> tuple[str, bool]:
    draft = resume.draft
    content = draft.content_md if draft else ""
    revisions = resume.revisions
    saved = max((revision.version for revision in revisions), default=None)
    saved_content = next((r.content_md for r in revisions if r.version == saved), None)
    return content, saved_content is None or saved_content != content


@router.post("/supplement", status_code=status.HTTP_201_CREATED)
def create_supplement(
    payload: SupplementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """把用户补充的真实经历交给模型做纯措辞优化，返回对比用的两段文本（尚未写入修改稿）。"""
    item = db.get(AnalysisItem, payload.item_id)
    if item is None or item.analysis_id != payload.analysis_id or item.analysis.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "分析条目不存在")

    try:
        supplement = service.polish(db, item, payload.text.strip())
    except service.SupplementRejected as exc:
        # 用字面量 422：Starlette 把常量名改过（UNPROCESSABLE_ENTITY -> CONTENT），
        # 写数字可以同时兼容新旧版本。
        raise HTTPException(422, str(exc)) from exc
    except llm.LLMNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return {"supplement": supplement_out(supplement), "item": item_out(item)}


@router.post("/supplements/{supplement_id}/decision")
def decide(
    supplement_id: int,
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """采纳 / 忽略 / 撤销一条补充。采纳只改工作稿，原稿保持只读。"""
    supplement = db.get(ItemSupplement, supplement_id)
    if supplement is None or supplement.item.analysis.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "补充记录不存在")

    try:
        service.apply_decision(db, supplement, payload.decision.strip())
    except service.SupplementConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    content, dirty = _draft_state(supplement.item.analysis.resume)
    return {
        "supplement": supplement_out(supplement),
        "item": item_out(supplement.item),
        "draft_content": content,
        "draft_dirty": dirty,
    }
