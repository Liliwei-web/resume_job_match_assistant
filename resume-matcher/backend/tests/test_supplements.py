"""补充「未体现 / 需要补充确认」条目：润色、写入修改稿、幂等与事实边界。"""
import pytest

import app.llm as llm_module
from app.services.grounding import supplement_violations
from tests.conftest import (
    JOB_TEXT,
    RESUME_TEXT,
    create_job,
    create_resume,
    fake_model_output,
    login,
)

# 一条未体现（无证据）、一条需要补充确认（有逐字证据），覆盖两种插入策略。
SUPPLEMENT_ITEMS = [
    {
        "requirement_quote": "熟悉 Kubernetes 与 CI/CD 流程",
        "evidence_quote": "",
        "match_status": "未体现",
        "reason": "简历中没有出现容器编排与流水线相关线索",
        "confirmation_question": "你是否在实际项目里用过 Kubernetes 或 CI/CD？",
        "suggestion": None,
    },
    {
        "requirement_quote": "熟悉 PostgreSQL 或 MySQL 等关系型数据库",
        "evidence_quote": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
        "match_status": "需要补充确认",
        "reason": "只写了用 PostgreSQL，没有说明负责范围与数据规模",
        "confirmation_question": "你负责了哪些表结构设计？数据量级大概多少？",
        "suggestion": None,
    },
]

# 只用了用户输入里出现过的词（实验室、部署），否则会被 grounding 判为模型自己加的内容。
POLISHED = "参与实验室项目的服务部署"


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(
        llm_module, "request_analysis", lambda *args, **kwargs: fake_model_output(SUPPLEMENT_ITEMS)
    )
    monkeypatch.setattr(
        llm_module,
        "request_supplement_polish",
        lambda text, requirement, question="", violations=None: {
            "polished": POLISHED,
            "reason": "只把口语表达改写成书面表达，没有新增任何事实",
            "section": "技能",
        },
    )


def _analyse(client):
    resume = create_resume(client)
    job = create_job(client)
    created = client.post("/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]})
    analysis_id = created.json()["id"]
    client.post(f"/api/analyses/{analysis_id}/run")
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    assert detail["status"] == "succeeded", detail
    return resume, detail


def _item(detail, status: str) -> dict:
    return next(item for item in detail["items"] if item["match_status"] == status)


def _supplement(client, analysis_id: int, item_id: int, text: str = "我在实验室里弄过部署"):
    return client.post(
        "/api/supplement", json={"analysis_id": analysis_id, "item_id": item_id, "text": text}
    )


def test_violations_only_flag_what_the_model_added():
    assert supplement_violations("参加实验室部署", "参加实验室部署") == []
    # 用户自己写了 Docker，模型沿用 —— 合法
    assert supplement_violations("用 Docker 部署服务", "用 Docker 部署服务") == []
    # 用户没写 Docker，模型自己加 —— 越界
    assert "Docker" in supplement_violations("用 Docker 部署服务", "参与过服务部署")
    assert "数字/量化指标" in supplement_violations("提升 30%", "做了一些优化")


def test_supplement_is_polished_but_not_written_before_accepting(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")

    response = _supplement(client, detail["id"], item["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supplement"]["user_input"] == "我在实验室里弄过部署"
    assert body["supplement"]["polished_text"] == POLISHED
    assert body["supplement"]["decision"] == "未处理"
    assert body["item"]["supplement_state"] == "待处理"

    draft = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    assert draft == RESUME_TEXT, "没有点采纳之前不能写入修改稿"


def test_accept_inserts_into_the_section_and_marks_the_item(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    decided = client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    assert decided.status_code == 200, decided.text
    body = decided.json()
    draft = body["draft_content"]
    assert body["item"]["supplement_state"] == "已补充"
    # 无证据的条目：插到「技能」小节最后一行之后、下一个标题之前
    lines = draft.splitlines()
    assert lines[lines.index("- Python、FastAPI、PostgreSQL") + 1] == f"- {POLISHED}"
    assert draft.index(f"- {POLISHED}") < draft.index("## 项目经历")
    # 原稿永远不动
    assert client.get(f"/api/resumes/{resume['id']}").json()["original_text"] == RESUME_TEXT


def test_accept_with_evidence_inserts_right_after_that_line(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "需要补充确认")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]
    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})

    draft = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    lines = draft.splitlines()
    evidence_line = "- 使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口"
    assert lines[lines.index(evidence_line) + 1] == f"- {POLISHED}"


def test_repeated_accept_never_inserts_twice(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    first = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    second = client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    assert second.status_code == 200
    assert second.json()["draft_content"] == first
    assert second.json()["draft_content"].count(f"- {POLISHED}") == 1


def test_undo_removes_the_inserted_block(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    undone = client.post(
        f"/api/supplements/{supplement['id']}/decision", json={"decision": "未处理"}
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["draft_content"] == RESUME_TEXT
    assert undone.json()["item"]["supplement_state"] == "待处理"


def test_undo_also_clears_the_fallback_heading(client, user_a, monkeypatch):
    """兜底路径会自己补一个「## 补充信息」标题，撤销时必须连标题一起清掉。"""
    monkeypatch.setattr(
        llm_module,
        "request_supplement_polish",
        lambda text, requirement, question="", violations=None: {
            "polished": POLISHED,
            "reason": "改写",
            "section": "其他",
        },
    )
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    adopted = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    assert "补充信息" in adopted

    undone = client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "未处理"})
    assert undone.status_code == 200, undone.text
    assert "补充信息" not in undone.json()["draft_content"]
    assert undone.json()["draft_content"] == RESUME_TEXT


def test_undo_restores_exactly_when_the_section_is_last_and_unterminated(client, user_a):
    """小节落在文末、原文又没有结尾换行时，撤销也必须逐字还原（不能多留一个换行）。"""
    login(client, "alice")
    text = "# 张明\n\n## 技能\n- Python、FastAPI、PostgreSQL"
    resume = create_resume(client, text=text)
    job = create_job(client)
    analysis_id = client.post(
        "/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]}
    ).json()["id"]
    client.post(f"/api/analyses/{analysis_id}/run")
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})
    adopted = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    assert adopted == f"{text}\n- {POLISHED}\n"

    undone = client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "未处理"})
    assert undone.status_code == 200, undone.text
    assert undone.json()["draft_content"] == text


def test_ignore_keeps_the_draft_and_resets_the_item(client, user_a):
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    ignored = client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "忽略"})
    assert ignored.status_code == 200, ignored.text
    assert ignored.json()["draft_content"] == RESUME_TEXT
    assert ignored.json()["item"]["supplement_state"] == "未补充"


def test_invented_term_is_rejected_and_never_reaches_the_draft(client, user_a, monkeypatch):
    """模型自己加了用户没说过的技术栈 —— 重试后仍越界，必须报错且不落库。"""
    monkeypatch.setattr(
        llm_module,
        "request_supplement_polish",
        lambda text, requirement, question="", violations=None: {
            "polished": "使用 Kubernetes 完成服务部署",
            "reason": "优化表达",
            "section": "项目经历",
        },
    )
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")

    response = _supplement(client, detail["id"], item["id"], "我参与过服务部署")
    assert response.status_code == 422, response.text
    assert "Kubernetes" in response.json()["detail"]

    after = client.get(f"/api/analyses/{detail['id']}").json()
    assert _item(after, "未体现")["supplement"] is None
    assert client.get(f"/api/resumes/{resume['id']}").json()["draft_content"] == RESUME_TEXT


def test_second_attempt_after_warning_can_still_succeed(client, user_a, monkeypatch):
    """第一次越界、第二次收敛 —— 应该照常返回，并说明重试过。"""
    calls: list[list[str] | None] = []

    def flaky(text, requirement, question="", violations=None):
        calls.append(violations)
        if len(calls) == 1:
            return {"polished": "使用 Kubernetes 部署服务", "reason": "优化", "section": "项目经历"}
        return {"polished": POLISHED, "reason": "去掉了新增的术语", "section": "项目经历"}

    monkeypatch.setattr(llm_module, "request_supplement_polish", flaky)
    login(client, "alice")
    _, detail = _analyse(client)
    item = _item(detail, "未体现")

    response = _supplement(client, detail["id"], item["id"], "我参与过服务部署")
    assert response.status_code == 201, response.text
    assert len(calls) == 2
    assert calls[0] in (None, [])
    assert "Kubernetes" in (calls[1] or [])


def test_unknown_section_falls_back_to_a_trailing_block(client, user_a, monkeypatch):
    monkeypatch.setattr(
        llm_module,
        "request_supplement_polish",
        lambda text, requirement, question="", violations=None: {
            "polished": POLISHED,
            "reason": "改写",
            "section": "其他",
        },
    )
    login(client, "alice")
    resume, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]
    client.post(f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"})

    draft = client.get(f"/api/resumes/{resume['id']}").json()["draft_content"]
    assert draft.rstrip().endswith(f"- {POLISHED}")


def test_other_users_cannot_touch_the_supplement(client, user_a, user_b):
    login(client, "alice")
    _, detail = _analyse(client)
    item = _item(detail, "未体现")
    supplement = _supplement(client, detail["id"], item["id"]).json()["supplement"]

    client.post("/api/auth/logout")
    login(client, "bob")
    assert _supplement(client, detail["id"], item["id"]).status_code == 404
    assert (
        client.post(
            f"/api/supplements/{supplement['id']}/decision", json={"decision": "采纳"}
        ).status_code
        == 404
    )
