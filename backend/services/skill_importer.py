"""
Skill Importer Service — 主记忆宫殿 skill 导入到 hermes-dashboard 的技能索引.

从主宫殿 skills/{category}/{name}/ 读取 SKILL.md，
创建到 dashboard 的引用链接（不是复制文件），
更新 skills_registry.json 索引。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

_PALACE_HOME = Path(
    os.getenv(
        "HERMES_HOME",
        "D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿",
    )
)
"""主记忆宫殿根目录。"""

_DASHBOARD_DIR = Path(
    "D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿\\profiles\\hermes-dashboard"
)
"""hermes-dashboard 目录。"""

_REGISTRY_PATH = _DASHBOARD_DIR / "data" / "skills_registry.json"
"""技能注册表 JSON 文件路径。"""

_SKILLS_DIR = _PALACE_HOME / "skills"
"""主宫殿技能目录。"""

_DASHBOARD_SKILLS_DIR = _DASHBOARD_DIR / "skills"
"""dashboard 技能引用目录。"""

# ── Cache for registry ─────────────────────────────────────────────────

_registry_cache: dict[str, Any] | None = None


def _get_registry() -> dict[str, Any]:
    """加载 skills_registry.json，带缓存。"""
    global _registry_cache
    if _registry_cache is not None:
        return _registry_cache
    if _REGISTRY_PATH.is_file():
        try:
            _registry_cache = json.loads(
                _REGISTRY_PATH.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load registry: %s", exc)
            _registry_cache = {"version": "1.0", "imported_skills": {}}
    else:
        _registry_cache = {"version": "1.0", "imported_skills": {}}
    return _registry_cache


def _save_registry(registry: dict[str, Any]) -> None:
    """保存 skills_registry.json 并刷新缓存。"""
    global _registry_cache
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _registry_cache = registry


def _get_iso_now() -> str:
    """返回当前 UTC 时间 ISO-8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


# ── Scanning ───────────────────────────────────────────────────────────


def get_palace_skills(force_reload: bool = False) -> list[dict[str, Any]]:
    """从 skills_registry.json 获取所有可导入的主宫殿技能列表。

    Parameters
    ----------
    force_reload : bool
        是否强制从磁盘重新加载注册表。

    Returns
    -------
    list[dict[str, Any]]
        所有候选技能的元数据列表。
    """
    registry = _get_registry()
    skills = registry.get("imported_skills", {})
    result = []
    for skill_name, meta in skills.items():
        entry = dict(meta)
        entry["source_exists"] = (
            Path(meta.get("source_path", "")).is_file()
            if meta.get("source_path")
            else False
        )
        entry["dashboard_imported"] = meta.get("imported_at") is not None
        result.append(entry)
    return result


def get_importable_skills() -> list[dict[str, Any]]:
    """返回尚未导入到 dashboard 的主宫殿技能列表。"""
    return [s for s in get_palace_skills() if not s["dashboard_imported"]]


# ── Import Logic ───────────────────────────────────────────────────────


def import_skill(skill_name: str) -> dict[str, Any]:
    """将主宫殿的一个 skill 导入到 dashboard 技能索引。

    逻辑：
    1. 从 skills_registry.json 找到该 skill 的元数据
    2. 验证源 SKILL.md 存在
    3. 在 dashboard/skills/{category}/{skill_name}/ 下创建引用文件
       （包含指向主宫殿原始位置的 README.md 引用）
    4. 更新 registry 中的 imported_at 时间戳

    Parameters
    ----------
    skill_name : str
        要导入的技能名称（注册表中的 key）。

    Returns
    -------
    dict[str, Any]
        导入结果：success, skill_name, dashboard_ref, message。

    Raises
    ------
    ValueError
        如果技能名称不在注册表中或已导入。
    FileNotFoundError
        如果源 SKILL.md 不存在。
    OSError
        如果文件操作失败。
    """
    registry = _get_registry()
    skills = registry.get("imported_skills", {})

    if skill_name not in skills:
        raise ValueError(
            f"技能 '{skill_name}' 不在注册表中。"
            f" 可用技能: {list(skills.keys())}"
        )

    meta = skills[skill_name]

    if meta.get("imported_at") is not None:
        raise ValueError(
            f"技能 '{skill_name}' 已经导入过"
            f"（导入时间: {meta['imported_at']}）。"
            f" 如需重新导入，请先 reset。"
        )

    source_path = Path(meta["source_path"])
    if not source_path.is_file():
        raise FileNotFoundError(
            f"源 SKILL.md 不存在: {source_path}"
        )

    # 读取源 SKILL.md 内容
    try:
        source_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"读取源文件失败 {source_path}: {exc}")

    # 创建 dashboard 引用目录
    category = meta["category"]
    ref_dir = _DASHBOARD_SKILLS_DIR / category / skill_name
    ref_dir.mkdir(parents=True, exist_ok=True)

    # 写入 README.md 引用文件（不是复制源文件，而是创建引用链接）
    ref_content = (
        f"# {meta.get('display_name', skill_name)}\n"
        f"\n"
        f"> 此技能来自主记忆宫殿，已通过 hermes-dashboard skill_importer 导入。\n"
        f"\n"
        f"## 源位置\n"
        f"\n"
        f"`{source_path}`\n"
        f"\n"
        f"## 源文件内容摘要\n"
        f"\n"
        f"```\n"
        f"{source_content[:500]}{'...' if len(source_content) > 500 else ''}\n"
        f"```\n"
        f"\n"
        f"## 导入时间\n"
        f"\n"
        f"{_get_iso_now()}\n"
        f"\n"
        f"## 元数据\n"
        f"\n"
        f"- **名称**: {meta.get('display_name', skill_name)}\n"
        f"- **分类**: {category}\n"
        f"- **版本**: {meta.get('version', 'N/A')}\n"
        f"- **描述**: {meta.get('description', '')}\n"
        f"\n"
        f"## 引用\n"
        f"\n"
        f"要查看完整的 SKILL.md 内容，请打开主记忆宫殿中的源文件:\n"
        f"\n"
        f"```\n"
        f"{source_path}\n"
        f"```\n"
    )

    ref_path = ref_dir / "README.md"
    ref_path.write_text(ref_content, encoding="utf-8")

    # 创建一个 .palace_ref 标记文件，记录源路径
    marker_path = ref_dir / ".palace_ref"
    marker_path.write_text(
        json.dumps(
            {
                "source_path": str(source_path),
                "imported_at": _get_iso_now(),
                "skill_name": skill_name,
                "category": category,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 更新注册表
    now = _get_iso_now()
    meta["imported_at"] = now
    skills[skill_name] = meta
    _save_registry(registry)

    logger.info(
        "Imported skill '%s' → %s (from %s)",
        skill_name, ref_dir, source_path,
    )

    return {
        "success": True,
        "skill_name": skill_name,
        "category": category,
        "dashboard_ref": str(ref_dir),
        "source_path": str(source_path),
        "imported_at": now,
        "message": f"技能 '{meta.get('display_name', skill_name)}' 导入成功",
    }


def batch_import_skills(skill_names: list[str]) -> dict[str, Any]:
    """批量导入多个主宫殿技能。

    Parameters
    ----------
    skill_names : list[str]
        要导入的技能名称列表。

    Returns
    -------
    dict[str, Any]
        包含 results（每个技能的导入结果）、success_count、fail_count 的字典。
    """
    results: list[dict[str, Any]] = []
    success_count = 0
    fail_count = 0

    for name in skill_names:
        try:
            result = import_skill(name)
            results.append(result)
            success_count += 1
        except (ValueError, FileNotFoundError, OSError) as exc:
            results.append(
                {
                    "success": False,
                    "skill_name": name,
                    "error": str(exc),
                }
            )
            fail_count += 1

    return {
        "results": results,
        "total": len(skill_names),
        "success_count": success_count,
        "fail_count": fail_count,
    }


def reset_import(skill_name: str) -> dict[str, Any]:
    """重置一个技能的导入状态（清空 imported_at，删除引用文件）。

    Parameters
    ----------
    skill_name : str
        要重置的技能名称。

    Returns
    -------
    dict[str, Any]
        操作结果。
    """
    registry = _get_registry()
    skills = registry.get("imported_skills", {})

    if skill_name not in skills:
        raise ValueError(f"技能 '{skill_name}' 不在注册表中")

    meta = skills[skill_name]

    # 清理 dashboard 引用目录
    category = meta["category"]
    ref_dir = _DASHBOARD_SKILLS_DIR / category / skill_name
    if ref_dir.is_dir():
        import shutil
        shutil.rmtree(ref_dir)
        logger.info("Removed dashboard ref directory: %s", ref_dir)

    # 重置 imported_at
    meta["imported_at"] = None
    skills[skill_name] = meta
    _save_registry(registry)

    return {
        "success": True,
        "skill_name": skill_name,
        "message": f"技能 '{skill_name}' 导入状态已重置",
    }


def count_imported_skills() -> int:
    """返回已导入的技能数量。"""
    registry = _get_registry()
    skills = registry.get("imported_skills", {})
    return sum(1 for meta in skills.values() if meta.get("imported_at") is not None)


def count_available_skills() -> int:
    """返回注册表中总技能数量。"""
    registry = _get_registry()
    return len(registry.get("imported_skills", {}))
