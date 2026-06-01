"""
Health Router — 系统健康状态 REST API.

提供健康历史趋势和当前服务状态两个端点，供前端健康驾驶舱使用。

端点
=====
===========================  =====  ======================================
Path                         Method  Description
===========================  =====  ======================================
/api/health/history          GET    健康采样历史（支持 ?hours=24/168/720）
/api/health/current          GET    当前各服务健康状态
/api/health/ping             GET    轻量存活探测（兼容老版 /health）
===========================  =====  ======================================

查询参数
---------
``hours`` (int, optional) — 历史采样范围，默认 24。
    支持的值: 1, 6, 12, 24, 48, 168 (7天), 720 (30天)。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from services.health_service import HealthService

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("/history")
async def get_health_history(
    hours: Annotated[
        int,
        Query(
            ge=1,
            le=720,
            description="时间范围（小时）: 1/6/12/24/48/168/720",
        ),
    ] = 24,
) -> dict:
    """返回过去 N 小时的健康采样数据。

    优先从 SQLite 读取；如果 SQLite 不可用，返回最近 30 个模拟采样点。

    Parameters
    ----------
    hours : int
        时间范围（小时）。支持 1, 6, 12, 24, 48, 168, 720。
        默认 24（过去一天）。

    Returns
    -------
    dict
        .. code-block:: json

            {
                "samples": [
                    {
                        "timestamp": "2026-06-01T12:00:00Z",
                        "status": "up",
                        "response_time_ms": 42,
                        "services_online": 5,
                        "services_total": 8
                    }
                ],
                "range_hours": 24,
                "total": 48,
                "source": "mock"
            }
    """
    try:
        return HealthService.get_history(hours=hours)
    except Exception as exc:
        logger.error("Failed to get health history: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get health history: {exc}",
        )


@router.get("/current")
async def get_current_health() -> dict:
    """返回当前系统各服务的健康状态。

    探测所有注册服务的端口连通性，聚合整体状态。

    Returns
    -------
    dict
        .. code-block:: json

            {
                "overall_status": "healthy",
                "uptime_pct": 87.5,
                "avg_response_time_ms": 48,
                "services": [
                    {
                        "name": "Hermes API",
                        "port": 8091,
                        "category": "P0核心",
                        "status": "up",
                        "response_time_ms": 23
                    }
                ],
                "total_services": 8,
                "online_services": 7,
                "generated_at": "2026-06-01T12:00:00Z"
            }
    """
    try:
        return HealthService.get_current_status()
    except Exception as exc:
        logger.error("Failed to get current health: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current health: {exc}",
        )


@router.get("/ping")
async def health_ping() -> dict:
    """轻量存活探测端点。

    Returns
    -------
    dict
        ``{"status": "ok", "service": "hermes-dashboard"}``
    """
    return {"status": "ok", "service": "hermes-dashboard"}
