"""
Talent Matcher — AI数智军团技能匹配与任务路由服务.

为 dashbaord 管理的注册员工（data/employees/ 下 JSON）提供：

1. ``match_task_to_employee`` — 根据任务描述 / 关键词匹配员工技能标签
2. ``suggest_team`` — 根据项目描述建议最优团队组合

设计原则
---------
* 基于简单关键词匹配（Jaccard 相似度 + 词频权重），无需外部 NLP 依赖。
* 匹配对象为 dashbaord 自已注册的员工，不扫描主宫殿 employees/ 目录。
"""

from __future__ import annotations

import json
import logging
import re
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Stop words (中英文混合) ──────────────────────────────────────────
_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "为", "所以", "因为", "但是", "可以", "被", "把", "让", "从", "对",
    "与", "及", "或", "等", "之", "其", "中", "将", "向", "并", "而",
    "所", "能", "应", "该", "还", "已", "经", "没", "做", "用", "以",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out",
    "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not",
    "only", "own", "same", "so", "than", "too", "very", "just", "also",
    "about", "up", "and", "but", "or", "if", "while", "because", "until",
    "this", "that", "these", "those",
}

# ── Data directory ─────────────────────────────────────────────────────

_DATA_DIR = Path(
    os.getenv(
        "DASHBOARD_DATA_DIR",
        str(Path(__file__).resolve().parent.parent / "data"),
    )
)
_EMPLOYEES_DATA_DIR = _DATA_DIR / "employees"


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════


def _tokenize(text: str) -> list[str]:
    """将文本分词，过滤停用词和短词（< 2 字符）。

    Parameters
    ----------
    text : str
        原始文本（中英文均可）。

    Returns
    -------
    list[str]
        有效词干的列表。
    """
    # 统一小写
    text = text.lower()
    # 提取中文汉字 + 英文单词（含连字符）
    tokens: list[str] = re.findall(r"[\u4e00-\u9fff]+|[a-z][a-z0-9_-]+", text)
    # 过滤停用词和单字符
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """计算两个集合的 Jaccard 相似度。"""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _load_employees() -> list[dict[str, Any]]:
    """从 data/employees/ 加载所有注册员工。

    Returns
    -------
    list[dict[str, Any]]
        员工数据列表（已反序列化）。
    """
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
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning(
                        "Failed to load employee file %s: %s", entry.name, exc
                    )
    except OSError as exc:
        logger.error("Failed to scan employees data dir: %s", exc)
    return employees


def _compute_score(
    task_tokens: set[str], employee: dict[str, Any]
) -> float:
    """计算任务与单个员工的匹配得分。

    综合考虑：
    * skill_tags 的 Jaccard 相似度（权重 0.7）
    * role 的关键词命中（权重 0.2）
    * personality 的关键词命中（权重 0.1）

    Parameters
    ----------
    task_tokens : set[str]
        任务描述的分词集合。
    employee : dict[str, Any]
        员工数据字典。

    Returns
    -------
    float
        0.0 ~ 1.0 的匹配得分。
    """
    # 技能标签匹配
    skill_tags: list[str] = employee.get("skill_tags", []) or []
    skill_tokens = _tokenize(" ".join(skill_tags))
    skill_jaccard = _jaccard_similarity(task_tokens, set(skill_tokens))

    # Role 匹配
    role = employee.get("role", "") or ""
    role_tokens = _tokenize(role)
    role_jaccard = _jaccard_similarity(task_tokens, set(role_tokens))

    # Personality 匹配
    personality = employee.get("personality", "") or ""
    personality_tokens = _tokenize(personality)
    personality_jaccard = _jaccard_similarity(
        task_tokens, set(personality_tokens)
    )

    # 加权综合
    score = (
        skill_jaccard * 0.7
        + role_jaccard * 0.2
        + personality_jaccard * 0.1
    )
    return round(score, 4)


# ══════════════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════════════


def match_task_to_employee(
    task_description: str,
    employees: list[dict[str, Any]] | None = None,
    min_score: float = 0.0,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """根据任务描述匹配最合适的员工。

    对任务描述进行分词，然后与每位员工的 skill_tags、role、personality
    做 Jaccard 相似度加权匹配，返回按得分降序排列的员工列表。

    Parameters
    ----------
    task_description : str
        任务描述文本（自然语言）。
    employees : list[dict[str, Any]] | None
        待匹配的员工列表。为 ``None`` 时自动从 data/employees/ 加载。
    min_score : float
        最低得分阈值（默认 0.0，即全部返回）。
    top_k : int
        最多返回多少名员工（默认 10）。

    Returns
    -------
    list[dict[str, Any]]
        按匹配度降序排列的列表，每个元素为员工数据字典，
        额外包含 ``_match_score`` 字段。
    """
    if employees is None:
        employees = _load_employees()

    if not employees or not task_description.strip():
        return []

    task_tokens = set(_tokenize(task_description))
    if not task_tokens:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for emp in employees:
        score = _compute_score(task_tokens, emp)
        if score >= min_score:
            scored.append((score, emp))

    # 按得分降序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 截断 top_k
    result = []
    for score, emp in scored[:top_k]:
        entry = dict(emp)  # 浅拷贝
        entry["_match_score"] = score
        result.append(entry)

    return result


def suggest_team(
    project_description: str,
    min_members: int = 2,
    max_members: int = 5,
) -> dict[str, Any]:
    """根据项目描述建议最优团队组合。

    策略
    ----
    1. 匹配所有员工获得得分列表。
    2. 选择得分最高的员工作为核心成员。
    3. 尽可能覆盖不同的 skill_tags 领域（多样性）。
    4. 最终团队在 ``[min_members, max_members]`` 之间。

    Parameters
    ----------
    project_description : str
        项目描述文本。
    min_members : int
        最小团队成员数（默认 2）。
    max_members : int
        最大团队成员数（默认 5）。

    Returns
    -------
    dict[str, Any]
        包含 ``team``（成员列表）、``coverage``（技能覆盖度）
        和 ``rationale``（推荐理由摘要）的字典。
    """
    employees = _load_employees()
    if not employees:
        return {
            "team": [],
            "coverage": 0.0,
            "rationale": "暂无注册员工，无法组建团队。",
        }

    matched = match_task_to_employee(project_description, employees)
    if not matched:
        return {
            "team": [],
            "coverage": 0.0,
            "rationale": "未找到与项目描述匹配的员工。",
        }

    # 构建核心团队：优先高匹配度，同时保证 skill 多样性
    selected: list[dict[str, Any]] = []
    covered_skills: set[str] = set()
    project_tokens = set(_tokenize(project_description))

    # 第一步：选择得分最高的成员（核心）
    core = matched[0]
    selected.append(core)
    core_skills = set(
        t.lower()
        for t in (core.get("skill_tags", []) or [])
    )
    covered_skills.update(core_skills)

    # 第二步：贪心选择 — 每次选一个能最大程度扩展技能覆盖的员工
    candidates = [e for e in matched[1:]]
    while len(selected) < max_members and candidates:
        best_idx = -1
        best_new_skills = 0
        for i, cand in enumerate(candidates):
            cand_skills = set(
                t.lower()
                for t in (cand.get("skill_tags", []) or [])
            )
            new_skills = len(cand_skills - covered_skills)
            if new_skills > best_new_skills:
                best_new_skills = new_skills
                best_idx = i

        if best_idx == -1 or best_new_skills == 0:
            # 无法再扩展技能覆盖，停止
            if len(selected) >= min_members:
                break
            # 如果没达到最小人数，取下一个最高分的
            best_idx = 0

        selected.append(candidates.pop(best_idx))
        cand_skills = set(
            t.lower()
            for t in (selected[-1].get("skill_tags", []) or [])
        )
        covered_skills.update(cand_skills)

    # 计算技能覆盖度
    total_project_skills = len(project_tokens) or 1
    matched_project_skills = sum(
        1 for t in project_tokens if any(t in s for s in covered_skills)
    )
    coverage = round(matched_project_skills / total_project_skills, 2)

    # 生成推荐理由
    member_list = [e.get("name", "?") for e in selected]
    rationale = (
        f"基于项目「{project_description[:50]}」进行技能匹配，"
        f"推荐 {len(selected)} 人团队：{', '.join(member_list)}。"
        f"技能覆盖度 {coverage:.0%}。"
    )

    return {
        "team": selected,
        "coverage": coverage,
        "rationale": rationale,
        "total_matches": len(matched),
    }
