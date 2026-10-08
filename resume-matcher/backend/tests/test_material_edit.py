"""编辑素材：岗位（名称/描述）与简历（标题/原稿正文），以及它对快照与修改稿的影响。

这里的重点不是「能不能改」，而是改完之后**哪些东西不许跟着变**：
历史分析快照、已保存的修改稿版本、以及「不勾重置就看不到新原稿」这条容易被误解的规则。
"""
import pytest

import app.llm as llm_module
from tests.conftest import (
    JOB_TEXT,
    RESUME_TEXT,
    create_job,
    create_resume,
    fake_model_output,
    login,
)

NEW_ORIGINAL = "# 张明\n\n## 技能\n- Python、FastAPI、PostgreSQL、Redis\n"

# 新岗位描述必须仍然包含假模型输出的那几条 requirement_quote（逐字），
# 否则接地层会把所有条目丢掉、分析直接失败——那是另一件事，不该混进这个用例。
NEW_JOB_TEXT = (
    "岗位名称：后端开发工程师（Go）\n\n任职要求：\n"
    "1. 熟悉 Python，了解 FastAPI 或 Django 等 Web 框架\n"
    "2. 熟悉 Kubernetes 与 CI/CD 流程\n"
    "3. 熟悉 Spark 或 Flink 等大数据处理框架\n"
)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(llm_module, "request_analysis", lambda *args, **kwargs: fake_model_output())


def _run_analysis(client, resume_id: int, job_id: int) -> dict:
    analysis_id = client.post(
        "/api/analyses", json={"resume_id": resume_id, "job_id": job_id}
    ).json()["id"]
    client.post(f"/api/analyses/{analysis_id}/run")
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    assert detail["status"] == "succeeded", detail
    return detail


def _adopt_one_suggestion(client, detail: dict) -> str:
    """采纳一条建议让修改稿与原稿不同，返回此时的修改稿内容。"""
    adopted = client.post(
        f"/api/suggestions/{detail['suggestions'][0]['id']}/decision", json={"decision": "采纳"}
    )
    assert adopted.status_code == 200, adopted.text
    return adopted.json()["draft_content"]


def test_editing_a_job_updates_title_and_description(client, user_a):
    login(client, "alice")
    job = create_job(client)

    response = client.put(
        f"/api/jobs/{job['id']}",
        json={"title": "后端开发工程师（Go）", "description": NEW_JOB_TEXT},
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "后端开发工程师（Go）"
    assert response.json()["description"] == NEW_JOB_TEXT.strip()
    listed = {row["id"]: row for row in client.get("/api/jobs").json()}
    assert listed[job["id"]]["description"] == NEW_JOB_TEXT.strip()


def test_editing_a_job_rejects_blank_fields(client, user_a):
    login(client, "alice")
    job = create_job(client)

    assert (
        client.put(f"/api/jobs/{job['id']}", json={"title": "   ", "description": "x"}).status_code
        == 400
    )
    assert (
        client.put(f"/api/jobs/{job['id']}", json={"title": "x", "description": "  "}).status_code
        == 400
    )
    assert client.get(f"/api/jobs/{job['id']}").json()["title"] == job["title"]


def test_editing_a_job_requires_your_own_job(client, user_a, user_b):
    login(client, "alice")
    job = create_job(client)

    client.post("/api/auth/logout")
    login(client, "bob")
    stolen = client.put(f"/api/jobs/{job['id']}", json={"title": "偷改", "description": "偷改"})
    assert stolen.status_code == 404, stolen.text

    client.post("/api/auth/logout")
    login(client, "alice")
    assert client.get(f"/api/jobs/{job['id']}").json()["title"] == job["title"]


def test_new_analysis_uses_the_edited_job_but_history_keeps_the_old_snapshot(client, user_a):
    login(client, "alice")
    job = create_job(client)
    resume = create_resume(client)
    before = _run_analysis(client, resume["id"], job["id"])

    client.put(
        f"/api/jobs/{job['id']}",
        json={"title": "改名后的岗位", "description": NEW_JOB_TEXT},
    )
    after = _run_analysis(client, resume["id"], job["id"])

    assert after["job_snapshot"] == NEW_JOB_TEXT.strip()
    assert after["job_title"] == "改名后的岗位"
    # 历史那条一个字都不变：它保存的是发起时的快照。
    kept = client.get(f"/api/analyses/{before['id']}").json()
    assert kept["job_snapshot"] == JOB_TEXT.strip()
    assert kept["job_title"] == job["title"]


def test_editing_a_resume_title_only_keeps_original_and_draft(client, user_a):
    login(client, "alice")
    resume = create_resume(client)

    response = client.put(f"/api/resumes/{resume['id']}", json={"title": "改过的名字"})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "改过的名字"
    assert data["original_text"] == RESUME_TEXT
    assert data["draft_content"] == RESUME_TEXT


def test_editing_the_original_leaves_draft_and_revisions_alone(client, user_a):
    login(client, "alice")
    job = create_job(client)
    resume = create_resume(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    revised = _adopt_one_suggestion(client, detail)
    assert revised != RESUME_TEXT

    saved = client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": "第一版"})
    assert saved.status_code == 201, saved.text

    response = client.put(
        f"/api/resumes/{resume['id']}",
        json={"title": "张明-后端简历", "original_text": NEW_ORIGINAL},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["original_text"] == NEW_ORIGINAL.strip()
    assert data["draft_content"] == revised  # 默认不动修改稿
    assert data["revision_count"] == 1  # 历史版本一条不少
    assert data["latest_revision"]["content_md"] == revised


def test_reset_draft_replaces_the_draft_with_the_new_original(client, user_a):
    login(client, "alice")
    job = create_job(client)
    resume = create_resume(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    revised = _adopt_one_suggestion(client, detail)
    client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": "第一版"})

    response = client.put(
        f"/api/resumes/{resume['id']}",
        json={
            "title": resume["title"],
            "original_text": NEW_ORIGINAL,
            "reset_draft": True,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["draft_content"] == NEW_ORIGINAL.strip()
    # 重置只动工作稿；已经保存的版本仍然是采纳过建议的那一份。
    assert data["revision_count"] == 1
    assert data["latest_revision"]["content_md"] == revised


def test_a_plain_edit_is_invisible_to_analysis_until_the_draft_is_reset(client, user_a):
    """这是最容易被误解的一条：输入取的是「修改稿 or 原稿」，所以只改原稿不生效。"""
    login(client, "alice")
    job = create_job(client)
    resume = create_resume(client)
    _run_analysis(client, resume["id"], job["id"])

    client.put(
        f"/api/resumes/{resume['id']}",
        json={"title": resume["title"], "original_text": NEW_ORIGINAL},
    )
    plain = _run_analysis(client, resume["id"], job["id"])
    assert plain["resume_snapshot"] == RESUME_TEXT  # 仍然是修改稿（此时恰好等于旧原稿）

    client.put(
        f"/api/resumes/{resume['id']}",
        json={"title": resume["title"], "original_text": NEW_ORIGINAL, "reset_draft": True},
    )
    reset = _run_analysis(client, resume["id"], job["id"])
    assert reset["resume_snapshot"] == NEW_ORIGINAL.strip()


def test_editing_a_resume_requires_your_own_resume(client, user_a, user_b):
    login(client, "alice")
    resume = create_resume(client)

    client.post("/api/auth/logout")
    login(client, "bob")
    assert (
        client.put(
            f"/api/resumes/{resume['id']}",
            json={"title": "偷改", "original_text": "偷改"},
        ).status_code
        == 404
    )

    client.post("/api/auth/logout")
    login(client, "alice")
    assert client.get(f"/api/resumes/{resume['id']}").json()["title"] == resume["title"]
