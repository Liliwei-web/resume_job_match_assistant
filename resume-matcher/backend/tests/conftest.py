"""Test bootstrap: a throwaway SQLite database and shared fixtures."""
import os
import pathlib
import tempfile

_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "resume_matcher_test.db"
if _DB_PATH.exists():
    _DB_PATH.unlink()

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_DB_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-1234"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "deepseek-chat"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import hash_password

JOB_TEXT = """岗位名称：后端开发工程师

任职要求：
1. 熟悉 Python，了解 FastAPI 或 Django 等 Web 框架
2. 熟悉 PostgreSQL 或 MySQL 等关系型数据库
3. 熟悉 Kubernetes 与 CI/CD 流程
4. 熟悉 Spark 或 Flink 等大数据处理框架
"""

RESUME_TEXT = """# 张明

## 技能
- Python、FastAPI、PostgreSQL

## 项目经历
### 校园二手交易平台
- 使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口
- 与两名同学一起完成联调
"""

# Model output used by the tests. The third item deliberately fabricates evidence
# that is not present in the resume: the grounding layer must downgrade it.
FAKE_ITEMS = [
    {
        "requirement_quote": "熟悉 Python，了解 FastAPI 或 Django 等 Web 框架",
        "evidence_quote": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
        "match_status": "已体现",
        "reason": "简历中有 FastAPI 项目经验",
        "confirmation_question": "",
        "suggestion": {
            "section": "项目经历",
            "original_passage": "使用 FastAPI + PostgreSQL 实现商品发布、搜索与订单接口",
            "suggested_passage": "使用 FastAPI + PostgreSQL 设计并实现商品发布、搜索与订单接口",
            "rewrite_reason": "补充“设计并”，说明个人职责",
        },
    },
    {
        "requirement_quote": "熟悉 Kubernetes 与 CI/CD 流程",
        "evidence_quote": "",
        "match_status": "未体现",
        "reason": "简历中没有相关描述",
        "confirmation_question": "你是否在实际项目中使用过 Kubernetes 或 CI/CD 流程？",
        "suggestion": None,
    },
    {
        "requirement_quote": "熟悉 Spark 或 Flink 等大数据处理框架",
        "evidence_quote": "熟练使用 Spark 处理亿级数据",
        "match_status": "已体现",
        "reason": "（模型编造的证据）",
        "confirmation_question": "",
        "suggestion": None,
    },
]


def fake_model_output(items=None, polish=None) -> dict:
    """``app.llm.request_analysis`` 的返回结构：逐条要求 + 与要求无关的表达优化。"""
    return {"items": FAKE_ITEMS if items is None else items, "polish": polish or []}


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def user_a(db):
    return ensure_user(db, "alice")


@pytest.fixture()
def user_b(db):
    return ensure_user(db, "bob")


def ensure_user(db, username: str, password: str = "pw123456") -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, display_name=username, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def login(client, username: str, password: str = "pw123456") -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text


def create_resume(client, title: str = "测试简历", text: str = RESUME_TEXT) -> dict:
    response = client.post("/api/resumes", json={"title": title, "original_text": text})
    assert response.status_code == 201, response.text
    return response.json()


def create_job(client, title: str = "后端开发工程师", description: str = JOB_TEXT) -> dict:
    response = client.post("/api/jobs", json={"title": title, "description": description})
    assert response.status_code == 201, response.text
    return response.json()
