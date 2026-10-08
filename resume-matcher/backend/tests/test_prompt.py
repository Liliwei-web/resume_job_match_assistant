"""The prompt template must stay complete and must not leak placeholders."""
from app.llm import SYSTEM_PROMPT, build_user_prompt


def test_user_prompt_substitutes_all_placeholders():
    text = build_user_prompt("RESUME_BODY", "JOB_TITLE_X", "JOB_DESC_Y")
    assert "RESUME_BODY" in text
    assert "JOB_TITLE_X" in text
    assert "JOB_DESC_Y" in text
    assert "<<" not in text


def test_prompt_covers_all_three_match_statuses():
    for status in ("已体现", "未体现", "需要补充确认"):
        assert status in SYSTEM_PROMPT
    assert "evidence_quote" in SYSTEM_PROMPT


def test_user_prompt_contains_a_second_json_example():
    """The schema block plus the few-shot example both describe match_status."""
    text = build_user_prompt("r", "t", "d")
    assert text.count('"match_status"') >= 2


def test_prompt_pins_the_status_evidence_contract():
    """Reviewers asked for an explicit contract between match_status and evidence_quote."""
    assert "evidence_quote 必须是空字符串" in SYSTEM_PROMPT
    assert "“未体现”与“需要补充确认”的区别" in SYSTEM_PROMPT


def test_prompt_lists_wording_only_rewrite_triggers():
    """The rewrite triggers must stay narrow: wording only, never new facts."""
    assert "口语化或非专业动词" in SYSTEM_PROMPT
    assert "不得高于原文" in SYSTEM_PROMPT


def test_few_shot_example_shows_a_wording_only_suggestion():
    example = build_user_prompt("r", "t", "d").split("===== 示例")[1]
    assert '"suggested_passage"' in example
    assert "没有新增任何事实" in example


def test_prompt_defines_the_suggestion_action_contract():
    """schema 与 few-shot 都要带上 action，并写明“补充”不得携带改写文本。"""
    text = build_user_prompt("r", "t", "d")
    assert text.count('"action"') >= 2
    assert 'action="补充"：suggested_passage 必须是空字符串' in text


def test_prompt_forbids_a_no_op_rewrite():
    """一句“有所提升→得到提升”式的同义替换不算建议，提示词必须写明并要求实质改动。"""
    assert "有实质改动" in SYSTEM_PROMPT
    assert "直接丢弃" in SYSTEM_PROMPT


def test_prompt_requires_evidence_of_the_candidate_own_work():
    """"已体现" 只能由候选人本人的产出支撑，参与／配合一类的模糊线索要降级。"""
    assert "候选人本人" in SYSTEM_PROMPT


def test_prompt_prefers_evidence_that_shows_a_usage_scenario():
    """技能列表里的名字不足以判“已体现”，有使用场景的那一句才是证据。"""
    assert "说明了使用场景" in SYSTEM_PROMPT


def test_prompt_asks_for_requirement_independent_polish_suggestions():
    """口语化句子不对应任何岗位要求时，也要有地方放改写建议。"""
    text = build_user_prompt("r", "t", "d")
    assert text.count('"polish"') >= 2, "schema 与 few-shot 都要包含 polish 数组"
    assert "不对应任何岗位要求" in text

# --- 2026-10-08：改写边界按“先收紧”重写后的新增约束 ---


def test_prompt_keeps_colloquial_rewrites_on_hold():
    """本轮先不开放口语化表述的自动改写：只提示用户自己改，不允许代写。"""
    assert "本轮暂不开放：口语化表述一律不自动改写" in SYSTEM_PROMPT
    assert "不得把改写结果写进 suggested_passage" in SYSTEM_PROMPT


def test_prompt_pins_the_role_boundary_for_weak_verbs():
    """参与／协助／配合一类词只能问角色，不能替用户升级成“负责／主导”。"""
    assert "参与不等于独立负责" in SYSTEM_PROMPT
    assert "参与／协助／配合／帮忙／跟着／跟随" in SYSTEM_PROMPT
    assert "绝不替用户认定" in SYSTEM_PROMPT


def test_prompt_keeps_the_passage_granularity_at_paragraph_level():
    """修改粒度是整段：不下沉到半句，也不合并相邻段落。"""
    assert "修改粒度是整段" in SYSTEM_PROMPT
    assert "更不要把相邻段落合并重写" in SYSTEM_PROMPT


def test_prompt_allows_markdown_formatting_but_bans_ordered_lists():
    """排版本轮放开，但只允许无序列表——有序列表的数字会撞上后端数字闸门。"""
    assert "文字排版（Markdown）" in SYSTEM_PROMPT
    assert "不得使用“1. 2. 3.”这类有序列表" in SYSTEM_PROMPT
    example = build_user_prompt("r", "t", "d").split("===== 示例")[1]
    assert "**\\n" in example, "few-shot 必须示范多行 suggested_passage 的写法"


def test_few_shot_does_not_teach_word_swapping():
    """few-shot 不能再用“编写→实现”“一起完成→协作完成”这类换词当范例。"""
    example = build_user_prompt("r", "t", "d").split("===== 示例")[1]
    assert "实现业务逻辑" not in example
    assert "协作完成上线" not in example
    assert '"polish": []' in example