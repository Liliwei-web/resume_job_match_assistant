"""事实边界：改写不得引入简历里没有的技术栈、机构名或数量词，action 必须被遵守。"""
from app.services.grounding import (
    find_unsupported_terms,
    introduces_new_numbers,
    normalize_items,
    normalize_polish,
)

JOB = """任职要求：
1. 熟悉 Python 与 FastAPI
"""

RESUME = """# 张明

## 技能
- Python、MySQL、Git

## 项目经历
### 实验室设备借用平台（后端）
- 使用 Python 和 FastAPI 开发设备借还的接口
- 数据库表与同学共同设计，后续调整过几次
"""

# 真实素材（王强-口语化简历）里的那两行。用户明确要求过“口语化表述一律不自动改写”，
# 所以这份原文留下来专门钉住那条边界：它只该拿到提问，不该被改写成书面语。
COLLOQUIAL_RESUME = """# 王强

## 技能
- Python、MySQL、Git

## 项目经历
### 实验室设备借用平台（后端）
- 用 Python 和 FastAPI 弄了个设备借还的接口
- 数据库表是我和同学一起建的，后面改过几次
"""

REQUIREMENT = "熟悉 Python 与 FastAPI"
ORIGINAL = "- 使用 Python 和 FastAPI 开发设备借还的接口"
QUESTION = "你是否有过被要求补充的经历？"


def _run(suggested, *, action="改写", original=ORIGINAL, question=QUESTION):
    raw = [
        {
            "requirement_quote": REQUIREMENT,
            "evidence_quote": ORIGINAL,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": question,
            "suggestion": {
                "action": action,
                "section": "项目经历",
                "original_passage": original,
                "suggested_passage": suggested,
                "rewrite_reason": "优化表达",
            },
        }
    ]
    return normalize_items(raw, RESUME, JOB)[0]["suggestions"]


def test_wording_only_rewrite_that_reorders_words_is_kept():
    """只调语序、不增信息：原文后半句被提前，信息量不变，属于允许的润色，必须放行。"""
    suggestions = _run("- 开发设备借还接口，使用 Python 和 FastAPI")
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is False
    assert suggestions[0]["suggested_passage"] == "- 开发设备借还接口，使用 Python 和 FastAPI"


def test_invented_technology_is_blocked():
    suggestions = _run("- 使用 Python 和 FastAPI 编写接口，并用 Kubernetes 部署设备借还服务")
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is True
    assert suggestions[0]["suggested_passage"] is None
    assert "Kubernetes" in suggestions[0]["rewrite_reason"]


def test_invented_technology_is_blocked_even_without_an_action_field():
    """模型漏给 action 时不能成为绕过校验的后门。"""
    raw = [
        {
            "requirement_quote": REQUIREMENT,
            "evidence_quote": ORIGINAL,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": QUESTION,
            "suggestion": {
                "section": "项目经历",
                "original_passage": ORIGINAL,
                "suggested_passage": "- 用 Redis 缓存设备借还接口的结果",
                "rewrite_reason": "优化表达",
            },
        }
    ]
    suggestions = normalize_items(raw, RESUME, JOB)[0]["suggestions"]
    assert suggestions[0]["is_question"] is True
    assert suggestions[0]["suggested_passage"] is None


def test_invented_company_or_platform_is_blocked():
    suggestions = _run("- 负责校园招聘平台的接口开发")
    assert suggestions[0]["is_question"] is True
    assert "校园招聘平台" in suggestions[0]["rewrite_reason"]


def test_existing_platform_name_is_allowed():
    suggestions = _run("- 负责实验室设备借用平台的后端接口开发")
    assert suggestions[0]["is_question"] is False


def test_invented_chinese_tech_term_is_blocked():
    suggestions = _run("- 使用微服务架构改造设备借还接口")
    assert suggestions[0]["is_question"] is True
    assert "微服务" in suggestions[0]["rewrite_reason"]


def test_invented_chinese_quantity_is_blocked():
    assert introduces_new_numbers("- 处理 10 万条数据", ORIGINAL, RESUME) is True
    suggestions = _run("- 使用 Python 处理上万条设备借还记录")
    assert suggestions[0]["is_question"] is True


def test_unsupported_terms_lists_only_what_is_missing():
    assert find_unsupported_terms("- 使用 Python 和 Redis", RESUME) == ["Redis"]
    assert find_unsupported_terms("- 使用 Python 和 FastAPI", RESUME) == []


def test_action_append_with_a_rewrite_is_downgraded_to_a_question():
    suggestions = _run("- 使用 Python 和 FastAPI 实现设备借还接口", action="补充")
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is True
    assert suggestions[0]["suggested_passage"] is None
    assert "补充" in suggestions[0]["rewrite_reason"]


def test_action_append_without_a_question_produces_nothing():
    assert _run(ORIGINAL, action="补充", question="") == []


def test_action_rewrite_still_needs_the_numbers_and_entities_checks():
    suggestions = _run(
        "- 使用 Python 和 FastAPI 实现接口，日均调用 10 万次", action="改写"
    )
    assert suggestions[0]["is_question"] is True
    assert "数字" in suggestions[0]["rewrite_reason"]


def test_rewrite_identical_to_the_original_is_dropped_entirely():
    """改完和原文一字不差：采纳后正文毫无变化，必须丢弃，且不能降级成提问行。"""
    assert _run(ORIGINAL) == []
    assert _run("  " + ORIGINAL + "\n") == []


def test_identical_entry_in_polish_is_dropped_too():
    raw = [
        {
            "action": "改写",
            "section": "项目经历",
            "original_passage": ORIGINAL,
            "suggested_passage": ORIGINAL,
            "rewrite_reason": "优化表达",
        }
    ]
    assert normalize_polish(raw, RESUME) == []


def test_synonym_only_rewrite_is_dropped_entirely():
    """实测里出现过的那条：“有所提升 → 得到提升”只换了虚词，必须丢弃。"""
    line = "- 负责线上问题的排查与修复，接口响应速度有所提升"
    resume = "## 项目经历\n" + line + "\n"
    job = "任职要求：\n1. 有线上性能调优经验\n"
    raw = [
        {
            "requirement_quote": "有线上性能调优经验",
            "evidence_quote": line,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": {
                "action": "改写",
                "section": "项目经历",
                "original_passage": line,
                "suggested_passage": line.replace("有所提升", "得到提升"),
                "rewrite_reason": "优化表达",
            },
        }
    ]
    assert normalize_items(raw, resume, job)[0]["suggestions"] == []


def test_real_wording_change_next_to_a_synonym_swap_is_kept():
    """除了虚词层面的同类互换之外还带了实质新信息时，整条建议必须保留。"""
    suggestions = _run("- 使用 Python 和 FastAPI 开发设备借还接口，并覆盖借出与归还流程")
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is False


def test_particle_only_change_is_dropped_entirely():
    """实测里出现过的那条：“优化了…改善了…” → “优化…改善…”只删了助词，不算改写。"""
    line = "- 优化了页面加载性能，改善了首屏的交互体验"
    resume = "## 工作经历\n" + line + "\n"
    job = "任职要求：\n1. 熟悉前端性能优化\n"
    raw = [
        {
            "requirement_quote": "熟悉前端性能优化",
            "evidence_quote": line,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": {
                "action": "改写",
                "section": "工作经历",
                "original_passage": line,
                "suggested_passage": "- 优化页面加载性能，改善首屏交互体验",
                "rewrite_reason": "优化表达",
            },
        }
    ]
    assert normalize_items(raw, resume, job)[0]["suggestions"] == []


def test_filler_noun_only_change_is_dropped_entirely():
    """实测里出现过的那条：只在“慢查询”后面加个“问题”，没有带来任何信息。"""
    line = "- 参与订单数据表结构调整，配合排查慢查询"
    resume = "## 项目经历\n" + line + "\n"
    job = "任职要求：\n1. 参与数据库表结构设计\n"
    raw = [
        {
            "requirement_quote": "参与数据库表结构设计",
            "evidence_quote": line,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": {
                "action": "改写",
                "section": "项目经历",
                "original_passage": line,
                "suggested_passage": line + "问题",
                "rewrite_reason": "优化表达",
            },
        }
    ]
    assert normalize_items(raw, resume, job)[0]["suggestions"] == []


def test_helper_verb_swap_alone_is_dropped_entirely():
    """实测里出现过的那条：“配合排查” → “协助排查”只换了助动词，必须丢弃。"""
    line = "- 参与前后端接口联调，配合排查线上页面问题"
    resume = "## 工作经历\n" + line + "\n"
    job = "任职要求：\n1. 与前端同学协作完成接口联调与上线\n"
    raw = [
        {
            "requirement_quote": "与前端同学协作完成接口联调与上线",
            "evidence_quote": line,
            "match_status": "需要补充确认",
            "reason": "ok",
            "confirmation_question": "你具体负责了哪一部分？",
            "suggestion": {
                "action": "改写",
                "section": "工作经历",
                "original_passage": line,
                "suggested_passage": "- 参与前后端接口联调，协助排查线上页面问题",
                "rewrite_reason": "优化表达",
            },
        }
    ]
    assert normalize_items(raw, resume, job)[0]["suggestions"] == []


def test_the_same_rewrite_is_only_offered_once_across_requirements():
    """两条要求命中同一句话时，同一条改写只能出现一次。"""
    job = "任职要求：\n1. 熟悉 Python 与 FastAPI\n2. 熟悉 FastAPI 的接口开发\n"
    rewrite = {
        "action": "改写",
        "section": "项目经历",
        "original_passage": ORIGINAL,
        "suggested_passage": "- 使用 Python 和 FastAPI 实现设备借还接口",
        "rewrite_reason": "只把技术栈关键词加粗，没有新增任何事实。",
    }
    raw = [
        {
            "requirement_quote": "熟悉 Python 与 FastAPI",
            "evidence_quote": ORIGINAL,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": dict(rewrite),
        },
        {
            "requirement_quote": "熟悉 FastAPI 的接口开发",
            "evidence_quote": ORIGINAL,
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": dict(rewrite),
        },
    ]
    items = normalize_items(raw, RESUME, job)
    assert len(items) == 2
    assert len(items[0]["suggestions"]) == 1
    assert items[1]["suggestions"] == []


def test_polish_keeps_a_real_wording_change():
    raw = [
        {
            "action": "改写",
            "section": "项目经历",
            "original_passage": "- 数据库表与同学共同设计，后续调整过几次",
            "suggested_passage": "- 与同学共同完成数据库表结构设计，并进行了多次调整",
            "rewrite_reason": "只把表达改得更专业，没有新增任何事实。",
        }
    ]
    polished = normalize_polish(raw, RESUME)
    assert len(polished) == 1
    assert polished[0]["is_question"] is False


def test_real_model_output_for_the_colloquial_resume_is_demoted_not_stored():
    """DeepSeek 对这份简历实际给出的两条“口语→书面”改写，现在必须被降级成提问。

    这两条是真实发生过越界的模型输出（见 docs/test-results.md 第 4.10 节）：
    提示词已经写明不改写口语化表述，但模型偶尔仍会给出，所以由代码兜底。
    """
    for original, suggested in (
        (
            "- 用 Python 和 FastAPI 弄了个设备借还的接口",
            "- 使用 Python 和 FastAPI 实现设备借还接口",
        ),
        (
            "- 数据库表是我和同学一起建的，后面改过几次",
            "- 与同学共同完成数据库表结构设计，并进行了多次调整",
        ),
    ):
        entry = {
            "action": "改写",
            "section": "项目经历",
            "original_passage": original,
            "suggested_passage": suggested,
            "rewrite_reason": "优化表达",
        }
        assert normalize_polish([entry], COLLOQUIAL_RESUME, set()) == []
