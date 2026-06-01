"""
Skill Import Router — 主记忆宫殿技能导入 REST API.

将主记忆宫殿中已定义但尚未导入的 5 套军团/自进化 skill
注册到 hermes-dashboard 的技能索引中。

Endpoints
---------
====================================  =====  =====================================
Path                                  Method  Description
====================================  =====  =====================================
/api/skills/registry                   GET    List all importable palace skills
/api/skills/import/{skill_name}       POST   Import a single palace skill
/api/skills/import/batch              POST   Batch import multiple palace skills
/api/skills/import/reset/{skill_name} POST   Reset a skill's import status
====================================  =====  =====================================
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from security.auth import require_api_key
from services.skill_importer import (
    batch_import_skills,
    get_importable_skills,
    get_palace_skills,
    import_skill,
    reset_import,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(
    prefix="/api/skills", tags=["Skill Import"]
)


# ──────────────────────────────────────────────────────────────────────
# GET  /api/skills/registry — list all candidate palace skills
# ──────────────────────────────────────────────────────────────────────


@router.get("/registry")
async def list_registry_skills() -> dict[str, Any]:
    """列出所有可导入的主宫殿 skill（包括已导入和未导入的）。

    Returns
    -------
    dict[str, Any]
        包含 ``total``（总数）、``imported_count``（已导入数）、
        ``importable_count``（待导入数）和 ``skills``（技能列表）的字典。
    """
    try:
        all_skills = get_palace_skills()
        importable = [s for s in all_skills if not s["dashboard_imported"]]
        imported = [s for s in all_skills if s["dashboard_imported"]]

        return {
            "total": len(all_skills),
            "imported_count": len(imported),
            "importable_count": len(importable),
            "skills": all_skills,
        }
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list registry skills: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/import/{skill_name} — import a single skill
# ──────────────────────────────────────────────────────────────────────


@router.post("/import/{skill_name}")
async def import_single_skill(
    skill_name: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """导入一个主宫殿 skill 到 dashboard 技能索引。

    创建引用文件到 dashboard/skills/{category}/{skill_name}/，
    更新 skills_registry.json。

    Parameters
    ----------
    skill_name : str
        要导入的技能名称（如 ``legion-self-evolution-engine``）。

    Returns
    -------
    dict[str, Any]
        导入结果，包含 success、skill_name、dashboard_ref 等。

    Raises
    ------
    404
        如果技能名称不在注册表中。
    409
        如果技能已经导入过。
    422
        如果源 SKILL.md 文件不存在。
    """
    try:
        return import_skill(skill_name)
    except ValueError as exc:
        # 技能不在注册表或已导入
        if "不在注册表中" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import skill: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/import/batch — batch import multiple skills
# ──────────────────────────────────────────────────────────────────────


@router.post("/import/batch")
async def import_batch_skills(
    body: dict[str, Any],
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """批量导入多个主宫殿 skill。

    Request Body
    ------------
    .. code-block:: json

        {
            "skill_names": [
                "legion-self-evolution-engine",
                "7x24-autonomous-push-engine"
            ]
        }

    Returns
    -------
    dict[str, Any]
        批量导入结果，包含每个技能的结果、成功/失败计数。
    """
    skill_names: list[str] = body.get("skill_names", [])
    if not skill_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'skill_names' is required and must be a non-empty list",
        )

    try:
        return batch_import_skills(skill_names)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch import failed: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/import/reset/{skill_name} — reset import status
# ──────────────────────────────────────────────────────────────────────


@router.post("/import/reset/{skill_name}")
async def reset_skill_import(
    skill_name: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """重置一个技能的导入状态（清空 imported_at，删除引用文件）。

    Parameters
    ----------
    skill_name : str
        要重置的技能名称。

    Returns
    -------
    dict[str, Any]
        重置结果。

    Raises
    ------
    404
        如果技能名称不在注册表中。
    """
    try:
        return reset_import(skill_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset import: {exc}",
        )
