"""
Hermes Dashboard — 跨Profile知识检索服务 (Knowledge Search Service).

跨记忆宫殿 L1–L5 层级搜索技能、原子、代码资产、心智模型和产品文档。
使用纯 Python 内置模块 (fnmatch + os.walk) 实现，无需外部搜索引擎。
搜索结果缓存到 JSON 文件以加速重复查询。

SearchResult 模型
=================
type           — skill / atom / code / mental_model / doc
name           — 文档或文件名
path           — 完整文件路径（Windows 原生格式）
snippet        — 匹配上下文片段
profile_source — 所属 Profile 名称（跨 Profile 搜索时填 "common"）
relevance_score — 0.0–1.0 相关度评分
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

SEARCHABLE_TYPES = frozenset({"skill", "atom", "code", "mental_model", "doc"})

# 知识库层级 → (描述名, 路径后缀, 文件匹配模式)
SEARCH_SOURCES: dict[str, tuple[str, str, str]] = {
    "skill": ("技能", "skills", "SKILL.md"),
    "code": ("代码资产", "L1图书馆/代码资产库", "*"),
    "mental_model": ("心智模型", "L3工作室/五池/模型池", "*"),
    "product": ("产品文档", "L5孵化室/产品开发", "PRODUCT.md"),
}

# ── Data Models ────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    """单个搜索结果数据模型。"""

    type: str  # skill / atom / code / mental_model / doc
    name: str
    path: str
    snippet: str = ""
    profile_source: str = "common"
    relevance_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchIndex:
    """搜索索引缓存（内存 + JSON 持久化）。"""

    entries: list[SearchResult] = field(default_factory=list)
    built_at: float = 0.0  # timestamp
    profiles_indexed: set[str] = field(default_factory=set)


# ── Service Class ──────────────────────────────────────────────────────


class KnowledgeSearchService:
    """知识检索服务 —— 扫描文件系统，进行文本匹配与排序。"""

    def __init__(self, hermes_home: str | Path | None = None) -> None:
        self._lock = Lock()
        self._index: SearchIndex = SearchIndex()
        self._cache_dir: Path
        self._hermes_home: Path

        if hermes_home is not None:
            self._hermes_home = Path(hermes_home).resolve()
        else:
            self._hermes_home = Path(
                os.getenv(
                    "HERMES_HOME",
                    str(Path.home() / "向海容的知识库" / "wiki" / "wiki" / "记忆宫殿"),
                )
            ).resolve()

        # Cache directory: inside the dashboard profile
        self._cache_dir = (
            self._hermes_home
            / "profiles"
            / "hermes-dashboard"
            / "backend"
            / ".knowledge_cache"
        )
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "KnowledgeSearchService initialised — HERMES_HOME=%s",
            self._hermes_home,
        )

    # ── Public helpers ──────────────────────────────────────────────────

    def _resolve_path(self, relative: str) -> Path:
        """将相对于 HERMES_HOME 的路径字符串解析为绝对 Path。"""
        return (self._hermes_home / relative).resolve()

    def _read_file_safe(self, path: Path, max_chars: int = 4096) -> str:
        """安全读取文件，返回最多 max_chars 字符的内容。"""
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("Cannot read %s: %s", path, exc)
            return ""

    def _compute_relevance(
        self, query: str, content: str, filename: str, path: str
    ) -> float:
        """计算 0.0–1.0 的相关度分数。

        规则：
          - 文件名精确匹配 query → 1.0
          - 文件名包含 query (fnmatch) → 0.9
          - 内容包含完整 query → 0.7
          - 内容包含 query 的每个词 → 0.5
          - 内容包含部分词 → 0.3
          - 无匹配 → 0.0
        """
        q_lower = query.lower().strip()
        if not q_lower:
            return 0.0

        name_lower = filename.lower()
        content_lower = content.lower()

        # 文件名精确匹配
        if name_lower == q_lower or name_lower == f"{q_lower}.md":
            return 1.0

        # fnmatch 匹配
        if fnmatch.fnmatch(name_lower, f"*{q_lower}*"):
            return 0.9

        # 内容完整匹配
        if q_lower in content_lower:
            return 0.7

        # 分词匹配
        terms = q_lower.split()
        matched = sum(1 for t in terms if t in content_lower)
        if matched == len(terms) and len(terms) > 1:
            return 0.6
        if matched > 0:
            return 0.3 + (0.2 * matched / len(terms))

        return 0.0

    def _extract_snippet(self, content: str, query: str, max_len: int = 120) -> str:
        """从内容中提取包含查询词的上下文片段。"""
        q_lower = query.lower().strip()
        if not q_lower or not content:
            return content[:max_len].replace("\n", " ")

        content_lower = content.lower()
        idx = content_lower.find(q_lower)
        if idx == -1:
            # 分词查找
            terms = q_lower.split()
            for t in terms:
                idx = content_lower.find(t)
                if idx != -1:
                    break
        if idx == -1:
            return content[:max_len].replace("\n", " ")

        start = max(0, idx - 40)
        end = min(len(content), idx + len(q_lower) + 40)
        snippet = content[start:end].replace("\n", " ")
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        return snippet[:max_len]

    def _walk_files(
        self, root: Path, pattern: str, query: str
    ) -> list[SearchResult]:
        """在 root 目录下递归查找匹配 pattern 的文件，返回 SearchResult 列表。"""
        results: list[SearchResult] = []
        if not root.is_dir():
            return results

        try:
            for dirpath_str, _dirnames, filenames in os.walk(str(root)):
                for fname in filenames:
                    if not fnmatch.fnmatch(fname, pattern):
                        continue
                    fpath = Path(dirpath_str) / fname
                    content = self._read_file_safe(fpath)
                    score = self._compute_relevance(query, content, fname, str(fpath))
                    if score > 0.0:
                        snippet = self._extract_snippet(content, query)
                        results.append(
                            SearchResult(
                                type=self._infer_type(fpath),
                                name=fname,
                                path=str(fpath),
                                snippet=snippet,
                                relevance_score=round(score, 4),
                            )
                        )
        except OSError as exc:
            logger.warning("Error walking %s: %s", root, exc)

        return results

    def _infer_type(self, path: Path) -> str:
        """根据路径推断资源类型。"""
        path_str = str(path).replace("\\", "/")
        if "skills" in path_str and "SKILL.md" in path_str:
            return "skill"
        if "L1图书馆/代码资产库" in path_str:
            return "code"
        if "L3工作室/五池/模型池" in path_str or "五池" in path_str:
            return "mental_model"
        if "L5孵化室/产品开发" in path_str:
            return "doc"
        return "doc"

    # ── Core search methods ────────────────────────────────────────────

    def search_skills(self, query: str) -> list[SearchResult]:
        """在 $HERMES_HOME/skills/ 下搜索 SKILL.md。

        同时在 skills/ 子目录名和 SKILL.md 文件名/内容中匹配。
        """
        results: list[SearchResult] = []
        skills_root = self._resolve_path("skills")
        if not skills_root.is_dir():
            logger.debug("skills directory not found: %s", skills_root)
            return results

        # 搜索 SKILL.md 文件
        results.extend(self._walk_files(skills_root, "SKILL.md", query))

        # 也搜索 skills/ 下的 .md 文件（部分技能可能用其他文件名）
        results.extend(self._walk_files(skills_root, "*.md", query))

        # 去重（以 path 为键）
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in results:
            if r.path not in seen:
                seen.add(r.path)
                r.type = "skill"
                deduped.append(r)
        return deduped

    def search_code_assets(self, query: str) -> list[SearchResult]:
        """在 $HERMES_HOME/L1图书馆/代码资产库/ 下搜索。

        搜索文件名和内容。
        """
        code_root = self._resolve_path("L1图书馆/代码资产库")
        return self._walk_files(code_root, "*", query)

    def search_mental_models(self, query: str) -> list[SearchResult]:
        """在 $HERMES_HOME/L3工作室/五池/模型池/ 下搜索。

        如果目录不存在，回退到 L3工作室/五池/ 下搜索。
        """
        model_pool = self._resolve_path("L3工作室/五池/模型池")
        if model_pool.is_dir():
            return self._walk_files(model_pool, "*", query)
        # 回退到 L3工作室/五池/
        fallback = self._resolve_path("L3工作室/五池")
        logger.debug("模型池不存在，回退到 %s", fallback)
        return self._walk_files(fallback, "*.md", query)

    def search_products(self, query: str) -> list[SearchResult]:
        """在 $HERMES_HOME/L5孵化室/产品开发/ 下搜索 PRODUCT.md。"""
        prod_root = self._resolve_path("L5孵化室/产品开发")
        results = self._walk_files(prod_root, "PRODUCT.md", query)
        # 也搜索 .md 文件
        results.extend(self._walk_files(prod_root, "*.md", query))
        # 去重
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for r in results:
            if r.path not in seen:
                seen.add(r.path)
                r.type = "doc"
                deduped.append(r)
        return deduped

    def search_all(self, query: str) -> list[SearchResult]:
        """合并所有来源的搜索结果，按 relevance_score 降序排列。"""
        results: list[SearchResult] = []
        results.extend(self.search_skills(query))
        results.extend(self.search_code_assets(query))
        results.extend(self.search_mental_models(query))
        results.extend(self.search_products(query))

        # 排序
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results

    def search_by_profile(self, query: str, profile_name: str) -> list[SearchResult]:
        """在指定 Profile 目录下搜索所有资源文件。"""
        profile_dir = self._resolve_path(f"profiles/{profile_name}")
        if not profile_dir.is_dir():
            logger.warning("Profile directory not found: %s", profile_dir)
            return []

        results = self._walk_files(profile_dir, "*.md", query)
        results.extend(self._walk_files(profile_dir, "*.yaml", query))
        results.extend(self._walk_files(profile_dir, "*.yml", query))
        results.extend(self._walk_files(profile_dir, "*.json", query))

        # 标记 profile_source
        for r in results:
            r.profile_source = profile_name

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results

    # ── Index / Cache ──────────────────────────────────────────────────

    def _cache_path(self, name: str = "index") -> Path:
        return self._cache_dir / f"{name}.json"

    def rebuild_index(self) -> dict:
        """重建搜索索引缓存 —— 扫描所有可搜索目录。"""
        start = time.time()
        all_entries: list[SearchResult] = []

        # 扫描所有 sources
        all_entries.extend(self.search_skills(""))
        query_all = ""  # 空查询获取所有文件
        all_entries.extend(self.search_code_assets(query_all))
        all_entries.extend(self.search_mental_models(query_all))
        all_entries.extend(self.search_products(query_all))

        # 扫描 profiles
        profiles_root = self._resolve_path("profiles")
        if profiles_root.is_dir():
            for p_dir in profiles_root.iterdir():
                if p_dir.is_dir() and not p_dir.name.startswith("_"):
                    for f in p_dir.rglob("*.md"):
                        content = self._read_file_safe(f)
                        all_entries.append(
                            SearchResult(
                                type=self._infer_type(f),
                                name=f.name,
                                path=str(f),
                                snippet=content[:120].replace("\n", " "),
                                profile_source=p_dir.name,
                                relevance_score=0.0,
                            )
                        )
                    for f in p_dir.rglob("*.yaml"):
                        all_entries.append(
                            SearchResult(
                                type="doc",
                                name=f.name,
                                path=str(f),
                                snippet="",
                                profile_source=p_dir.name,
                                relevance_score=0.0,
                            )
                        )

        # 去重
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for e in all_entries:
            if e.path not in seen:
                seen.add(e.path)
                deduped.append(e)

        self._index.entries = deduped
        self._index.built_at = time.time()

        # 持久化
        self._save_cache()

        elapsed = time.time() - start
        stats = self._compute_stats(deduped)
        stats["elapsed_seconds"] = round(elapsed, 3)
        logger.info(
            "Index rebuilt: %d entries in %.2fs", len(deduped), elapsed
        )
        return stats

    def _save_cache(self) -> None:
        """将索引保存到 JSON 缓存文件。"""
        data = {
            "built_at": self._index.built_at,
            "entries": [e.to_dict() for e in self._index.entries],
        }
        cache_file = self._cache_path()
        try:
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write cache: %s", exc)

    def _load_cache(self) -> bool:
        """从 JSON 缓存加载索引。成功返回 True。"""
        cache_file = self._cache_path()
        if not cache_file.is_file():
            return False
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            self._index.built_at = data.get("built_at", 0.0)
            self._index.entries = [
                SearchResult(**e) for e in data.get("entries", [])
            ]
            return True
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to load cache: %s", exc)
            return False

    def get_search_stats(self) -> dict:
        """获取搜索索引统计信息。

        返回
        ----
        dict 包含 total_docs, categories (各类别计数), profiles_count,
              last_built 等。
        """
        # 尝试加载缓存
        if not self._index.entries:
            self._load_cache()

        entries = self._index.entries
        if not entries:
            # 实时扫描
            return self.rebuild_index()

        return self._compute_stats(entries)

    def _compute_stats(self, entries: list[SearchResult]) -> dict:
        """计算统计信息。"""
        from collections import Counter

        type_counter: Counter[str] = Counter()
        profile_sources: set[str] = set()

        for e in entries:
            type_counter[e.type] += 1
            if e.profile_source and e.profile_source != "common":
                profile_sources.add(e.profile_source)

        return {
            "total_documents": len(entries),
            "categories": dict(type_counter),
            "profiles_count": len(profile_sources),
            "profiles": sorted(profile_sources),
            "last_built": self._index.built_at,
            "cache_path": str(self._cache_path()),
            "hermes_home": str(self._hermes_home),
        }

    # ── Convenience search with type filter & pagination ───────────────

    def search(
        self,
        query: str,
        type_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SearchResult], int]:
        """统一的搜索入口。

        Parameters
        ----------
        query : str
            搜索关键词。
        type_filter : str | None
            限定搜索类型：skill / code / mental_model / doc / product / all。
            为 None 或 "all" 时搜索全部。
        limit : int
            每页数量（默认 20）。
        offset : int
            偏移量（默认 0）。

        Returns
        -------
        (results, total_count)
        """
        if not query or not query.strip():
            return [], 0

        if type_filter and type_filter.lower() not in ("all", "", None):
            type_lower = type_filter.lower()
            # 将 "product" 映射为 "doc"
            if type_lower == "product":
                type_lower = "doc"
            if type_lower not in SEARCHABLE_TYPES:
                raise ValueError(
                    f"Invalid type filter: {type_filter}. "
                    f"Valid: {', '.join(sorted(SEARCHABLE_TYPES))}"
                )
            if type_lower == "skill":
                results = self.search_skills(query)
            elif type_lower == "code":
                results = self.search_code_assets(query)
            elif type_lower == "mental_model":
                results = self.search_mental_models(query)
            elif type_lower == "doc":
                results = self.search_products(query)
            else:
                results = self.search_all(query)
        else:
            results = self.search_all(query)

        total = len(results)
        paged = results[offset : offset + limit]
        return paged, total


# ── Module-level singleton ─────────────────────────────────────────────

_service: Optional[KnowledgeSearchService] = None


def get_service() -> KnowledgeSearchService:
    """获取（或创建）服务单例。"""
    global _service
    if _service is None:
        _service = KnowledgeSearchService()
    return _service
