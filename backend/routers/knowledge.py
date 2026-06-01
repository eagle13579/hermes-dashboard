"""
Knowledge Router — REST API for cross-profile knowledge search.

Endpoints
=========
============================  =====  ====================================
Path                            Method  Description
============================  =====  ====================================
/api/knowledge/search           GET    跨源搜索
/api/knowledge/search/{profile} GET    限定 Profile 搜索
/api/knowledge/stats            GET    索引统计
/api/knowledge/rebuild          POST   重建索引
============================  =====  ====================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from security.auth import require_api_key
from services.knowledge_search import get_service

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/knowledge", tags=["Knowledge Search"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/knowledge/search — 跨源搜索
# ──────────────────────────────────────────────────────────────────────


@router.get("/search")
async def search_knowledge(
    q: Annotated[str, Query(description="搜索关键词（支持中文）")],
    type: Annotated[
        Optional[str],
        Query(
            description=(
                "过滤类型: skill / code / mental_model / doc / all。"
                "不传则搜索全部。"
            ),
        ),
    ] = None,
    limit: Annotated[
        int, Query(description="每页结果数（默认 20，最大 100）", ge=1, le=100)
    ] = 20,
    offset: Annotated[
        int, Query(description="分页偏移量（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """跨源知识搜索 — 同时搜索技能、代码资产、心智模型和产品文档。

    搜索路径：
      - 技能：$HERMES_HOME/skills/
      - 代码资产：$HERMES_HOME/L1图书馆/代码资产库/
      - 心智模型：$HERMES_HOME/L3工作室/五池/模型池/
      - 产品文档：$HERMES_HOME/L5孵化室/产品开发/

    Parameters
    ----------
    q : str
        搜索关键词（必需）。
    type : str, optional
        资源类型过滤。可选值：skill, code, mental_model, doc, all。
    limit : int
        每页返回数量（1–100，默认 20）。
    offset : int
        分页偏移（默认 0）。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int}``
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="查询参数 'q' 不能为空",
        )

    try:
        service = get_service()
        results, total = service.search(
            query=q.strip(),
            type_filter=type,
            limit=limit,
            offset=offset,
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

    return {
        "results": [r.to_dict() for r in results],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ──────────────────────────────────────────────────────────────────────
# GET  /api/knowledge/search/{profile} — 限定 Profile 搜索
# ──────────────────────────────────────────────────────────────────────


@router.get("/search/{profile}")
async def search_knowledge_by_profile(
    profile: str,
    q: Annotated[str, Query(description="搜索关键词（支持中文）")],
    limit: Annotated[
        int, Query(description="每页结果数（默认 20，最大 100）", ge=1, le=100)
    ] = 20,
    offset: Annotated[
        int, Query(description="分页偏移量（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """在指定 Profile 目录下搜索知识文档。

    Parameters
    ----------
    profile : str
        Profile 名称（对应 $HERMES_HOME/profiles/<profile>/ 目录）。
    q : str
        搜索关键词（必需）。
    limit : int
        每页返回数量（1–100，默认 20）。
    offset : int
        分页偏移（默认 0）。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int, "profile": str}``

    Raises
    ------
    404
        如果指定的 Profile 不存在。
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="查询参数 'q' 不能为空",
        )

    service = get_service()
    try:
        results = service.search_by_profile(query=q.strip(), profile_name=profile)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件系统错误: {exc}",
        )

    if not results and not service._resolve_path(f"profiles/{profile}").is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{profile}' 不存在",
        )

    total = len(results)
    paged = results[offset : offset + limit]

    return {
        "results": [r.to_dict() for r in paged],
        "total": total,
        "offset": offset,
        "limit": limit,
        "profile": profile,
    }


# ──────────────────────────────────────────────────────────────────────
# GET  /api/knowledge/stats — 索引统计
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def knowledge_stats() -> dict:
    """获取知识索引统计信息。

    Returns
    -------
    dict
        ``{"total_documents": int, "categories": {...}, "profiles_count": int, ...}``
    """
    try:
        service = get_service()
        stats = service.get_search_stats()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"索引统计失败: {exc}",
        )
    return stats


# ──────────────────────────────────────────────────────────────────────
# POST  /api/knowledge/rebuild — 重建索引
# ──────────────────────────────────────────────────────────────────────


@router.post("/rebuild")
async def rebuild_knowledge_index(
    _auth: None = Depends(require_api_key),
) -> dict:
    """重建搜索索引缓存。

    扫描所有知识库目录（skills、L1图书馆、L3工作室、L5孵化室、profiles），
    重建 JSON 缓存文件以加速后续搜索。

    Returns
    -------
    dict
        ``{"status": "ok", "stats": {...}}``
    """
    try:
        service = get_service()
        stats = service.rebuild_index()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重建索引失败: {exc}",
        )
    return {
        "status": "ok",
        "stats": stats,
    }
