"""FastAPI entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import analyses, auth, jobs, resumes, suggestions, supplements
from .services.analysis import fail_stale_tasks

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        stale = fail_stale_tasks()
        if stale:
            logger.info("marked %s interrupted analysis task(s) as failed", stale)
    except Exception as exc:  # noqa: BLE001 - never block startup on this check
        logger.warning("could not check for interrupted analysis tasks: %s", exc)
    yield


app = FastAPI(title="简历与岗位匹配助手 API", version="0.1.0", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, resumes, jobs, analyses, suggestions, supplements):
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict:
    current = get_settings()
    return {"ok": True, "llm_configured": current.llm_configured, "model": current.llm_model}
