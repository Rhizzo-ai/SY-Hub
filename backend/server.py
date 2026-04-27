"""SY Homes Operations Platform — FastAPI entrypoint."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import APIRouter, FastAPI  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

from alembic import command as alembic_command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402

from app.jobs.audit_retention import (  # noqa: E402
    start_audit_retention_scheduler, stop_audit_retention_scheduler,
)
from app.jobs.insurance_alerts import start_scheduler, stop_scheduler  # noqa: E402
from app.jobs.notification_expiry import (  # noqa: E402
    start_notification_expiry_scheduler, stop_notification_expiry_scheduler,
)
from app.jobs.planning_expiry import (  # noqa: E402
    start_planning_expiry_scheduler, stop_planning_expiry_scheduler,
)
from app.jobs.role_expiry import start_role_expiry_scheduler, stop_role_expiry_scheduler  # noqa: E402
from app.routers.audit import router as audit_router  # noqa: E402
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.cost_codes import router as cost_codes_router  # noqa: E402
from app.routers.entities import router as entities_router  # noqa: E402
from app.routers.login_history import router as login_history_router  # noqa: E402
from app.routers.meta import router as meta_router  # noqa: E402
from app.routers.notifications import router as notifications_router  # noqa: E402
from app.routers.projects import router as projects_router  # noqa: E402
from app.routers.roles import roles_router, perms_router  # noqa: E402
from app.routers.sessions import router as sessions_router  # noqa: E402
from app.routers.system_config import router as system_config_router  # noqa: E402
from app.routers.users import router as users_router  # noqa: E402
from app.seed import seed  # noqa: E402
from app.seed_rbac import seed_rbac  # noqa: E402
from app.seed_system_config import (  # noqa: E402
    seed_system_config, seed_system_config_role_grants,
)
from app import models  # noqa: F401, E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("syhomes")


def _run_migrations() -> None:
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
        log.exception("Tenant/entity seed failed")
    try:
        seed_rbac()
    except Exception:
        log.exception("RBAC seed failed")
    try:
        seed_system_config_role_grants()
    except Exception:
        log.exception("system_config role-grant seed failed")
    try:
        seed_system_config()
    except Exception:
        log.exception("system_config seed failed")
    start_scheduler()
    start_role_expiry_scheduler()
    start_planning_expiry_scheduler()
    start_notification_expiry_scheduler()
    start_audit_retention_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        stop_role_expiry_scheduler()
        stop_planning_expiry_scheduler()
        stop_notification_expiry_scheduler()
        stop_audit_retention_scheduler()


app = FastAPI(
    title="SY Homes Operations Platform",
    version="0.2.0-phase1-prompt1.2",
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health():
    return {"status": "ok", "module": "users+rbac", "phase": "1.2"}


@api_router.get("/")
def root():
    return {"service": "SY Homes Operations Platform", "phase": "1.2-users"}


api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(sessions_router)
api_router.include_router(login_history_router)
api_router.include_router(roles_router)
api_router.include_router(perms_router)
api_router.include_router(entities_router)
api_router.include_router(projects_router)
api_router.include_router(cost_codes_router)
api_router.include_router(meta_router)
api_router.include_router(audit_router)

# Prompt 1.7 — system_config + notifications mount under /api/v1.
# Pre-existing /api/* routes remain unchanged. /api/v1 is the new
# baseline going forward; older modules will migrate on a per-prompt
# basis (Polish Pass).
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(system_config_router)
v1_router.include_router(notifications_router)
api_router.include_router(v1_router)

app.include_router(api_router)


def _resolve_cors_origins() -> list[str]:
    """Guard against the classic CORS-with-credentials wildcard footgun.

    Allowing credentials + any origin is unsafe: any site the user visits
    could issue authenticated cross-origin requests. We fail startup fast
    with an informative error rather than silently serving a permissive policy.
    """
    raw = os.environ.get("CORS_ORIGINS", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts or "*" in parts:
        raise RuntimeError(
            "CORS misconfiguration: allow_credentials=True is incompatible "
            "with a wildcard CORS_ORIGINS. Set CORS_ORIGINS to an explicit "
            "comma-separated list of origins, e.g. "
            "'https://app.syhomes.co.uk,https://preview.emergentagent.com'. "
            f"Currently CORS_ORIGINS={raw!r}."
        )
    return parts


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_resolve_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)
