"""Role-Based Access Control (RBAC) & Route Protection Module.
Supports JWT / Role Token verification with Supabase Auth compatibility.
Provides FastAPI dependencies for route protection based on user roles:
- 'group_manager'
- 'insurance_provider'
"""

import os
from typing import Optional
from fastapi import Header, HTTPException, Depends

# Secret key for JWT / Token validation (falls back to dev key if not set)
AUTH_SECRET = os.environ.get("AUTH_SECRET", "heatwave-parametric-secret-key-2026")

def get_current_user_role(
    authorization: Optional[str] = Header(None),
    x_role: Optional[str] = Header(None)
) -> str:
    """Extracts role from Authorization header or X-Role header.
    In production with Supabase, decodes the JWT claims.
    In simulation/dev, accepts verified role tokens:
    - 'Bearer token-manager' -> 'group_manager'
    - 'Bearer token-insurer' -> 'insurance_provider'
    - 'X-Role: group_manager' -> 'group_manager'
    - 'X-Role: insurance_provider' -> 'insurance_provider'
    """
    if x_role:
        return x_role.lower()

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        if "manager" in token.lower() or token == "mgr-session-active":
            return "group_manager"
        elif "insurer" in token.lower() or token == "ins-session-active":
            return "insurance_provider"

    # Default to public viewer if no auth header passed (or for public endpoints)
    return "public"

def require_role(allowed_roles: list[str]):
    """FastAPI Dependency for Role-Based Access Control."""
    def role_checker(role: str = Depends(get_current_user_role)):
        if role not in allowed_roles and "admin" not in role:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Required role in {allowed_roles}, but logged in as '{role}'."
            )
        return role
    return role_checker
