"""
Health Service — 系统健康状态采样与趋势分析.

提供健康历史数据采样、当前服务状态聚合，以及可选的 SQLite 持久化。

健康采样数据格式
------------------
.. code-block:: json

    {
        "timestamp": "2026-06-01T12:00:00Z",
        "status": "up",
        "response_time_ms": 42,
        "services_online": 5,
        "services_total": 8
    }

当前服务状态格式
------------------
.. code-block:: json

    {
        "overall_status": "degraded",
        "uptime_pct": 87.5,
        "avg_response_time_ms": 48,
        "services": [
            {
                "name": "Hermes API",
                "status": "up",
                "response_time_ms": 23,
                "category": "P0核心"
            },
            ...
        ],
        "generated_at": "2026-06-01T12:00:00Z"
    }
"""

from __future__ import annotations

import logging
import math
import random
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "health.db"
"""SQLite 数据库路径 (backend/data/health.db)。"""

_SQLITE_AVAILABLE: bool | None = None
"""惰性检测 SQLite 是否可用（只在首次调用时检测）。"""

# ── Service registry for /api/health/current ──────────────────────────

_DEFAULT_SERVICES: list[dict[str, Any]] = [
    {"name": "Hermes API", "port": 8091, "category": "P0核心"},
    {"name": "Memory Palace", "port": 8092, "category": "P0核心"},
    {"name": "Gaia Sync Bridge", "port": 8093, "category": "P1扩展"},
    {"name": "Log Stream", "port": 8094, "category": "P1扩展"},
    {"name": "Kanban Service", "port": 8095, "category": "P1扩展"},
    {"name": "Legion Dashboard", "port": 8096, "category": "P1扩展"},
    {"name": "Skill Studio", "port": 8097, "category": "P2按需"},
    {"name": "Soul Diff Engine", "port": 8098, "category": "P2按需"},
]

# ── SQLite helpers ─────────────────────────────────────────────────────


def _check_sqlite() -> bool:
    """检查 SQLite 是否可用并能正常创建/写入数据库文件。"""
    global _SQLITE_AVAILABLE
    if _SQLITE_AVAILABLE is not None:
        return _SQLITE_AVAILABLE

    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
        conn.execute("SELECT 1")
        conn.close()
        _SQLITE_AVAILABLE = True
        logger.info("SQLite available at %s", _DB_PATH)
    except Exception as exc:
        _SQLITE_AVAILABLE = False
        logger.warning("SQLite unavailable, falling back to mock data: %s", exc)
    return _SQLITE_AVAILABLE


def _init_db() -> None:
    """初始化 health_samples 表（如果不存在）。"""
    if not _check_sqlite():
        return
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS health_samples (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                status      TEXT    NOT NULL CHECK(status IN ('up', 'down')),
                response_time_ms INTEGER NOT NULL,
                services_online   INTEGER NOT NULL,
                services_total    INTEGER NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_samples(timestamp)"
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Failed to initialize health_samples table: %s", exc)


def _insert_sample(sample: dict[str, Any]) -> None:
    """写入一条健康采样记录到 SQLite。"""
    if not _check_sqlite():
        return
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
        conn.execute(
            """
            INSERT INTO health_samples (timestamp, status, response_time_ms, services_online, services_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sample["timestamp"],
                sample["status"],
                sample["response_time_ms"],
                sample["services_online"],
                sample["services_total"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.debug("Failed to insert health sample: %s", exc)


def _query_samples(hours: int = 24) -> list[dict[str, Any]]:
    """从 SQLite 查询过去 N 小时的采样数据。"""
    if not _check_sqlite():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        conn = sqlite3.connect(str(_DB_PATH), timeout=5.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, status, response_time_ms, services_online, services_total
            FROM health_samples
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("Failed to query health samples: %s", exc)
        return []


# ── Mock data generator ───────────────────────────────────────────────


def _generate_mock_history(
    hours: int = 24, count: int | None = None
) -> list[dict[str, Any]]:
    """生成模拟健康采样数据。

    Parameters
    ----------
    hours : int
        时间范围（小时），默认 24。
    count : int | None
        采样点数量。None 时自动计算（每 30 分钟一个点）。

    Returns
    -------
    list[dict[str, Any]]
        按时间升序排列的采样点列表。
    """
    if count is None:
        count = max(12, hours * 2)  # 每 30 分钟一个点
    if count > 1000:
        count = 1000

    now = datetime.now(timezone.utc)
    samples: list[dict[str, Any]] = []
    seed = int(time.time()) % 100000

    rng = random.Random(seed)

    for i in range(count):
        # 均匀分布在时间范围内
        t = now - timedelta(hours=hours * (count - i) / max(count, 1))
        ts = t.isoformat()

        # 模拟：大部分时间 up，偶尔 down
        is_down = rng.random() < 0.08  # ~8% 采样点标记为 down
        status = "down" if is_down else "up"

        # 响应时间：正态分布 ~50ms，标准差 15ms
        response_time = max(5, int(rng.gauss(50, 15)))

        # 在线服务数：模拟波动
        services_total = 8
        if is_down:
            services_online = rng.randint(4, 7)
        else:
            services_online = rng.randint(6, 8)

        samples.append(
            {
                "timestamp": ts,
                "status": status,
                "response_time_ms": response_time,
                "services_online": services_online,
                "services_total": services_total,
            }
        )

    return samples


def _probe_service(service: dict[str, Any]) -> bool:
    """探测一个服务是否在线（模拟版 — 基于端口奇偶性模拟波动）。

    真实场景中可替换为 TCP socket 检查。
    """
    port = service.get("port", 0)
    if isinstance(port, str):
        try:
            port = int(port)
        except (ValueError, TypeError):
            port = 0

    # P0 核心服务在线率 95%，P1 在线率 85%，P2 在线率 75%
    category = service.get("category", "P2按需")
    base_rate = {"P0核心": 0.95, "P1扩展": 0.85, "P2按需": 0.75}.get(category, 0.8)

    # 用端口 + 当前分钟作为种子，使探测结果随时间缓慢变化
    now = datetime.now(timezone.utc)
    seed = port * 10000 + now.hour * 60 + now.minute
    rng = random.Random(seed)
    return rng.random() < base_rate


# ══════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════


class HealthService:
    """健康状态服务 — 提供历史趋势和当前状态查询。"""

    # ── History ───────────────────────────────────────────────────────

    @staticmethod
    def get_history(
        hours: int = 24,
    ) -> dict[str, Any]:
        """返回过去 N 小时的健康采样数据。

        Parameters
        ----------
        hours : int
            时间范围（小时），支持 1/6/12/24/48/168/720 （分别对应
            1小时/6小时/12小时/24小时/2天/7天/30天）。

        Returns
        -------
        dict[str, Any]
            ``{"samples": [...], "range_hours": hours, "total": count}``。
        """
        # 标准化到支持的枚举值
        valid_ranges = {1, 6, 12, 24, 48, 168, 720}
        if hours not in valid_ranges:
            # 就近取整
            hours = min(valid_ranges, key=lambda v: abs(v - hours))

        # 优先从 SQLite 读取
        if _check_sqlite():
            _init_db()
            samples = _query_samples(hours=hours)
            if samples:
                return {
                    "samples": samples,
                    "range_hours": hours,
                    "total": len(samples),
                    "source": "sqlite",
                }

        # 回退：生成模拟数据
        samples = _generate_mock_history(hours=hours)
        return {
            "samples": samples,
            "range_hours": hours,
            "total": len(samples),
            "source": "mock",
        }

    # ── Current Status ────────────────────────────────────────────────

    @staticmethod
    def get_current_status() -> dict[str, Any]:
        """返回当前系统各服务的健康状态。

        Returns
        -------
        dict[str, Any]
            包含 ``overall_status``、``uptime_pct``、``avg_response_time_ms``、
            ``services`` 列表和 ``generated_at``。
        """
        services: list[dict[str, Any]] = []
        online_count = 0
        total_response_time = 0
        checked_count = 0

        for svc_def in _DEFAULT_SERVICES:
            is_online = _probe_service(svc_def)

            # 模拟响应时间
            rng = random.Random(
                int(svc_def.get("port", 0)) * 1000 + int(time.time()) // 15
            )
            latency = max(5, int(rng.gauss(45, 20)))

            services.append(
                {
                    "name": svc_def["name"],
                    "port": svc_def["port"],
                    "category": svc_def["category"],
                    "status": "up" if is_online else "down",
                    "response_time_ms": latency if is_online else 0,
                }
            )

            if is_online:
                online_count += 1
                total_response_time += latency
            checked_count += 1

        total = len(services)
        uptime_pct = round(online_count / total * 100, 1) if total > 0 else 0.0
        avg_response = (
            round(total_response_time / max(online_count, 1), 1)
            if online_count > 0
            else 0.0
        )

        # 判定整体状态
        if total == 0:
            overall_status = "unknown"
        elif uptime_pct >= 95:
            overall_status = "healthy"
        elif uptime_pct >= 75:
            overall_status = "degraded"
        else:
            overall_status = "critical"

        return {
            "overall_status": overall_status,
            "uptime_pct": uptime_pct,
            "avg_response_time_ms": avg_response,
            "services": services,
            "total_services": total,
            "online_services": online_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Record a sample (for cron / periodic tasks) ───────────────────

    @staticmethod
    def record_sample(force_mock: bool = False) -> dict[str, Any]:
        """记录一个即时的健康采样点。

        Parameters
        ----------
        force_mock : bool
            即使 SQLite 可用也强制使用模拟数据（用于测试）。

        Returns
        -------
        dict[str, Any]
            写入的采样数据。
        """
        status_data = HealthService.get_current_status()
        total = status_data["total_services"]
        online = status_data["online_services"]
        avg_rt = status_data["avg_response_time_ms"]

        # 如果平均响应时间 > 200ms 或在线率 < 50%，标记为 down
        is_down = avg_rt > 200 or (total > 0 and online / total < 0.5)
        status_str = "down" if is_down else "up"

        sample = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status_str,
            "response_time_ms": int(avg_rt),
            "services_online": online,
            "services_total": total,
        }

        if not force_mock and _check_sqlite():
            _init_db()
            _insert_sample(sample)
        elif force_mock:
            logger.debug("Forced mock mode — not writing to SQLite")

        return sample
