"""RES-02 / RES-03: the grounding layer must drop anything the model invented."""
from app.models import MATCH_NEEDS_CHECK, MATCH_SHOWN
from app.services.grounding import (
    find_colloquial_marker,
    find_quote,
    normalize_items,
    normalize_polish,
)
from tests.conftest import FAKE_ITEMS, JOB_TEXT, RESUME_TEXT


def test_find_quote_is_whitespace_tolerant_and_returns_original_slice():
    text = "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口"
    quote = "使用   FastAPI + PostgreSQL   实现商品发布、搜索与订单接口"
    assert find_quote(text, quote) == text
    assert find_quote(text, "完全不存在的内容") is None


def test_fabricated_evidence_is_dropped_and_status_downgraded():
    items = normalize_items(FAKE_ITEMS, RESUME_TEXT, JOB_TEXT)
    spark_item = next(i for i in items if "Spark" in i["requirement_quote"])
    assert spark_item["evidence_quote"] is None
    assert spark_item["match_status"] == MATCH_NEEDS_CHECK
    assert spark_item["confirmation_question"]


def test_evidence_is_kept_when_it_exists_in_the_resume():
    items = normalize_items(FAKE_ITEMS, RESUME_TEXT, JOB_TEXT)
    python_item = next(i for i in items if "FastAPI" in i["requirement_quote"])
    assert python_item["match_status"] == MATCH_SHOWN
    assert python_item["evidence_quote"] in RESUME_TEXT
    assert python_item["suggestions"][0]["original_passage"] in RESUME_TEXT


def test_requirement_not_present_in_the_job_is_dropped():
    raw = [
        {
            "requirement_quote": "拥有十年大型分布式系统经验",
            "match_status": "未体现",
            "reason": "模型自造的要求",
        }
    ]
    assert normalize_items(raw, RESUME_TEXT, JOB_TEXT) == []


def test_absent_requirement_always_gets_a_confirmation_question():
    items = normalize_items(FAKE_ITEMS, RESUME_TEXT, JOB_TEXT)
    k8s_item = next(i for i in items if "Kubernetes" in i["requirement_quote"])
    assert k8s_item["match_status"] == "未体现"
    assert k8s_item["confirmation_question"]
    assert k8s_item["suggestions"] == []


def test_suggestion_with_a_passage_not_in_the_resume_is_dropped():
    raw = [
        {
            "requirement_quote": "熟悉 Python，了解 FastAPI 或 Django 等 Web 框架",
            "evidence_quote": "Python、FastAPI、PostgreSQL",
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": {
                "section": "技能",
                "original_passage": "精通 Kubernetes 与服务网格",
                "suggested_passage": "精通 Kubernetes 与服务网格平台",
                "rewrite_reason": "编造的段落",
            },
        }
    ]
    items = normalize_items(raw, RESUME_TEXT, JOB_TEXT)
    assert items[0]["suggestions"] == []


def test_absent_status_never_carries_a_quote():
    """Contradictory output ("未体现" + a quote) must be normalised, not trusted."""
    raw = [
        {
            "requirement_quote": "熟悉 Kubernetes 与 CI/CD 流程",
            "evidence_quote": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
            "match_status": "未体现",
            "reason": "模型自相矛盾",
            "confirmation_question": "你是否使用过 Kubernetes？",
            "suggestion": None,
        }
    ]
    items = normalize_items(raw, RESUME_TEXT, JOB_TEXT)
    assert items[0]["match_status"] == "未体现"
    assert items[0]["evidence_quote"] is None


def test_rewrite_that_invents_a_number_is_blocked_and_becomes_a_question():
    raw = [
        {
            "requirement_quote": "熟悉 Python，了解 FastAPI 或 Django 等 Web 框架",
            "evidence_quote": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "这个接口的日均调用量大概是多少？",
            "suggestion": {
                "section": "项目经历",
                "original_passage": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
                "suggested_passage": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口，日均调用 10 万次",
                "rewrite_reason": "补充量化结果",
            },
        }
    ]
    items = normalize_items(raw, RESUME_TEXT, JOB_TEXT)
    suggestions = items[0]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is True
    assert suggestions[0]["suggested_passage"] is None
    assert "数字" in suggestions[0]["rewrite_reason"]


def test_rewrite_reusing_a_number_already_in_the_resume_is_allowed():
    resume = "## 项目经历\n- 负责 3 人小组的接口联调工作\n"
    job = "任职要求：\n1. 有团队协作经验\n"
    raw = [
        {
            "requirement_quote": "有团队协作经验",
            "evidence_quote": "- 负责 3 人小组的接口联调工作",
            "match_status": "已体现",
            "reason": "ok",
            "confirmation_question": "",
            "suggestion": {
                "section": "项目经历",
                "original_passage": "- 负责 3 人小组的接口联调工作",
                "suggested_passage": "- 负责 3 人小组的接口联调，并推动联调进度",
                "rewrite_reason": "调整语序",
            },
        }
    ]
    items = normalize_items(raw, resume, job)
    assert items[0]["suggestions"][0]["is_question"] is False


def test_polish_entries_must_be_grounded_and_are_deduplicated():
    """表达优化建议同样要逐字接地，并且不能和岗位条目建议重复。"""
    entries = [
        {
            "action": "改写",
            "section": "技能",
            "original_passage": "- Python、FastAPI、PostgreSQL",
            "suggested_passage": "- Python、FastAPI、PostgreSQL 等",
            "rewrite_reason": "保留原意",
        },
        {
            "action": "改写",
            "section": "项目经历",
            "original_passage": "- 简历里根本没有这一行",
            "suggested_passage": "- 更专业的一行",
            "rewrite_reason": "编造的段落",
        },
        {
            "action": "改写",
            "section": "项目经历",
            "original_passage": "- 与两名同学一起完成联调",
            "suggested_passage": "- 与两名同学协作完成联调",
            "rewrite_reason": "只把口语化的“一起完成”改为“协作完成”，没有新增事实",
        },
    ]
    kept = normalize_polish(entries, RESUME_TEXT, {"- Python、FastAPI、PostgreSQL"})
    assert [s["original_passage"] for s in kept] == ["- 与两名同学一起完成联调"]
    assert kept[0]["is_question"] is False


def test_polish_never_emits_a_question_row():
    """polish 只用来改写：标成“补充”却带文本的条目既不该改写也不该变成提问。"""
    entries = [
        {
            "action": "补充",
            "section": "项目经历",
            "original_passage": "- 与两名同学一起完成联调",
            "suggested_passage": "- 与两名同学协作完成联调",
            "rewrite_reason": "r",
        }
    ]
    assert normalize_polish(entries, RESUME_TEXT, set()) == []


# --------------------------------------------------- 口语化闸门（本轮边界：只提问、不改写）
#
# 提示词已经写明「口语化表述一律不自动改写」，但真实模型仍会偶尔给出
# “弄了个 → 实现”这类换词建议，所以这一层用词表兜底：命中就把改写降级成提问。

COLLOQUIAL_RESUME = """# 王强

## 技能
- Python、MySQL、Git

## 项目经历
### 实验室设备借用平台（后端）
- 用 Python 和 FastAPI 弄了个设备借还的接口
- 帮忙看了一下接口慢的问题，做了一些调整
"""

COLLOQUIAL_LINE = "- 用 Python 和 FastAPI 弄了个设备借还的接口"

COLLOQUIAL_ITEMS = [
    {
        "requirement_quote": "熟悉 Python，了解 FastAPI 或 Django 等 Web 框架",
        "evidence_quote": COLLOQUIAL_LINE,
        "match_status": "已体现",
        "reason": "项目里写过 Python 接口",
        "confirmation_question": "",
        "suggestion": {
            "action": "改写",
            "section": "项目经历",
            "original_passage": COLLOQUIAL_LINE,
            "suggested_passage": "- 使用 **Python** 和 **FastAPI** 实现设备借还的接口",
            "rewrite_reason": "把口语动词“弄了个”改为“实现”。",
        },
    }
]


def test_find_colloquial_marker_spots_the_usual_suspects():
    assert find_colloquial_marker(COLLOQUIAL_LINE) == "弄了个"
    assert find_colloquial_marker("- 顺手改了两行配置") == "顺手"
    assert find_colloquial_marker("- 负责线上问题的排查与修复") is None
    assert find_colloquial_marker("") is None


def test_colloquial_rewrite_is_demoted_to_a_question():
    """模型给出的“弄了个 → 实现”不得落库成改写建议。"""
    items = normalize_items(COLLOQUIAL_ITEMS, COLLOQUIAL_RESUME, JOB_TEXT)
    suggestion = items[0]["suggestions"][0]
    assert suggestion["is_question"] is True
    assert suggestion["suggested_passage"] is None
    assert "弄了个" in suggestion["rewrite_reason"]
    assert "自行改写" in suggestion["rewrite_reason"]


def test_colloquial_hint_is_given_even_when_the_model_asked_nothing():
    """降级后必须留下提示，不能因为模型没给 confirmation_question 就整条消失。"""
    raw = [dict(COLLOQUIAL_ITEMS[0])]
    raw[0]["confirmation_question"] = ""
    items = normalize_items(raw, COLLOQUIAL_RESUME, JOB_TEXT)
    suggestions = items[0]["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["is_question"] is True
    assert suggestions[0]["suggested_passage"] is None
    assert suggestions[0]["original_passage"] == COLLOQUIAL_LINE


def test_colloquial_gate_does_not_touch_ordinary_rewrites():
    items = normalize_items(FAKE_ITEMS, RESUME_TEXT, JOB_TEXT)
    python_item = next(i for i in items if "FastAPI" in i["requirement_quote"])
    suggestion = python_item["suggestions"][0]
    assert suggestion["is_question"] is False
    assert suggestion["suggested_passage"]


def test_polish_drops_colloquial_lines_instead_of_asking():
    """polish 没有可以挂问题的岗位要求，所以口语化的行只能被丢掉。"""
    entry = {
        "action": "改写",
        "section": "项目经历",
        "original_passage": "- 帮忙看了一下接口慢的问题，做了一些调整",
        "suggested_passage": "- 排查了接口性能问题并做了相应调整",
        "rewrite_reason": "把口语化的“帮忙看了一下”改成专业表述。",
    }
    assert normalize_polish([entry], COLLOQUIAL_RESUME, set()) == []


def test_polish_still_keeps_ordinary_rewrites():
    entry = {
        "action": "改写",
        "section": "技能",
        "original_passage": "- Python、FastAPI、PostgreSQL",
        "suggested_passage": "- **Python**、**FastAPI**、**PostgreSQL**",
        "rewrite_reason": "只加粗关键词，没有改动任何事实。",
    }
    kept = normalize_polish([entry], RESUME_TEXT, set())
    assert len(kept) == 1
    assert kept[0]["is_question"] is False