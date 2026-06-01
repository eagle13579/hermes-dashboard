"""Auth Router — 用户注册/登录/管理API"""
from __future__ import annotations
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.user_service import (
    init_db, register_user, authenticate_user, get_user_by_id,
    list_users, update_role, deactivate_user, update_last_login
)
from security.rbac import create_jwt, get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str = ""
    role: str = "user"

class RoleUpdate(BaseModel):
    role: str

@router.on_event("startup")
async def startup():
    init_db()
    logger.info("Auth database initialized")

@router.post("/login")
async def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    update_last_login(user["id"])
    token = create_jwt({
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
    }, timedelta(days=1))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {k: v for k, v in user.items() if k != "password_hash"},
    }

@router.post("/register")
async def register(req: RegisterRequest, current_user: dict = Depends(require_role("admin"))):
    user = register_user(req.username, req.password, req.email, req.role)
    if not user:
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"message": "User registered", "user": {k: v for k, v in user.items() if k != "password_hash"}}

@router.get("/users")
async def get_users(current_user: dict = Depends(require_role("admin"))):
    return {"users": list_users()}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user": current_user}

@router.put("/users/{user_id}/role")
async def change_role(user_id: int, req: RoleUpdate, current_user: dict = Depends(require_role("admin"))):
    ok = update_role(user_id, req.role)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} role updated to {req.role}"}

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current_user: dict = Depends(require_role("admin"))):
    ok = deactivate_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"User {user_id} deactivated"}
