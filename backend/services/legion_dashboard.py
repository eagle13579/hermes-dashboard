"""
Legion Dashboard — AI数智军团看板服务层.

提供军团员工扫描、服务健康检测、Profile 活跃度统计以及
灵魂质量分布统计等核心业务逻辑。所有文件操作使用
Windows 原生 D:\\ 路径以确保在本地开发环境正常运转。
"""

from __future__ import annotations

import logging
import os
import re
import socket
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════════

_HERMES_HOME = Path("D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿")
"""军团知识库根目录（Windows 原生 D: 路径）。"""

_EMPLOYEES_DIR = _HERMES_HOME / "employees"
"""员工目录。"""

_PROFILES_DIR = _HERMES_HOME / "profiles"
"""Profile 目录。"""

_REGISTRY_FILE = _HERMES_HOME / "registry" / "service_registry.yaml"
"""服务注册文件。"""

_MEMORY_FILE = _HERMES_HOME / "MEMORY.md"
"""军团记忆文件。"""


# ══════════════════════════════════════════════════════════════════════
#  Data Models
# ══════════════════════════════════════════════════════════════════════


@dataclass
class LegionStats:
    """AI数智军团总览统计数据模型。

    Attributes
    ----------
    total_employees : int
        员工总数。
    elite_count : int
        精锐员工数（有独立灵魂+觉醒记录）。
    standard_count : int
        标准员工数（有基本灵魂配置）。
    shell_count : int
        空壳员工数（仅目录结构，无灵魂）。
    online_services : int
        当前在线服务数。
    services_total : int
        注册服务总数。
    active_profiles : int
        活跃 Profile 数。
    total_profiles : int
        Profile 总数。
    """

    total_employees: int = 0
    elite_count: int = 0
    standard_count: int = 0
    shell_count: int = 0
    online_services: int = 0
    services_total: int = 0
    active_profiles: int = 0
    total_profiles: int = 0
    imported_skills: int = 0
    """已导入的 dashboard skill 数量。"""

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的字典表示。"""
        return asdict(self)


@dataclass
class EmployeeInfo:
    """单个员工信息模型。

    Attributes
    ----------
    name : str
        员工姓名。
    employee_id : str
        员工唯一标识符。
    level : str
        员工等级（如 P8）。
    department : str
        所属部门。
    type : str
        员工类型（如 engineer, analyst）。
    status : str
        当前状态（active / inactive）。
    soul_level : str
        灵魂等级：elite / standard / shell。
    has_awakening : bool
        是否有觉醒记录。
    mental_models : list[str]
        心智模型列表。
    emotional_anchors : list[dict[str, str]]
        情感锚点列表。
    capabilities : list[str]
        能力列表。
    """

    name: str = ""
    employee_id: str = ""
    level: str = ""
    department: str = ""
    type: str = ""
    status: str = "active"
    soul_level: str = "shell"
    has_awakening: bool = False
    mental_models: list[str] = field(default_factory=list)
    emotional_anchors: list[dict[str, str]] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的字典表示。"""
        return asdict(self)


@dataclass
class ServiceInfo:
    """单个服务状态模型。

    Attributes
    ----------
    port : str
        服务端口。
    name : str
        服务名称。
    category : str
        服务类别（P0核心 / P1扩展 / P2按需）。
    online : bool
        是否在线。
    auto_start : bool
        是否自动启动。
    health_check : str
        健康检查方式（http / tcp）。
    watch_priority : int
        值守优先级。
    """

    port: str = ""
    name: str = ""
    category: str = ""
    online: bool = False
    auto_start: bool = False
    health_check: str = "http"
    watch_priority: int = 3

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的字典表示。"""
        return asdict(self)


@dataclass
class ProfileInfo:
    """Profile 基本信息。

    Attributes
    ----------
    name : str
        Profile 名称。
    is_active : bool
        是否活跃（有 SOUL.md）。
    soul_summary : str
        灵魂摘要（SOUL.md 前 200 字符）。
    """

    name: str = ""
    is_active: bool = False
    soul_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的字典表示。"""
        return asdict(self)


@dataclass
class SoulDistribution:
    """灵魂质量分布数据。

    Attributes
    ----------
    elite : int
        精锐员工数。
    standard : int
        标准员工数。
    shell : int
        空壳员工数。
    with_awakening : int
        有觉醒记录的员工数。
    total_souls : int
        有灵魂注入的员工总数。
    """

    elite: int = 0
    standard: int = 0
    shell: int = 0
    with_awakening: int = 0
    total_souls: int = 0

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 安全的字典表示。"""
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════
#  Helper utilities
# ══════════════════════════════════════════════════════════════════════


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """安全加载 YAML 文件，出错时返回 None。"""
    try:
        import yaml

        if not path.is_file():
            return None
        with open(str(path), encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.warning("Failed to load YAML %s: %s", path, exc)
        return None


def _check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """检测指定端口是否开放（TCP 连接检查）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.error):
        return False


# ══════════════════════════════════════════════════════════════════════
#  Scanning logic
# ══════════════════════════════════════════════════════════════════════


def _classify_employee(
    emp_dir: Path,
) -> tuple[str, bool, list[str], list[dict[str, str]]]:
    """对单个员工目录进行灵魂质量分级。

    Parameters
    ----------
    emp_dir : Path
        员工目录路径。

    Returns
    -------
    tuple[str, bool, list[str], list[dict[str, str]]]
        (soul_level, has_awakening, mental_models, emotional_anchors)
    """
    employee_yaml = emp_dir / "employee.yaml"
    soul_yaml = emp_dir / "soul-injection.yaml"

    # 检查 employee.yaml 是否存在
    if not employee_yaml.is_file():
        return "shell", False, [], []

    emp_data = _load_yaml(employee_yaml)
    if not emp_data:
        return "shell", False, [], []

    # 检查 soul-injection.yaml
    if not soul_yaml.is_file():
        return "shell", False, [], []

    soul_data = _load_yaml(soul_yaml)
    if not soul_data:
        return "shell", False, [], []

    # 解析觉醒记录
    awakening_marks = soul_data.get("awakening_marks") or []
    has_awakening = len(awakening_marks) > 0

    # 解析心智模型
    mental_models: list[str] = []
    raw_mm = soul_data.get("mental_models") or soul_data.get("mandates") or []
    if isinstance(raw_mm, list):
        for item in raw_mm:
            if isinstance(item, str):
                mental_models.append(item)

    # 解析情感锚点
    emotional_anchors: list[dict[str, str]] = []
    raw_ea = soul_data.get("emotional_anchors") or []
    if isinstance(raw_ea, list):
        for item in raw_ea:
            if isinstance(item, dict):
                anchor: dict[str, str] = {}
                anchor["name"] = str(item.get("name", item.get("type", "")))
                anchor["description"] = str(
                    item.get("description", item.get("trigger", ""))
                )
                if anchor["name"]:
                    emotional_anchors.append(anchor)

    # 从 employee.yaml 的 soul_injection 字段读取
    emp_soul = emp_data.get("soul_injection") or {}
    soul_enabled = emp_soul.get("enabled", False)

    # 从 personality 字段获取额外信息
    personality = soul_data.get("personality") or {}
    core_identity = soul_data.get("core_identity", "")

    # 判定等级
    if has_awakening and soul_enabled and len(emotional_anchors) >= 3:
        return "elite", has_awakening, mental_models, emotional_anchors
    elif soul_enabled or core_identity:
        return "standard", has_awakening, mental_models, emotional_anchors
    else:
        return "shell", has_awakening, mental_models, emotional_anchors


# ══════════════════════════════════════════════════════════════════════
#  LegionDashboard — Public API
# ══════════════════════════════════════════════════════════════════════


class LegionDashboard:
    """AI数智军团看板 — 军团状态聚合与数据扫描。

    提供对员工、服务、Profile 的静态扫描方法，所有操作都是同步的，
    可直接在 FastAPI 路由中调用。
    """

    # ── Scan Employees ────────────────────────────────────────────────

    @staticmethod
    def scan_employees() -> list[EmployeeInfo]:
        """扫描 ``$HERMES_HOME/employees/`` 下所有 ``emp-*`` 目录，
        统计每位员工的灵魂等级分布。

        Returns
        -------
        list[EmployeeInfo]
            所有员工的信息列表。
        """
        if not _EMPLOYEES_DIR.is_dir():
            logger.warning("Employees directory not found: %s", _EMPLOYEES_DIR)
            return []

        employees: list[EmployeeInfo] = []
        try:
            for entry in sorted(_EMPLOYEES_DIR.iterdir()):
                if not entry.is_dir():
                    continue
                dirname = entry.name
                if not dirname.startswith("emp-"):
                    continue

                # 读取 employee.yaml
                emp_data = _load_yaml(entry / "employee.yaml")
                if not emp_data:
                    # 有目录但无有效 employee.yaml，作为空壳记录
                    employees.append(
                        EmployeeInfo(
                            name=dirname,
                            employee_id=dirname,
                            soul_level="shell",
                        )
                    )
                    continue

                # 灵魂分级
                soul_level, has_awakening, mental_models, emotional_anchors = (
                    _classify_employee(entry)
                )

                # 提取基础字段
                name = str(emp_data.get("name", dirname))
                emp_id = str(emp_data.get("employee_id", dirname))
                level = str(emp_data.get("level", ""))
                department = str(
                    emp_data.get("department", emp_data.get("squad", ""))
                )
                emp_type = str(emp_data.get("type", ""))
                status = str(emp_data.get("status", "active"))
                capabilities: list[str] = emp_data.get("capabilities") or []

                employees.append(
                    EmployeeInfo(
                        name=name,
                        employee_id=emp_id,
                        level=level,
                        department=department,
                        type=emp_type,
                        status=status,
                        soul_level=soul_level,
                        has_awakening=has_awakening,
                        mental_models=mental_models,
                        emotional_anchors=emotional_anchors,
                        capabilities=capabilities,
                    )
                )
        except OSError as exc:
            logger.error("Failed to scan employees directory: %s", exc)

        logger.info(
            "Employee scan complete: %d employees found", len(employees)
        )
        return employees

    # ── Scan Services ─────────────────────────────────────────────────

    @staticmethod
    def scan_services() -> list[ServiceInfo]:
        """从 ``service_registry.yaml`` 读取注册服务列表，
        通过 TCP socket 扫描在线状态。

        Returns
        -------
        list[ServiceInfo]
            所有已注册服务的在线状态列表。
        """
        if not _REGISTRY_FILE.is_file():
            logger.warning("Service registry not found: %s", _REGISTRY_FILE)
            return []

        data = _load_yaml(_REGISTRY_FILE)
        if not data:
            return []

        raw_services: dict[str, Any] = data.get("services") or {}
        services: list[ServiceInfo] = []

        for port_str, svc_info in raw_services.items():
            if not isinstance(svc_info, dict):
                continue

            name = str(svc_info.get("name", ""))
            category = str(svc_info.get("category", "P2按需"))
            auto_start = bool(svc_info.get("auto_start", False))
            health_check = str(svc_info.get("health_check", "http"))
            watch_priority = int(svc_info.get("watch_priority", 3))

            # 只扫描 P0 和 P1 服务
            if "P0" not in category and "P1" not in category:
                continue

            try:
                port_int = int(port_str)
            except ValueError:
                port_int = 0

            online = False
            if port_int > 0 and port_int < 65536:
                online = _check_port_open("127.0.0.1", port_int)

            services.append(
                ServiceInfo(
                    port=port_str,
                    name=name,
                    category=category,
                    online=online,
                    auto_start=auto_start,
                    health_check=health_check,
                    watch_priority=watch_priority,
                )
            )

        # P0 排在前面
        services.sort(key=lambda s: (0 if "P0" in s.category else 1, s.port))
        logger.info(
            "Service scan complete: %d P0/P1 services, %d online",
            len(services),
            sum(1 for s in services if s.online),
        )
        return services

    # ── Scan Profiles ─────────────────────────────────────────────────

    @staticmethod
    def scan_profiles() -> list[ProfileInfo]:
        """扫描 ``$HERMES_HOME/profiles/`` 下的所有 Profile，
        以 ``SOUL.md`` 是否存在判定活跃状态。

        Returns
        -------
        list[ProfileInfo]
            所有 Profile 的列表。
        """
        if not _PROFILES_DIR.is_dir():
            logger.warning("Profiles directory not found: %s", _PROFILES_DIR)
            return []

        profiles: list[ProfileInfo] = []
        try:
            for entry in sorted(_PROFILES_DIR.iterdir()):
                if not entry.is_dir():
                    continue
                name = entry.name
                if name.startswith("."):
                    continue

                soul_path = entry / "SOUL.md"
                is_active = soul_path.is_file()
                soul_summary = ""
                if is_active:
                    try:
                        text = soul_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                        soul_summary = text.strip()[:200].replace(
                            "\n", " "
                        ).strip()
                    except OSError as exc:
                        logger.warning(
                            "Failed to read SOUL.md in %s: %s", name, exc
                        )

                profiles.append(
                    ProfileInfo(
                        name=name,
                        is_active=is_active,
                        soul_summary=soul_summary,
                    )
                )
        except OSError as exc:
            logger.error("Failed to scan profiles directory: %s", exc)

        logger.info(
            "Profile scan complete: %d profiles (%d active)",
            len(profiles),
            sum(1 for p in profiles if p.is_active),
        )
        return profiles

    # ── Get Overview ──────────────────────────────────────────────────

    @staticmethod
    def get_overview() -> dict[str, Any]:
        """返回军团总览数据。

        聚合员工数、服务数、Profile 数，并计算健康度百分比。
        健康度 = (精锐员工数 + 标准员工数) / 总员工数 * 100，
        但如果总员工数为 0 则返回 100%。

        Returns
        -------
        dict[str, Any]
            总览数据字典，包含 ``legion_stats`` (LegionStats 字典)
            和 ``health_pct`` (健康度百分比)。
        """
        employees = LegionDashboard.scan_employees()
        services = LegionDashboard.scan_services()
        profiles = LegionDashboard.scan_profiles()

        # 统计已导入的 dashboard skill 数量
        try:
            from services.skill_importer import count_imported_skills
            imported_skill_count = count_imported_skills()
        except Exception:
            imported_skill_count = 0

        elite_count = sum(1 for e in employees if e.soul_level == "elite")
        standard_count = sum(
            1 for e in employees if e.soul_level == "standard"
        )
        shell_count = sum(1 for e in employees if e.soul_level == "shell")

        stats = LegionStats(
            total_employees=len(employees),
            elite_count=elite_count,
            standard_count=standard_count,
            shell_count=shell_count,
            online_services=sum(1 for s in services if s.online),
            services_total=len(services),
            active_profiles=sum(1 for p in profiles if p.is_active),
            total_profiles=len(profiles),
            imported_skills=imported_skill_count,
        )

        total = stats.total_employees
        health_pct = (
            round((stats.elite_count + stats.standard_count) / total * 100, 1)
            if total > 0
            else 100.0
        )

        return {
            "legion_stats": stats.to_dict(),
            "health_pct": health_pct,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Get Employee Detail ──────────────────────────────────────────

    @staticmethod
    def get_employee_detail(name: str) -> dict[str, Any] | None:
        """查询单个员工的详细信息。

        Parameters
        ----------
        name : str
            员工姓名或 employee_id。

        Returns
        -------
        dict[str, Any] | None
            员工详情字典，未找到时返回 None。
        """
        employees = LegionDashboard.scan_employees()
        for emp in employees:
            if emp.name == name or emp.employee_id == name:
                result = emp.to_dict()
                # 尝试读取完整的 soul-injection.yaml 作为附加数据
                emp_dir = _find_employee_dir(emp.employee_id)
                if emp_dir:
                    soul_data = _load_yaml(emp_dir / "soul-injection.yaml")
                    if soul_data:
                        result["core_identity"] = soul_data.get(
                            "core_identity", ""
                        )
                        result["personality"] = soul_data.get(
                            "personality", {}
                        )
                        result["mandates"] = soul_data.get("mandates", [])
                return result
        return None

    # ── Get Service Detail ────────────────────────────────────────────

    @staticmethod
    def get_service_detail(port: str) -> dict[str, Any] | None:
        """查询单个服务的详细信息。

        Parameters
        ----------
        port : str
            服务端口号。

        Returns
        -------
        dict[str, Any] | None
            服务详情字典，未找到时返回 None。
        """
        services = LegionDashboard.scan_services()
        for svc in services:
            if svc.port == port or svc.port == str(port):
                return svc.to_dict()
        return None

    # ── Soul Distribution ─────────────────────────────────────────────

    @staticmethod
    def get_soul_distribution() -> dict[str, Any]:
        """统计灵魂质量分布数据。

        Returns
        -------
        dict[str, Any]
            灵魂分布数据，包含各级别计数和比例。
        """
        employees = LegionDashboard.scan_employees()

        elite = sum(1 for e in employees if e.soul_level == "elite")
        standard = sum(1 for e in employees if e.soul_level == "standard")
        shell = sum(1 for e in employees if e.soul_level == "shell")
        with_awakening = sum(1 for e in employees if e.has_awakening)

        dist = SoulDistribution(
            elite=elite,
            standard=standard,
            shell=shell,
            with_awakening=with_awakening,
            total_souls=elite + standard,
        )

        total = len(employees) or 1  # 防止除以零
        return {
            "distribution": dist.to_dict(),
            "elite_pct": round(elite / total * 100, 1),
            "standard_pct": round(standard / total * 100, 1),
            "shell_pct": round(shell / total * 100, 1),
            "awakening_pct": round(with_awakening / total * 100, 1),
            "total_employees": len(employees),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Recent Activity ───────────────────────────────────────────────

    @staticmethod
    def get_recent_activity(limit: int = 20) -> list[dict[str, str]]:
        """从 MEMORY.md 中提取最近活动摘要。

        Parameters
        ----------
        limit : int
            返回的最大条目数（默认 20）。

        Returns
        -------
        list[dict[str, str]]
            活动条目列表，每条包含 ``timestamp`` 和 ``summary``。
        """
        if not _MEMORY_FILE.is_file():
            logger.warning("MEMORY.md not found: %s", _MEMORY_FILE)
            return []

        try:
            text = _MEMORY_FILE.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.error("Failed to read MEMORY.md: %s", exc)
            return []

        entries: list[dict[str, str]] = []
        # 匹配形如 "## 2026-05-31 07:08 白泽苏醒" 的标题行
        pattern = re.compile(
            r"^##\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s*[·\-–—]\s*(.+?)$",
            re.MULTILINE,
        )
        for match in pattern.finditer(text):
            timestamp = match.group(1).strip()
            summary = match.group(2).strip()
            entries.append(
                {
                    "timestamp": timestamp,
                    "summary": summary,
                }
            )

        # 另提取以 "|-" 或 "| -" 开头的条目行（MEMORY.md 中的列表条目）
        list_pattern = re.compile(
            r"^\|\s*[-–—]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s*[·\-–—]\s*(.+?)$",
            re.MULTILINE,
        )
        for match in list_pattern.finditer(text):
            timestamp = match.group(1).strip()
            summary = match.group(2).strip()
            # 去重
            if not any(
                e["timestamp"] == timestamp and e["summary"] == summary
                for e in entries
            ):
                entries.append({"timestamp": timestamp, "summary": summary})

        # 按时间倒序排列（最近在前）
        entries.sort(key=lambda e: e["timestamp"], reverse=True)
        return entries[:limit]

    # ── Employees List ────────────────────────────────────────────────

    @staticmethod
    def get_employees_list(
        page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """返回分页的员工列表。

        Parameters
        ----------
        page : int
            页码（从 1 开始）。
        page_size : int
            每页条目数。

        Returns
        -------
        dict[str, Any]
            包含 ``items``、``total``、``page``、``page_size`` 和
            ``total_pages`` 的字典。
        """
        employees = LegionDashboard.scan_employees()
        total = len(employees)
        total_pages = max(1, (total + page_size - 1) // page_size)

        start = (page - 1) * page_size
        end = start + page_size
        page_items = [e.to_dict() for e in employees[start:end]]

        return {
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }


# ══════════════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════════════


def _find_employee_dir(employee_id: str) -> Path | None:
    """根据 employee_id 查找对应的员工目录。"""
    if not _EMPLOYEES_DIR.is_dir():
        return None
    try:
        for entry in _EMPLOYEES_DIR.iterdir():
            if entry.is_dir() and entry.name.startswith("emp-"):
                if employee_id in entry.name or entry.name == employee_id:
                    return entry
    except OSError:
        pass
    return None
