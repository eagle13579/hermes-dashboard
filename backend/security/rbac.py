"""RBAC — 角色权限控制 + JWT用户提取"""
from __future__ import annotations
import json, os, logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import urllib.request

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# JWT settings (stdlib only - no PyJWT dependency)
JWT_SECRET = os.environ.get("HERMES_API_KEY", "hermes-dashboard-dev-secret-key")

# Permission matrix
PERMISSIONS = {
    "admin": {"*": {"*": True}},  # admin can do everything
    "user": {
        "read": {"*": True},
        "write": {"own": True},
        "admin": {"*": False},
    },
    "viewer": {
        "read": {"*": True},
        "write": {"*": False},
        "admin": {"*": False},
    },
}

def _b64encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64decode(s: str) -> bytes:
    import base64
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)

def _hmac_sha256(key: str, msg: str) -> str:
    import hmac
    return hmac.new(key.encode(), msg.encode(), "sha256").hexdigest()

def create_jwt(payload: dict, expires_delta: timedelta = timedelta(hours=24)) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_with_exp = {**payload, "exp": (datetime.utcnow() + expires_delta).timestamp()}
    payload_b64 = _b64encode(json.dumps(payload_with_exp).encode())
    signature = _hmac_sha256(JWT_SECRET, f"{header}.{payload_b64}")
    return f"{header}.{payload_b64}.{signature}"

def verify_jwt(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload_b64, signature = parts
        expected_sig = _hmac_sha256(JWT_SECRET, f"{header}.{payload_b64}")
        if signature != expected_sig:
            return None
        payload = json.loads(_b64decode(payload_b64))
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            return None
        return payload
    except Exception:
        return None

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[dict]:
    """Extract current user from JWT token."""
    if credentials is None:
        return None
    payload = verify_jwt(credentials.credentials)
    if payload is None:
        return None
    return payload

async def require_role(role: str):
    """FastAPI dependency: require minimum role level.
    
    Hierarchy: admin > user > viewer
    """
    role_level = {"admin": 3, "user": 2, "viewer": 1}
    min_level = role_level.get(role, 1)
    
    async def _checker(current_user: Optional[dict] = Depends(get_current_user)) -> dict:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user_role = current_user.get("role", "viewer")
        user_level = role_level.get(user_role, 1)
        if user_level < min_level:
            raise HTTPException(status_code=403, detail=f"Requires role: {role}")
        return current_user
    return _checker

async def require_permission(resource: str, action: str):
    """FastAPI dependency: check specific permission."""
    async def _checker(current_user: Optional[dict] = Depends(get_current_user)) -> dict:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        role = current_user.get("role", "viewer")
        role_perms = PERMISSIONS.get(role, {})
        # Check if resource has wildcard
        resource_perms = role_perms.get(resource, role_perms.get("*", {}))
        if resource_perms.get(action, resource_perms.get("*", False)):
            return current_user
        # Check wildcard resource
        wild_perms = role_perms.get("*", {})
        if wild_perms.get(action, wild_perms.get("*", False)):
            return current_user
        raise HTTPException(status_code=403, detail=f"Permission denied: {resource}:{action}")
    return _checker
