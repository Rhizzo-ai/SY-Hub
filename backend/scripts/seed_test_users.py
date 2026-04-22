"""Seed test users for testing subagent. Idempotent.

Creates a set of purpose-built test users in the default tenant, each with
a single predictable role assignment so RBAC tests can exercise every role.

Usage:
    python /app/backend/scripts/seed_test_users.py

All test accounts use the password from $TEST_USER_PASSWORD (backend/.env).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import select, insert  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.auth.passwords import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.entity import Entity  # noqa: E402
from app.models.rbac import Role, UserRole, user_role_entities  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


TEST_USERS = [
    # (email, first, last, role_code, entity_scope, role_limited_entity_name)
    ("test-admin@example.test", "Test", "Admin", "super_admin", "All", None),
    ("test-director@example.test", "Test", "Director", "director", "All", None),
    ("test-pm@example.test", "Test", "PM", "project_manager", "Specific", "SY Homes (Shrewsbury) Ltd"),
    ("test-finance@example.test", "Test", "Finance", "finance", "All", None),
    ("test-site@example.test", "Test", "Site", "site_manager", "All", None),
    ("test-readonly@example.test", "Test", "Readonly", "read_only", "All", None),
    ("test-archived@example.test", "Test", "Archived", "read_only", "All", None),
]


def main() -> None:
    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.name == os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")))
        if tenant is None:
            raise SystemExit("Default tenant not found — run backend seed first.")

        password = os.environ.get("TEST_USER_PASSWORD")
        if not password:
            raise SystemExit("TEST_USER_PASSWORD missing in .env")
        pw_hash = hash_password(password)

        roles = {r.code: r for r in db.scalars(select(Role)).all()}
        bootstrap_admin = db.scalars(select(User).where(User.email == (os.environ.get("BOOTSTRAP_ADMIN_EMAIL") or "").lower())).first()
        assigner_id = bootstrap_admin.id if bootstrap_admin else None

        for email, first, last, role_code, scope, ent_name in TEST_USERS:
            u = db.scalars(select(User).where(User.email == email, User.tenant_id == tenant.id)).first()
            if u is None:
                u = User(
                    tenant_id=tenant.id,
                    email=email,
                    email_verified=True,
                    password_hash=pw_hash,
                    password_algorithm="argon2id",
                    password_changed_at=datetime.now(timezone.utc),
                    password_history=[],
                    first_name=first, last_name=last,
                    display_name=f"{first} {last}",
                    user_type="Internal",
                    status="Active",
                )
                db.add(u)
                db.flush()
                print(f"created {email} ({u.id})")
            else:
                # Always rewrite password so tests don't drift
                u.password_hash = pw_hash
                u.password_history = []
                u.status = "Active"
                u.failed_login_attempts = 0
                u.locked_until = None
                u.mfa_enabled = False
                u.mfa_secret_encrypted = None
                u.mfa_backup_codes_encrypted = None
                print(f"reset {email}")

            # Wipe existing role assignments to keep seeds deterministic
            for ur in db.scalars(select(UserRole).where(UserRole.user_id == u.id)).all():
                db.delete(ur)
            db.flush()

            ur = UserRole(
                user_id=u.id,
                role_id=roles[role_code].id,
                entity_scope=scope,
                project_scope="All",
                view_overrides=[],
                assigned_by_user_id=assigner_id or u.id,
                status="Active",
            )
            db.add(ur)
            db.flush()

            if scope == "Specific" and ent_name:
                ent = db.scalars(select(Entity).where(Entity.name == ent_name, Entity.tenant_id == tenant.id)).first()
                if ent is not None:
                    db.execute(insert(user_role_entities).values(user_role_id=ur.id, entity_id=ent.id))

        # Archive the "archived" user
        archived = db.scalars(select(User).where(User.email == "test-archived@example.test", User.tenant_id == tenant.id)).first()
        if archived is not None:
            archived.status = "Archived"
            archived.archived_at = datetime.now(timezone.utc)

        db.commit()
        print("Test users seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
