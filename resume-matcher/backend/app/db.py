"""Database engine and session factory."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


# SQLite 默认不校验外键，ON DELETE CASCADE 会静默失效（本地用 SQLite 跑测试时尤其危险：
# 删简历会留下孤立的分析与建议）。打开它，让 SQLite 的行为和部署用的 PostgreSQL 一致。
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # pragma: no cover - 驱动回调
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass
