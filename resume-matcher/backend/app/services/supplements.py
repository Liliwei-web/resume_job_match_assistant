"""用户为「未体现 / 需要补充确认」条目补充真实经历：模型只做措辞优化，再写进修改稿。

与 ``services.analysis`` 的分工：

* 那边是**替换**已有原文（``Suggestion``），原段落必须能在修改稿里逐字找到；
* 这边是**插入**用户新提供的内容（``ItemSupplement``），所以要记锚点与实际插入的
  文本块，才能保证“重复采纳不重复插入”和“撤销能干净移除”。

事实边界同样由代码兜底：模型润色后的文本里，凡是用户这次没说过的实体或数字，
都会被拦下来（见 ``grounding.supplement_violations``），拦两次就直接报错，不静默放行。
"""
import logging
import re

from .. import llm
from ..models import (
    DECISION_ACCEPTED,
    DECISION_PENDING,
    DECISIONS,
    ItemSupplement,
    latest_supplement,
    utcnow,
)
from .grounding import find_quote, supplement_violations

logger = logging.getLogger(__name__)

# 一次提交最多润色两轮：第一轮越界就把命中的词回喂给模型，再越界就拒绝。
MAX_POLISH_ATTEMPTS = 2

# 找不到对应小节时，追加到文末的这个标题下。
BLOCK_HEADING = "## 补充信息"

_HEADING_RE = re.compile(r"^(#{1,6})\s*(.*)$")


class SupplementRejected(RuntimeError):
    """润色结果引入了用户没说过的内容，重试后仍然越界 —— 拒绝写入。"""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(
            "改写结果里出现了你没有提到的内容（"
            + "、".join(violations)
            + "），已阻止写入。请确认是否漏写，或换一种说法再提交。"
        )


class SupplementConflict(RuntimeError):
    """补充内容无法应用到当前修改稿（通常是被手动编辑过）。"""


def polish(db, item, text: str) -> ItemSupplement:
    """润色用户输入并落一条待处理记录；同一条目上已有的待处理记录会被覆盖。"""
    violations: list[str] = []
    result: dict | None = None
    for attempt in range(MAX_POLISH_ATTEMPTS):
        result = llm.request_supplement_polish(
            text, item.requirement_quote, item.confirmation_question or "", violations or None
        )
        violations = supplement_violations(result["polished"], text)
        if not violations:
            break
        logger.warning(
            "supplement polish introduced %s (attempt %s/%s)", violations, attempt + 1, MAX_POLISH_ATTEMPTS
        )
    if result is None or violations:
        raise SupplementRejected(violations)

    supplement = latest_supplement(item)
    if supplement is None or supplement.decision == DECISION_ACCEPTED:
        # 已采纳过的补充不允许原地改写（否则修改稿里那一段会对不上），另起一条。
        supplement = ItemSupplement(analysis_id=item.analysis_id)
        # 走关系而不是直接塞外键：会话是 expire_on_commit=False，不然接口返回的
        # item.supplement_state 会拿到旧的空集合。
        supplement.item = item
        db.add(supplement)
    supplement.user_input = text
    supplement.polished_text = result["polished"]
    supplement.polish_reason = result["reason"]
    supplement.section = result["section"]
    supplement.decision = DECISION_PENDING
    supplement.anchor_passage = None
    supplement.inserted_block = None
    supplement.applied_at = None
    supplement.updated_at = utcnow()
    db.commit()
    db.refresh(supplement)
    return supplement


def apply_decision(db, supplement: ItemSupplement, decision: str) -> ItemSupplement:
    """采纳 / 忽略 / 撤销一条补充。采纳只改工作稿，原稿永远不动。"""
    if decision not in DECISIONS:
        raise ValueError("无效的处理状态")

    draft = supplement.item.analysis.resume.draft
    if draft is None:
        raise SupplementConflict("该简历缺少修改稿，无法写入补充内容")

    if decision == supplement.decision:
        return supplement  # 幂等：重复点“采纳”不会重复插入

    content = draft.content_md or ""
    if decision == DECISION_ACCEPTED:
        # inserted_block 记的是“实际插进去的那一段”（含补上的换行，兜底时还含标题），
        # 所以撤销时按字面删掉它就能逐字还原。
        fragment = supplement.inserted_block or ""
        if not fragment or fragment not in content:
            content, fragment = _insert_block(
                content, _build_block(supplement.polished_text or ""), supplement
            )
            supplement.inserted_block = fragment or None
            if fragment:
                draft.content_md = content
                draft.updated_at = utcnow()
    elif supplement.decision == DECISION_ACCEPTED:
        fragment = supplement.inserted_block or ""
        if fragment:
            cleaned = _remove_block(content, fragment)
            if cleaned is None:
                raise SupplementConflict(
                    "补充内容未能在当前修改稿中唯一定位（可能已被手动编辑），请手动删除。"
                )
            draft.content_md = cleaned
            draft.updated_at = utcnow()

    supplement.decision = decision
    supplement.applied_at = utcnow() if decision == DECISION_ACCEPTED else None
    supplement.updated_at = utcnow()
    db.commit()
    return supplement


def _build_block(text: str) -> str:
    """把润色后的文本整理成要插入修改稿的块：每一非空行都是一条 bullet。"""
    lines = [line.strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(line if line.startswith("-") else f"- {line}" for line in lines)


def _insert_block(content: str, block: str, supplement) -> tuple[str, str]:
    """把补充块插进修改稿，返回 ``(新内容, 实际插入的片段)``。

    第二个返回值包含为拼接补上的换行（走兜底时还包含 ``## 补充信息`` 标题），
    所以 ``_remove_block`` 只要按字面删掉这一段，就能逐字回到插入前的样子 ——
    不会剩下空行或空标题。插入位置：证据行之后 → 同名小节末尾 → 文末兜底。
    """
    if not block:
        return content, ""

    evidence = supplement.item.evidence_quote
    if evidence:
        quote = find_quote(content, evidence)
        if quote:
            index = content.find(quote)
            line_end = content.find("\n", index)
            fragment = f"\n{block}"
            if line_end == -1:
                return f"{content}{fragment}", fragment
            return f"{content[:line_end]}{fragment}{content[line_end:]}", fragment

    offset = _section_offset(content, supplement.section)
    if offset is not None:
        lead = "" if offset == 0 or content[offset - 1] == "\n" else "\n"
        fragment = f"{lead}{block}\n"
        return f"{content[:offset]}{fragment}{content[offset:]}", fragment

    lead = ""
    if content and not content.endswith("\n"):
        lead = "\n"
    if content and not content.endswith("\n\n"):
        lead += "\n"
    fragment = f"{lead}{BLOCK_HEADING}\n{block}\n"
    return f"{content}{fragment}", fragment


def _section_offset(content: str, section: str) -> int | None:
    """返回 ``section`` 小节末尾的位置（下一个同级或更高级标题之前）；没有该小节时返回 None。

    只认同级或更高级的标题作为结束点，所以 ``## 项目经历`` 下的 ``### 某某项目``
    会连同它自己的内容一起算进这一节，插入位置落在整节最后一行之后。
    """
    if not section or section == "其他":
        return None
    lines = content.split("\n")
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        heading = _HEADING_RE.match(line.strip())
        if heading and section in heading.group(2):
            start, level = index, len(heading.group(1))
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        heading = _HEADING_RE.match(lines[index].strip())
        if heading and len(heading.group(1)) <= level:
            end = index
            break
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    offset = len("\n".join(lines[:end]))
    return offset + 1 if end < len(lines) else offset


def _remove_block(content: str, fragment: str) -> str | None:
    """按字面删掉补充时插入的那一段；定位不唯一（已被手改）时返回 None。"""
    if not fragment or content.count(fragment) != 1:
        return None
    return content.replace(fragment, "", 1)
