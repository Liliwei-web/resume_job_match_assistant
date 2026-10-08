"""删除简历 / 岗位：二次确认要用的计数、级联范围、越权与「分析进行中」的拦截。"""
import pytest
from sqlalchemy import func, select, update

import app.llm as llm_module
from app.models import (
    ANALYSIS_FAILED,
    ANALYSIS_RUNNING,
    AnalysisItem,
    AnalysisTask,
    ItemSupplement,
    Resume,
    Revision,
    Suggestion,
)
from tests.conftest import create_job, create_resume, fake_model_output, login

# 只用了用户输入里出现过的词，否则会被 grounding 判成模型自己加的内容。
POLISHED = "参与实验室项目的服务部署"


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(llm_module, "request_analysis", lambda *args, **kwargs: fake_model_output())
    monkeypatch.setattr(
        llm_module,
        "request_supplement_polish",
        lambda text, requirement, question="", violations=None: {
            "polished": POLISHED,
            "reason": "只把口语改成书面表达",
            "section": "技能",
        },
    )


def _run_analysis(client, resume_id: int, job_id: int) -> dict:
    analysis_id = client.post(
        "/api/analyses", json={"resume_id": resume_id, "job_id": job_id}
    ).json()["id"]
    client.post(f"/api/analyses/{analysis_id}/run")
    detail = client.get(f"/api/analyses/{analysis_id}").json()
    assert detail["status"] == "succeeded", detail
    return detail


def _count(db, model, **filters) -> int:
    query = select(func.count()).select_from(model)
    for column, value in filters.items():
        query = query.where(getattr(model, column) == value)
    return int(db.scalar(query) or 0)


def _prepare_resume(client, detail: dict) -> dict:
    """跑完一次分析、采纳一条建议 + 一条补充，并存一版修改稿，返回简历详情。"""
    suggestion_id = detail["suggestions"][0]["id"]
    adopted = client.post(f"/api/suggestions/{suggestion_id}/decision", json={"decision": "采纳"})
    assert adopted.status_code == 200, adopted.text

    hidden = next(item for item in detail["items"] if item["match_status"] == "未体现")
    polished = client.post(
        "/api/supplement",
        json={"analysis_id": detail["id"], "item_id": hidden["id"], "text": "我在实验室里弄过部署"},
    )
    assert polished.status_code == 201, polished.text
    decided = client.post(
        f"/api/supplements/{polished.json()['supplement']['id']}/decision",
        json={"decision": "采纳"},
    )
    assert decided.status_code == 200, decided.text

    revision = client.post(f"/api/resumes/{detail['resume_id']}/revisions", json={"note": ""})
    assert revision.status_code == 201, revision.text
    return client.get(f"/api/resumes/{detail['resume_id']}").json()


def test_resume_deletion_preview_counts_what_will_be_lost(client, user_a):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    _prepare_resume(client, detail)

    preview = client.get(f"/api/resumes/{resume['id']}/deletion-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "title": "测试简历",
        "adopted_suggestions": 1,
        "adopted_supplements": 1,
        "analysis_count": 1,
        "revision_count": 1,
        "running_analysis_count": 0,
    }


def test_deleting_a_resume_removes_every_child_row(client, user_a, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    _prepare_resume(client, detail)

    assert client.delete(f"/api/resumes/{resume['id']}").status_code == 204

    assert client.get(f"/api/resumes/{resume['id']}").status_code == 404
    assert client.get(f"/api/analyses/{detail['id']}").status_code == 404
    assert _count(db, Resume, id=resume["id"]) == 0
    assert _count(db, Revision, resume_id=resume["id"]) == 0
    assert _count(db, AnalysisTask, resume_id=resume["id"]) == 0
    assert _count(db, AnalysisItem, analysis_id=detail["id"]) == 0
    assert _count(db, Suggestion, analysis_id=detail["id"]) == 0
    assert _count(db, ItemSupplement, analysis_id=detail["id"]) == 0
    # 岗位是账号级的素材，不该跟着简历一起消失
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200


def test_another_user_cannot_preview_or_delete(client, user_a, user_b, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    _prepare_resume(client, detail)

    client.post("/api/auth/logout")
    login(client, "bob")
    assert client.get(f"/api/resumes/{resume['id']}/deletion-preview").status_code == 404
    assert client.delete(f"/api/resumes/{resume['id']}").status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/deletion-preview").status_code == 404
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 404

    # bob 的越权尝试不能动到 alice 的数据
    assert _count(db, Resume, id=resume["id"]) == 1
    assert _count(db, AnalysisTask, id=detail["id"]) == 1
    assert _count(db, Suggestion, analysis_id=detail["id"]) > 0
    assert client.get(f"/api/analyses/{detail['id']}").status_code == 404  # bob 看不到


def test_delete_is_blocked_while_an_analysis_is_running(client, user_a, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    db.execute(
        update(AnalysisTask).where(AnalysisTask.id == detail["id"]).values(status=ANALYSIS_RUNNING)
    )
    db.commit()

    blocked = client.delete(f"/api/resumes/{resume['id']}")
    assert blocked.status_code == 409, blocked.text
    assert "正在进行" in blocked.json()["detail"]
    assert (
        client.get(f"/api/resumes/{resume['id']}/deletion-preview").json()[
            "running_analysis_count"
        ]
        == 1
    )

    db.execute(
        update(AnalysisTask).where(AnalysisTask.id == detail["id"]).values(status=ANALYSIS_FAILED)
    )
    db.commit()
    assert client.delete(f"/api/resumes/{resume['id']}").status_code == 204


def test_deleting_a_job_keeps_the_analyses_and_only_nulls_the_reference(client, user_a, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])

    preview = client.get(f"/api/jobs/{job['id']}/deletion-preview").json()
    assert preview == {"title": "后端开发工程师", "analysis_count": 1, "resume_count": 1}

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204

    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    db.expire_all()
    task = db.get(AnalysisTask, detail["id"])
    assert task is not None, "删岗位不应该删掉分析记录"
    assert task.job_id is None
    assert task.job_title_snapshot == "后端开发工程师"
    # 分析详情仍然完整可读，岗位名走快照
    after = client.get(f"/api/analyses/{detail['id']}").json()
    assert after["job_id"] is None
    assert after["job_title"] == "后端开发工程师"
    assert len(after["items"]) == len(detail["items"])
    # 简历本身不受影响
    assert client.get(f"/api/resumes/{resume['id']}").status_code == 200

# ---------------------------------------------------------------------------
# 分析记录的删除：单条 + 批量。级联清掉条目/建议/补充，但不动已保存的修改稿。
# ---------------------------------------------------------------------------


def test_deleting_one_analysis_removes_its_children_but_keeps_the_draft(client, user_a, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    detail = _run_analysis(client, resume["id"], job["id"])
    prepared = _prepare_resume(client, detail)
    draft_before = prepared["draft_content"]
    assert draft_before and prepared["revision_count"] == 1

    assert client.delete(f"/api/analyses/{detail['id']}").status_code == 204

    assert client.get(f"/api/analyses/{detail['id']}").status_code == 404
    assert _count(db, AnalysisTask, id=detail["id"]) == 0
    assert _count(db, AnalysisItem, analysis_id=detail["id"]) == 0
    assert _count(db, Suggestion, analysis_id=detail["id"]) == 0
    assert _count(db, ItemSupplement, analysis_id=detail["id"]) == 0

    # 已保存的修改稿与版本不跟着消失：删除分析不该回滚用户已经采纳的内容
    db.expire_all()
    after = client.get(f"/api/resumes/{resume['id']}").json()
    assert after["draft_content"] == draft_before
    assert after["revision_count"] == 1
    assert _count(db, Revision, resume_id=resume["id"]) == 1
    # 简历与岗位都还在
    assert client.get(f"/api/jobs/{job['id']}").status_code == 200


def test_bulk_delete_only_touches_your_own_rows(client, user_a, user_b, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    mine = _run_analysis(client, resume["id"], job["id"])

    client.post("/api/auth/logout")
    login(client, "bob")
    bob_resume = create_resume(client, title="bob 的简历")
    bob_job = create_job(client, title="bob 的岗位")
    ours = _run_analysis(client, bob_resume["id"], bob_job["id"])

    response = client.post("/api/analyses/bulk-delete", json={"ids": [ours["id"], mine["id"]]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted"] == [ours["id"]]
    assert body["missing"] == [mine["id"]], "别人的 id 只能当作不存在"

    assert _count(db, AnalysisTask, id=ours["id"]) == 0
    assert _count(db, AnalysisTask, id=mine["id"]) == 1
    assert _count(db, Suggestion, analysis_id=mine["id"]) > 0


def test_bulk_delete_is_blocked_while_any_of_them_is_running(client, user_a, db):
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    done = _run_analysis(client, resume["id"], job["id"])
    running = client.post("/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]}).json()

    db.execute(
        update(AnalysisTask).where(AnalysisTask.id == running["id"]).values(status=ANALYSIS_RUNNING)
    )
    db.commit()

    blocked = client.post(
        "/api/analyses/bulk-delete", json={"ids": [done["id"], running["id"]]}
    )
    assert blocked.status_code == 409, blocked.text
    assert "进行中" in blocked.json()["detail"]
    # 整批都不动，避免删一半留下不一致的状态
    assert _count(db, AnalysisTask, id=done["id"]) == 1
    assert _count(db, AnalysisTask, id=running["id"]) == 1

    # 单独删这条进行中的也不行
    single = client.delete(f"/api/analyses/{running['id']}")
    assert single.status_code == 409, single.text


def test_bulk_delete_rejects_an_empty_or_oversized_list(client, user_a):
    login(client, "alice")
    assert client.post("/api/analyses/bulk-delete", json={"ids": []}).status_code == 422
    assert (
        client.post("/api/analyses/bulk-delete", json={"ids": list(range(1, 300))}).status_code == 422
    )
    # 全是不存在的 id 时按“没有可删的记录”处理，而不是静默成功
    assert client.post("/api/analyses/bulk-delete", json={"ids": [999999]}).status_code == 404

def test_a_queued_but_never_run_analysis_does_not_block_deletion(client, user_a, db):
    """建了任务却没跑（pending）不该永久挡住删除——本轮补的一个死角。

    pending 不会写任何数据，后台任务在 run_analysis_task 里找不到记录会直接返回，
    所以它既可以被删，也不该算作「进行中的分析」挡住简历删除。
    """
    login(client, "alice")
    resume = create_resume(client)
    job = create_job(client)
    queued = client.post("/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]}).json()
    assert queued["status"] == "pending"

    assert client.delete(f"/api/analyses/{queued['id']}").status_code == 204
    assert _count(db, AnalysisTask, id=queued["id"]) == 0

    client.post("/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]})
    preview = client.get(f"/api/resumes/{resume['id']}/deletion-preview").json()
    assert preview["running_analysis_count"] == 0, "pending 不该算进行中"
    assert client.delete(f"/api/resumes/{resume['id']}").status_code == 204
