from app.auth.passwords import (
    hash_password,
    verify_password,
    validate_complexity,
    is_in_history,
    needs_rehash,
    PasswordPolicyError,
    MIN_PASSWORD_LENGTH,
    PASSWORD_HISTORY_SIZE,
)
from app.auth.tokens import issue_access_token, decode_token
from app.auth.deps import (
    Principal,
    get_current_user,
    get_current_principal,
    get_current_tenant_id_from_user,
    get_optional_principal,
    require_permission,
)
from app.auth.permissions import (
    UserPermissions,
    compute_effective_permissions,
)

__all__ = [
    "hash_password",
    "verify_password",
    "validate_complexity",
    "is_in_history",
    "needs_rehash",
    "PasswordPolicyError",
    "MIN_PASSWORD_LENGTH",
    "PASSWORD_HISTORY_SIZE",
    "issue_access_token",
    "decode_token",
    "Principal",
    "get_current_user",
    "get_current_principal",
    "get_current_tenant_id_from_user",
    "get_optional_principal",
    "require_permission",
    "UserPermissions",
    "compute_effective_permissions",
]
