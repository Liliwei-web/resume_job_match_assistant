"""RES-07: accounts must never be able to read or modify each other's data."""
import pytest

import app.llm as llm_module
from tests.conftest import RESUME_TEXT, create_job, create_resume, fake_model_output, login


@pytest.fixture(autouse=True)
def fake_model(monkeypatch):
    monkeypatch.setattr(llm_module, "request_analysis", lambda *args, **kwargs: fake_model_output())


def _analysis_for(client, resume_id: int, job_id: int) -> dict:
    analysis_id = client.post(
        "/api/analyses", json={"resume_id": resume_id, "job_id": job_id}
    ).json()["id"]
    client.post(f"/api/analyses/{analysis_id}/run")
    return client.get(f"/api/analyses/{analysis_id}").json()


def test_other_account_cannot_read_or_write(client, user_a, user_b):
    login(client, "alice")
    resume = create_resume(client, title="alice 的简历")
    job = create_job(client)
    analysis = _analysis_for(client, resume["id"], job["id"])
    suggestion_id = analysis["suggestions"][0]["id"]
    client.post(f"/api/suggestions/{suggestion_id}/decision", json={"decision": "采纳"})
    before = client.get(f"/api/resumes/{resume['id']}").json()
    client.post("/api/auth/logout")

    login(client, "bob")
    assert client.get(f"/api/resumes/{resume['id']}").status_code == 404
    assert client.get(f"/api/resumes/{resume['id']}/export").status_code == 404
    assert client.get(f"/api/resumes/{resume['id']}/revisions").status_code == 404
    assert client.get(f"/api/analyses/{analysis['id']}").status_code == 404
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404

    assert (
        client.put(
            f"/api/resumes/{resume['id']}/draft", json={"content_md": "恶意修改"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/suggestions/{suggestion_id}/decision", json={"decision": "忽略"}
        ).status_code
        == 404
    )
    assert (
        client.post(f"/api/resumes/{resume['id']}/revisions", json={"note": "x"}).status_code == 404
    )
    assert (
        client.post(
            "/api/analyses", json={"resume_id": resume["id"], "job_id": job["id"]}
        ).status_code
        == 404
    )

    client.post("/api/auth/logout")
    login(client, "alice")
    after = client.get(f"/api/resumes/{resume['id']}").json()
    assert after["draft_content"] == before["draft_content"]
    assert after["original_text"] == RESUME_TEXT


def test_list_endpoints_only_return_own_rows(client, user_a, user_b):
    login(client, "bob")
    create_resume(client, title="bob 的简历")
    client.post("/api/auth/logout")

    login(client, "alice")
    titles = [item["title"] for item in client.get("/api/resumes").json()]
    assert "bob 的简历" not in titles


def test_anonymous_requests_are_rejected(client):
    assert client.get("/api/resumes").status_code == 401
    assert client.get("/api/analyses").status_code == 401
    assert client.get("/api/jobs").status_code == 401
