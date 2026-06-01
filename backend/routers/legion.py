"""
Legion Router — AI数智军团看板 REST API.

端点
---------
===========================  =====  ======================================
Path                         Method  Description
===========================  =====  ======================================
/api/legion/overview          GET    军团总览
/api/legion/employees         GET    员工列表（支持分页）
/api/legion/employees/{name}  GET    单个员工详情
/api/legion/services          GET    服务状态
/api/legion/soul-distribution GET    灵魂质量分布
/api/legion/recent-activity   GET    最近活动摘要
----------------------------  -----  --------------------------------------
/api/legion/employees         POST   注册新员工
/api/legion/employees/{name}  DELETE 注销员工
/api/legion/employees/{name}/assign    POST   分配任务
/api/legion/employees/{name}/tasks     GET    查看员工任务列表
----------------------------  -----  --------------------------------------
/api/legion/skill-match        POST   技能匹配（全能版）
/api/legion/suggest-team       POST   建议团队组合
===========================  =====  ======================================
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import (
    AssignTaskRequest,
    RegisterEmployeeRequest,
)
from security.auth import require_api_key
from services.legion_dashboard import LegionDashboard
from services.talent_matcher import (
    match_task_to_employee,
    suggest_team,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/legion", tags=["Legion"])

# ── Data storage ───────────────────────────────────────────────────────

_DATA_DIR = Path(
    os.getenv(
        "DASHBOARD_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / "data"),
    )
)
_EMPLOYEES_DATA_DIR = _DATA_DIR / "employees"


def _employee_file_path(name: str) -> Path:
    """返回员工 JSON 文件的完整路径。

    将员工名称规范化：空格 → 下划线，小写化。
    """
    safe_name = name.strip().replace(" ", "_").lower()
    return _EMPLOYEES_DATA_DIR / f"{safe_name}.json"


def _load_employee(name: str) -> dict[str, Any] | None:
    """加载单个员工数据，未找到时返回 None。"""
    path = _employee_file_path(name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load employee %s: %s", name, exc)
        return None


def _save_employee(data: dict[str, Any]) -> None:
    """保存/覆写员工数据到 JSON 文件。"""
    _EMPLOYEES_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _employee_file_path(data["name"])
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _delete_employee_file(name: str) -> bool:
    """删除员工 JSON 文件。成功返回 True，文件不存在返回 False。"""
    path = _employee_file_path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _list_all_employees() -> list[dict[str, Any]]:
    """列出 data/employees/ 下所有注册员工。"""
    if not _EMPLOYEES_DATA_DIR.is_dir():
        return []
    employees: list[dict[str, Any]] = []
    try:
        for entry in sorted(_EMPLOYEES_DATA_DIR.iterdir()):
            if entry.suffix.lower() == ".json":
                try:
                    data = json.loads(entry.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data.get("name"):
                        employees.append(data)
                except (json.JSONDecodeError, OSError):
                    continue
    except OSError:
        pass
    return employees


# ══════════════════════════════════════════════════════════════════════
# Existing GET endpoints (backward-compatible)
# ══════════════════════════════════════════════════════════════════════


@router.get("/overview")
async def get_overview() -> dict[str, Any]:
    """返回 AI 数智军团总览数据。

    聚合员工数、服务数、Profile 数，并计算健康度百分比。
    健康度 = (精锐员工数 + 标准员工数) / 总员工数 × 100。

    Returns
    -------
    dict[str, Any]
        ``legion_stats``（军团统计）、``health_pct``（健康度百分比）、
        以及 ``generated_at``（生成时间戳）。
        ``legion_stats.imported_skills`` 显示已导入的 dashboard skill 数量。
    """
    try:
        return LegionDashboard.get_overview()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get legion overview: {exc}",
        )


@router.get("/employees")
async def get_employees(
    page: Annotated[
        int, Query(ge=1, description="页码（从 1 开始）")
    ] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="每页条目数")
    ] = 20,
) -> dict[str, Any]:
    """返回分页的员工列表。

    按目录扫描顺序排列。每个条目包含姓名、ID、等级、
    部门、类型、灵魂等级和心智模型摘要。

    Parameters
    ----------
    page : int
        页码（默认 1）。
    page_size : int
        每页条目数（默认 20，最大 100）。

    Returns
    -------
    dict[str, Any]
        包含 ``items``、``total``、``page``、``page_size``
        和 ``total_pages`` 的字典。
    """
    try:
        return LegionDashboard.get_employees_list(
            page=page, page_size=page_size
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get employees list: {exc}",
        )


@router.get("/employees/{name}")
async def get_employee_detail(name: str) -> dict[str, Any]:
    """返回单个员工的详细信息。

    包括灵魂注入详情、情感锚点、心智模型和能力列表。

    Parameters
    ----------
    name : str
        员工姓名或 employee_id。

    Returns
    -------
    dict[str, Any]
        员工详情字典。

    Raises
    ------
    404
        如果未找到该员工。
    """
    try:
        detail = LegionDashboard.get_employee_detail(name)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get employee detail: {exc}",
        )

    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{name}' not found",
        )
    return detail


@router.get("/services")
async def get_services() -> list[dict[str, Any]]:
    """返回所有 P0/P1 注册服务的在线状态。

    对每个服务通过 TCP socket 连接 ``127.0.0.1:{port}``
    检测是否在线。P0 核心服务排在前面。

    Returns
    -------
    list[dict[str, Any]]
        服务列表，按优先级排序。
    """
    try:
        services = LegionDashboard.scan_services()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan services: {exc}",
        )
    return [s.to_dict() for s in services]


@router.get("/soul-distribution")
async def get_soul_distribution() -> dict[str, Any]:
    """返回灵魂质量分布统计数据。

    统计精锐/标准/空壳三级员工数量及比例，以及有觉醒记录
    的员工占比。

    Returns
    -------
    dict[str, Any]
        灵魂分布数据，包含原始计数和百分比。
    """
    try:
        return LegionDashboard.get_soul_distribution()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get soul distribution: {exc}",
        )


@router.get("/recent-activity")
async def get_recent_activity(
    limit: Annotated[
        int, Query(ge=1, le=100, description="返回条目数上限")
    ] = 20,
) -> list[dict[str, str]]:
    """从 ``MEMORY.md`` 中提取最近活动摘要。

    解析标题行和列表条目，按时间倒序排列。

    Parameters
    ----------
    limit : int
        返回的最大条目数（默认 20，最大 100）。

    Returns
    -------
    list[dict[str, str]]
        活动条目列表，每条包含 ``timestamp`` 和 ``summary``。
    """
    try:
        return LegionDashboard.get_recent_activity(limit=limit)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent activity: {exc}",
        )


# ══════════════════════════════════════════════════════════════════════
# New: 员工管理端点 (需 API Key 认证)
# ══════════════════════════════════════════════════════════════════════


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def register_employee(
    body: RegisterEmployeeRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """注册新 AI 员工到 dashboard 管理的员工池。

    员工数据存储在 ``data/employees/`` 目录下 JSON 文件，
    不与主记忆宫殿 ``employees/`` 目录冲突。

    Request Body
    ------------
    .. code-block:: json

        {
            \"name\": \"小智\",
            \"role\": \"engineer\",
            \"skill_tags\": [\"python\", \"fastapi\", \"nlp\"],
            \"personality\": \"细致认真，擅长代码审查\"
        }

    Returns
    -------
    dict[str, Any]
        创建的员工数据（含自动生成的 ``employee_id`` 和 ``created_at``）。

    Raises
    ------
    409
        如果同名员工已存在。
    """
    # 检查是否已存在
    existing = _load_employee(body.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Employee '{body.name}' already exists in dashboard registry",
        )

    now = datetime.now(timezone.utc).isoformat()
    employee_data: dict[str, Any] = {
        "employee_id": f"dash-emp-{uuid.uuid4().hex[:8]}",
        "name": body.name,
        "role": body.role,
        "skill_tags": body.skill_tags,
        "personality": body.personality or "",
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "tasks": [],
    }

    try:
        _save_employee(employee_data)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save employee data: {exc}",
        )

    logger.info(
        "Registered new dashboard employee: %s (role=%s, skills=%s)",
        body.name,
        body.role,
        body.skill_tags,
    )
    return employee_data


@router.delete("/employees/{name}")
async def unregister_employee(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, str]:
    """注销（删除）已注册的 AI 员工。

    Parameters
    ----------
    name : str
        员工名称（注册时的原始名称，大小写不敏感）。

    Returns
    -------
    dict[str, str]
        确认消息。

    Raises
    ------
    404
        如果该员工未在 dashboard 中注册。
    """
    if not _delete_employee_file(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{name}' not found in dashboard registry",
        )

    logger.info("Unregistered dashboard employee: %s", name)
    return {
        "message": f"Employee '{name}' has been unregistered",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/employees/{name}/assign")
async def assign_task(
    name: str,
    body: AssignTaskRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """为指定员工分配任务。

    任务会追加到员工的 ``tasks`` 列表中，每个任务自动获得
    唯一 task_id。

    Request Body
    ------------
    .. code-block:: json

        {
            \"task\": \"开发用户登录模块\",
            \"priority\": 4,
            \"deadline\": \"2026-06-15T18:00:00\"
        }

    Parameters
    ----------
    name : str
        员工名称。

    Returns
    -------
    dict[str, Any]
        分配后的员工数据（含新任务）。

    Raises
    ------
    404
        如果员工不存在。
    """
    employee = _load_employee(name)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{name}' not found in dashboard registry",
        )

    now = datetime.now(timezone.utc).isoformat()
    task_entry: dict[str, Any] = {
        "task_id": f"task-{uuid.uuid4().hex[:12]}",
        "task": body.task,
        "priority": body.priority,
        "deadline": body.deadline,
        "status": "pending",
        "assigned_at": now,
    }

    tasks: list[dict[str, Any]] = employee.get("tasks", [])
    tasks.append(task_entry)
    employee["tasks"] = tasks
    employee["updated_at"] = now

    try:
        _save_employee(employee)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save task: {exc}",
        )

    logger.info(
        "Assigned task to %s: %s (priority=%d)",
        name,
        body.task[:60],
        body.priority,
    )
    return employee


@router.get("/employees/{name}/tasks")
async def get_employee_tasks(
    name: str,
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description="按任务状态过滤: pending / in_progress / completed / cancelled",
        ),
    ] = None,
) -> dict[str, Any]:
    """查看指定员工的任务列表。

    Parameters
    ----------
    name : str
        员工名称。
    status_filter : str, optional
        按状态过滤（pending / in_progress / completed / cancelled）。

    Returns
    -------
    dict[str, Any]
        包含 ``tasks``、``total``、``employee_name`` 的字典。

    Raises
    ------
    404
        如果员工不存在。
    """
    employee = _load_employee(name)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee '{name}' not found in dashboard registry",
        )

    tasks: list[dict[str, Any]] = employee.get("tasks", [])
    if status_filter:
        tasks = [
            t for t in tasks if t.get("status") == status_filter
        ]

    # 按优先级降序排列（高优先级在前），然后按分配时间倒序
    tasks.sort(
        key=lambda t: (
            -t.get("priority", 3),
            t.get("assigned_at", ""),
        )
    )

    return {
        "employee_name": name,
        "employee_id": employee.get("employee_id", ""),
        "tasks": tasks,
        "total": len(tasks),
    }


# ══════════════════════════════════════════════════════════════════════
# New: 技能匹配全能端点
# ══════════════════════════════════════════════════════════════════════


@router.post("/skill-match")
async def skill_match(
    body: dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """根据任务描述匹配最合适的员工。

    使用 talent_matcher 的关键词 + Jaccard 相似度匹配。
    匹配对象为 dashboard 注册员工（data/employees/），
    非主宫殿 employees/。

    Request Body
    ------------
    .. code-block:: json

        {
            \"task_description\": \"需要开发一个 FastAPI 后端 API\",
            \"top_k\": 5,
            \"min_score\": 0.0
        }

    Returns
    -------
    dict[str, Any]
        包含 ``matches``、``total``、``task_description`` 的字典。
    """
    task_description = body.get("task_description", "")
    if not task_description or not task_description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'task_description' is required",
        )

    top_k = body.get("top_k", 10)
    min_score = body.get("min_score", 0.0)

    try:
        matches = match_task_to_employee(
            task_description=task_description,
            employees=None,
            min_score=min_score,
            top_k=top_k,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Skill matching failed: {exc}",
        )

    return {
        "task_description": task_description,
        "matches": matches,
        "total": len(matches),
    }


@router.post("/suggest-team")
async def suggest_team_endpoint(
    body: dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """根据项目描述建议最优团队组合。

    使用贪心算法，在保证技能覆盖度的同时选择核心成员。

    Request Body
    ------------
    .. code-block:: json

        {
            \"project_description\": \"开发一个多模态 AI 助手，\"
                                   \"需要 NLP、语音合成和前端开发能力\",
            \"min_members\": 2,
            \"max_members\": 5
        }

    Returns
    -------
    dict[str, Any]
        包含 ``team``、``coverage``、``rationale`` 的字典。
    """
    project_description = body.get("project_description", "")
    if not project_description or not project_description.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'project_description' is required",
        )

    min_members = body.get("min_members", 2)
    max_members = body.get("max_members", 5)

    try:
        result = suggest_team(
            project_description=project_description,
            min_members=min_members,
            max_members=max_members,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Team suggestion failed: {exc}",
        )

    return result
