"""
Joint Operations Router — REST API for Joint Operations (联合作战模式).

Endpoints
=========
============================  =====  ===================================
Path                            Method  Description
============================  =====  ===================================
/api/joint-ops                   GET    联合作战列表
/api/joint-ops                   POST   创建联合作战
/api/joint-ops/templates         GET    模板列表
/api/joint-ops/templates         POST   保存模板
/api/joint-ops/{op_id}           GET    联合作战详情
/api/joint-ops/{op_id}/execute   POST   执行联合作战
/api/joint-ops/{op_id}/cancel    POST   取消联合作战
============================  =====  ===================================

NOTE
----
Static routes (``/templates``) are declared **before** the parameterised
route ``/{op_id}`` so that FastAPI does not interpret ``templates`` as
an ``op_id`` value, which would cause a 404.
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import CreateOperationRequest, SaveTemplateRequest
from security.auth import require_api_key
from services.joint_ops import get_manager

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/joint-ops", tags=["Joint Operations"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/joint-ops — 联合作战列表
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_operations(
    status_filter: Annotated[
        Optional[str],
        Query(
            alias="status",
            description=(
                "按状态过滤: planning / running / completed / failed / cancelled。"
                "不传则返回全部。"
            ),
        ),
    ] = None,
) -> dict:
    """获取联合作战列表，可按状态过滤。

    Parameters
    ----------
    status_filter : str, optional
        过滤状态。可选值：planning, running, completed, failed, cancelled。

    Returns
    -------
    dict
        ``{\"operations\": [...], \"total\": int}``
    """
    try:
        manager = get_manager()
        ops = manager.list_operations(status=status_filter)
        return {
            "operations": [op.to_dict() for op in ops],
            "total": len(ops),
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/joint-ops — 创建联合作战
# ──────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_operation(
    body: CreateOperationRequest,
    _auth: None = Depends(require_api_key),
) -> dict:
    """创建一个新的联合作战。

    Request Body
    ------------
    .. code-block:: json

        {
            "name": "代码评审",
            "description": "描述文本",
            "stages": [
                {
                    "profile_name": "chainke-dev",
                    "goal": "编写用户注册代码"
                },
                {
                    "profile_name": "gaia-city",
                    "goal": "评审上述代码架构"
                }
            ]
        }

    Returns
    -------
    dict
        创建的 JointOperation 对象。
    """
    try:
        manager = get_manager()
        op = manager.create_operation(
            name=body.name,
            description=body.description,
            stages=[s.model_dump() for s in body.stages],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    return op.to_dict()


# ──────────────────────────────────────────────────────────────────────
# GET  /api/joint-ops/templates — 模板列表
# ──────────────────────────────────────────────────────────────────────
# NOTE: Declared BEFORE /{op_id} so FastAPI matches the literal
#       "templates" path before treating it as a parameter.


@router.get("/templates")
async def list_templates() -> dict:
    """获取所有联合作战模板（包括预定义模板和用户保存的模板）。"""
    try:
        manager = get_manager()
        templates = manager.get_templates()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    return {
        "templates": [t.to_dict() for t in templates],
        "total": len(templates),
    }


# ──────────────────────────────────────────────────────────────────────
# POST  /api/joint-ops/templates — 保存模板
# ──────────────────────────────────────────────────────────────────────


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def save_template(
    body: SaveTemplateRequest,
    _auth: None = Depends(require_api_key),
) -> dict:
    """保存一个新的联合作战模板。

    Request Body
    ------------
    .. code-block:: json

        {
            "name": "我的模板",
            "description": "模板描述",
            "stages": [
                {
                    "profile_name": "chainke-dev",
                    "goal": "任务描述"
                }
            ]
        }

    Returns
    -------
    dict
        创建的 JointTemplate 对象。
    """
    try:
        manager = get_manager()
        tmpl = manager.save_template(
            name=body.name,
            description=body.description,
            stages=[s.model_dump() for s in body.stages],
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    return tmpl.to_dict()


# ──────────────────────────────────────────────────────────────────────
# GET  /api/joint-ops/{op_id} — 联合作战详情
# ──────────────────────────────────────────────────────────────────────
# NOTE: Parameterised route — must come after static routes.


@router.get("/{op_id}")
async def get_operation(op_id: str) -> dict:
    """获取指定联合作战的详细信息。"""
    try:
        manager = get_manager()
        op = manager.get_operation(op_id)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    if op is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"联合作战 '{op_id}' 不存在",
        )

    return op.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/joint-ops/{op_id}/execute — 执行联合作战
# ──────────────────────────────────────────────────────────────────────


@router.post("/{op_id}/execute")
async def execute_operation(
    op_id: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """执行整个联合作战（按 Stage 顺序依次执行）。

    每个 Stage 通过 ``hermes -p <profile> chat -q \"<goal>\" -Q`` 调用，
    上一个 Stage 的输出自动作为下一个的上下文输入。
    """
    try:
        manager = get_manager()
        op = manager.execute_operation(op_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    return op.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/joint-ops/{op_id}/cancel — 取消联合作战
# ──────────────────────────────────────────────────────────────────────


@router.post("/{op_id}/cancel")
async def cancel_operation(
    op_id: str,
    _auth: None = Depends(require_api_key),
) -> dict:
    """取消指定联合作战（仅允许取消 planning / running 状态的作战）。"""
    try:
        manager = get_manager()
        op = manager.cancel_operation(op_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    return op.to_dict()
