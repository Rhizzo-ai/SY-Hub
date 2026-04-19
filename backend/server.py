"""SY Homes Operations Platform — FastAPI entrypoint.

Phase 1 stack: FastAPI + SQLAlchemy 2 + PostgreSQL.
Every API route is prefixed with /api (Kubernetes ingress convention).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from alembic import command as alembic_command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402

from app.db import engine  # noqa: E402
from app.jobs.insurance_alerts import start_scheduler, stop_scheduler  # noqa: E402
from app.routers.entities import router as entities_router  # noqa: E402
from app.routers.meta import router as meta_router  # noqa: E402
from app.seed import seed  # noqa: E402

# Import models so they register with metadata (used by alembic env.py).
from app import models  # noqa: F401, E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("syhomes")


def _run_migrations() -> None:
    """Apply any pending Alembic migrations. Single source of truth for schema."""
    cfg = AlembicConfig(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    alembic_command.upgrade(cfg, "head")
    log.info("Alembic migrations up to date.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _run_migrations()
    try:
        seed()
    except Exception:
        log.exception("Seed failed")
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="SY Homes Operations Platform",
    version="0.1.0-phase1-prompt1.1",
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health():
    return {"status": "ok", "module": "entities", "phase": "1.1"}


@api_router.get("/")
def root():
    return {"service": "SY Homes Operations Platform", "phase": "1.1-entities"}


api_router.include_router(entities_router)
api_router.include_router(meta_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
