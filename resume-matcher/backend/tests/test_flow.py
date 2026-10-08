"""End-to-end flow: analyse, accept / ignore, save, export."""
import pytest

import app.llm as llm_module
from app.models import DECISION_IGNORED, DECISION_PENDING
from tests.conftest import (
    FAKE_ITEMS,
    JOB_TEXT,
    RESUME_TEXT,
    create_job,
    create_resume,
    fake_model_output,
    login,
)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(llm_module, "request_analysis", lambda *args, **kwargs: fake_model_output())


def _run_analysis(client, resume_id: int, job_id: int) -> dict:
    created = client.post("/api/analyses", json={"resume_id": resume_id, "job_id": job_id})
    assert created.status_code == 201, created.text
    analysis_id = created.json()["id"]
    run = client.post(f"/api/analyses/{analysis_id}/run")
    assert run.status_code == 200, run.text
    detail = client.get(f"/api/analyses/{analysis_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_analysis_is_grounded_and_stored(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    assert detail["status"] == "succeeded"
    assert len(detail["items"]) == 3
    assert detail["model_name"] == "deepseek-chat"
    statuses = {item["match_status"] for item in detail["items"]}
    assert statuses == {"已体现", "未体现", "需要补充确认"}


def test_accept_updates_only_the_draft(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    suggestion = detail["suggestions"][0]

    accepted = client.post(
        f"/api/suggestions/{suggestion['id']}/decision", json={"decision": "采纳"}
    )
    assert accepted.status_code == 200, accepted.text
    draft = accepted.json()["draft_content"]
    assert suggestion["suggested_passage"] in draft
    assert suggestion["original_passage"] not in draft

    fetched = client.get(f"/api/resumes/{resume['id']}").json()
    assert fetched["original_text"] == RESUME_TEXT


def test_repeated_accept_does_not_insert_twice(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    suggestion = detail["suggestions"][0]

    client.post(f"/api/suggestions/{suggestion['id']}/decision", json={"decision": "采纳"})
    first = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    second = client.post(
        f"/api/suggestions/{suggestion['id']}/decision", json={"decision": "采纳"}
    )
    assert second.status_code == 200
    assert second.json()["draft_content"] == first
    assert second.json()["draft_content"].count(suggestion["suggested_passage"]) == 1


def test_ignore_does_not_change_the_body(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    suggestion = detail["suggestions"][0]

    ignored = client.post(
        f"/api/suggestions/{suggestion['id']}/decision", json={"decision": "忽略"}
    )
    assert ignored.status_code == 200
    assert ignored.json()["draft_content"] == RESUME_TEXT
    assert ignored.json()["suggestion"]["decision"] == DECISION_IGNORED


def test_reset_to_pending_restores_the_body_so_it_can_be_accepted_again(client, user_a):
    """撤销（回到“未处理”）必须和“忽略”一样还原正文。

    否则状态回退了、正文却还是改写稿，再次采纳会 409「原段落未在当前修改稿中找到」。
    """
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    suggestion = detail["suggestions"][0]
    endpoint = f"/api/suggestions/{suggestion['id']}/decision"

    accepted = client.post(endpoint, json={"decision": "采纳"})
    assert accepted.status_code == 200, accepted.text
    rewritten = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    assert suggestion["suggested_passage"] in rewritten

    reverted = client.post(endpoint, json={"decision": "未处理"})
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["suggestion"]["decision"] == DECISION_PENDING
    assert reverted.json()["draft_content"] == RESUME_TEXT  # 逐字还原，原始稿一分不差

    again = client.post(endpoint, json={"decision": "采纳"})
    assert again.status_code == 200, again.text
    assert again.json()["draft_content"] == rewritten


def test_export_saves_the_current_draft_first_and_returns_it(client, user_a):
    """从没保存过也能导出：导出前先把当前工作稿存成一版，导出的就是最新内容。"""
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    client.post(f"/api/suggestions/{detail['suggestions'][0]['id']}/decision", json={"decision": "采纳"})
    adopted = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]

    payload = client.get(f"/api/resumes/{resume['id']}/export").json()
    assert payload["revision_version"] == 1
    assert payload["content"] == adopted
    assert payload["draft_dirty"] is False
    # 这次自动保存会出现在版本列表里，用户能看到导出的是哪一版
    revisions = client.get(f"/api/resumes/{resume['id']}/revisions").json()
    assert [r["version"] for r in revisions] == [1]
    assert "需要补充确认" not in payload["content"]
    assert "修改理由" not in payload["content"]


def test_export_does_not_add_a_version_when_the_draft_is_already_saved(client, user_a):
    """工作稿与最近保存的版本一致时，导出不会再存一版。"""
    login(client, "alice")
    resume = create_resume(client)
    saved = client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": ""}).json()

    first = client.get(f"/api/resumes/{resume['id']}/export").json()
    second = client.get(f"/api/resumes/{resume['id']}/export").json()
    assert first["revision_version"] == second["revision_version"] == saved["version"]
    assert first["content"] == saved["content_md"]
    assert len(client.get(f"/api/resumes/{resume['id']}/revisions").json()) == 1


def test_unsaved_draft_is_saved_before_export(client, user_a):
    """工作稿有未保存改动时，导出会先把它存成一版，导出的是新内容而不是旧版本。"""
    login(client, "alice")
    resume = create_resume(client)
    client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": ""})
    client.put(
        f"/api/resumes/{resume['id']}/draft", json={"content_md": RESUME_TEXT + "\n- 新增一行"}
    )

    payload = client.get(f"/api/resumes/{resume['id']}/export").json()
    assert payload["draft_dirty"] is False
    assert "新增一行" in payload["content"]
    assert payload["revision_version"] == 2


def test_new_analysis_does_not_overwrite_the_saved_revision(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    client.post(
        f"/api/suggestions/{detail['suggestions'][0]['id']}/decision", json={"decision": "采纳"}
    )
    saved = client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": ""}).json()

    second_job = create_job(
        client, title="数据工程师", description=JOB_TEXT.replace("后端开发工程师", "数据工程师")
    )
    second = _run_analysis(client, resume["id"], second_job["id"])
    assert second["id"] != detail["id"]
    assert second["resume_snapshot"] == saved["content_md"]
    assert second["resume_snapshot"] != detail["resume_snapshot"]

    export = client.get(f"/api/resumes/{resume['id']}/export").json()
    assert export["content"] == saved["content_md"]


def test_failed_run_keeps_inputs_and_can_be_retried(client, user_a, monkeypatch):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)

    def boom(*args, **kwargs):
        raise llm_module.LLMError("模拟模型超时")

    monkeypatch.setattr(llm_module, "request_analysis", boom)
    detail = _run_analysis(client, resume["id"], job["id"])
    assert detail["status"] == "failed"
    assert "模拟模型超时" in detail["error_message"]

    monkeypatch.setattr(llm_module, "request_analysis", lambda *a, **k: fake_model_output())
    assert client.post(f"/api/analyses/{detail['id']}/run").status_code == 200
    after = client.get(f"/api/analyses/{detail['id']}").json()
    assert after["status"] == "succeeded"
    assert client.get(f"/api/resumes/{resume['id']}").json()["original_text"] == RESUME_TEXT


def test_analysis_starts_as_an_explicit_task(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    created = client.post("/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]})
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["item_count"] == 0


def test_polish_suggestion_needs_no_matching_requirement(client, user_a, monkeypatch):
    """口语化句子即使不对应任何岗位要求，也要能拿到改写建议并采纳进修改稿。"""
    polish_entry = {
        "action": "改写",
        "section": "项目经历",
        "original_passage": "- 与两名同学一起完成联调",
        "suggested_passage": "- 与两名同学协作完成联调",
        "rewrite_reason": "只把口语化的“一起完成”改为“协作完成”，没有新增任何事实",
    }
    monkeypatch.setattr(
        llm_module,
        "request_analysis",
        lambda *a, **k: fake_model_output(polish=[polish_entry]),
    )
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    stored = [
        s for s in detail["suggestions"] if s["original_passage"] == polish_entry["original_passage"]
    ]
    assert len(stored) == 1, "表达优化建议没有被保存"
    assert stored[0]["is_question"] is False

    decided = client.post(
        f"/api/suggestions/{stored[0]['id']}/decision", json={"decision": "采纳"}
    )
    assert decided.status_code == 200, decided.text
    assert "- 与两名同学协作完成联调" in decided.json()["draft_content"]
    assert (
        client.get(f"/api/resumes/{resume['id']}").json()["original_text"] == RESUME_TEXT
    ), "原稿必须保持不变"


def test_analysis_summary_exposes_the_three_state_counts(client, user_a):
    """工作台的匹配概览直接读落库的三态计数，这里确认它和逐条判断完全一致。"""
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    expected = {"已体现": 0, "未体现": 0, "需要补充确认": 0}
    for item in detail["items"]:
        expected[item["match_status"]] += 1
    assert sum(expected.values()) == len(detail["items"])

    def listed():
        rows = client.get("/api/analyses").json()
        return [row for row in rows if row["id"] == detail["id"]][0]

    summary = listed()
    assert summary["status_counts"] == expected
    assert sum(summary["status_counts"].values()) == summary["item_count"]
    assert summary["adopted_suggestion_count"] == 0

    rewritable = [
        s for s in detail["suggestions"] if not s["is_question"] and s["suggested_passage"]
    ]
    assert rewritable, "测试数据里应至少有一条可采纳的改写建议"
    accepted = client.post(
        f"/api/suggestions/{rewritable[0]['id']}/decision", json={"decision": "采纳"}
    )
    assert accepted.status_code == 200, accepted.text
    assert listed()["adopted_suggestion_count"] == 1
    assert listed()["status_counts"] == expected


def test_colloquial_rewrite_never_reaches_the_suggestion_list(client, user_a, monkeypatch):
    """RES-02：模型偶尔会给“弄了个 → 实现”这类换词，代码层必须把它降级成提问。"""
    plain_line = "- 使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口"
    colloquial_line = "- 用 FastAPI 和 PostgreSQL 弄了个商品发布、搜索与订单的接口"
    colloquial_resume = RESUME_TEXT.replace(plain_line, colloquial_line)
    item = {
        "requirement_quote": "熟悉 Python，了解 FastAPI 或 Django 等 Web 框架",
        "evidence_quote": colloquial_line,
        "match_status": "已体现",
        "reason": "项目里用过 FastAPI",
        "confirmation_question": "",
        "suggestion": {
            "action": "改写",
            "section": "项目经历",
            "original_passage": colloquial_line,
            "suggested_passage": "- 使用 **FastAPI** 与 **PostgreSQL** 实现商品发布、搜索与订单接口",
            "rewrite_reason": "把口语动词“弄了个”改为“实现”。",
        },
    }
    monkeypatch.setattr(
        llm_module, "request_analysis", lambda *a, **k: fake_model_output(items=[item])
    )
    login(client, "alice")
    resume = create_resume(client, text=colloquial_resume)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    assert detail["status"] == "succeeded"
    stored = detail["suggestions"]
    assert len(stored) == 1
    assert stored[0]["is_question"] is True
    assert stored[0]["suggested_passage"] is None
    assert "弄了个" in stored[0]["rewrite_reason"]
    # 原文这一行本身仍然要能被用户看到（作为提问挂在条目上）
    assert detail["items"][0]["evidence_quote"] == colloquial_line
    # 没有任何可采纳的改写，修改稿必须还是原稿
    assert client.get(f"/api/resumes/{resume['id']}").json()["draft_content"] == colloquial_resume
