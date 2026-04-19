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

from app.db import Base, engine, ensure_updated_at_trigger, UPDATED_AT_FN_SQL  # noqa: E402
from app.jobs.insurance_alerts import start_scheduler, stop_scheduler  # noqa: E402
from app.routers.entities import router as entities_router  # noqa: E402
from app.routers.meta import router as meta_router  # noqa: E402
from app.seed import seed  # noqa: E402

# Import models so they register with metadata before create_all().
from app import models  # noqa: F401, E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("syhomes")


def _init_schema() -> None:
    """Create tables + updated_at trigger function + per-table triggers."""
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
        conn.exec_driver_sql(UPDATED_AT_FN_SQL)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table_name in Base.metadata.tables.keys():
            ensure_updated_at_trigger(conn, table_name)
    log.info("Schema ready; updated_at triggers installed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_schema()
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
