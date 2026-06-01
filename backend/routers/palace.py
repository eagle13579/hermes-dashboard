"""
Palace Router — 记忆宫殿 L1-L5 数据查询与归档 API
==================================================

Endpoints
=========
===================================  =====  ==============================
Path                                  Method  Description
===================================  =====  ==============================
/api/palace/skills                   GET    搜索主宫殿 skills/ 技能
/api/palace/library                  GET    查询 L1图书馆 资源
/api/palace/models                   GET    查询 L3 心智模型
/api/palace/products                 GET    查询 L5 产品资料
/api/palace/archive/code             POST   归档代码到 L1图书馆/代码资产库
/api/palace/archive/model            POST   归档心智模型到 L3五池/模型池
/api/palace/archive/adr              POST   归档架构决策到 L1图书馆/ADR
===================================  =====  ==============================
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from config import settings
from models.request import ArchiveAdrRequest, ArchiveCodeRequest, ArchiveModelRequest
from security.auth import require_api_key

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/palace", tags=["Palace — 记忆宫殿"])


# ── Helper utilities ───────────────────────────────────────────────────


def _palace_path(*segments: str) -> Path:
    """Resolve a path under the main palace (hermes_home).

    All lookups are derived from ``settings.hermes_home`` which points to
    ``D:/向海容的知识库/wiki/wiki/记忆宫殿``.
    """
    return Path(settings.hermes_home).joinpath(*segments)


def _safe_read_dir(path: Path) -> list[Path]:
    """Return sorted list of directory entries, empty if missing."""
    if not path.is_dir():
        return []
    try:
        return sorted(
            [p for p in path.iterdir() if p.is_dir()],
            key=lambda p: p.name.lower(),
        )
    except OSError:
        return []


def _safe_read_text(path: Path, max_lines: int = 20) -> str:
    """Read first *max_lines* lines of a text file, safely."""
    if not path.is_file():
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n\r"))
            return "\n".join(lines)
    except OSError:
        return ""


def _parse_frontmatter(text: str) -> dict:
    """Parse YAML-like frontmatter between ``---`` markers.

    This is a lightweight parser (no yaml dependency required). Returns a
    dict of key-value pairs found between the first two ``---`` lines.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str | list[str]] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Handle list values like [a, b, c]
            if val.startswith("[") and val.endswith("]"):
                result[key] = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",")]
            else:
                result[key] = val.strip('"').strip("'")
    return result


def _atomic_write(path: Path, content: str) -> None:
    """Atomically write *content* to *path* using a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _build_adr_filename(title: str) -> str:
    """Generate an ADR filename from a title.

    Scans existing ADR files for the next sequential number, then returns
    something like ``ADR-012-my-decision-title.md``.
    """
    adr_dir = _palace_path("L1图书馆", "ADR")
    existing = []
    if adr_dir.is_dir():
        for child in adr_dir.iterdir():
            if child.suffix.lower() == ".md" and child.stem.startswith("ADR-"):
                try:
                    num = int(child.stem.split("-")[1])
                    existing.append(num)
                except (IndexError, ValueError):
                    pass
    next_num = max(existing) + 1 if existing else 1
    # Slugify the title
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in title.lower())
    slug = "-".join(p for p in slug.split("-") if p)[:60]
    return f"ADR-{next_num:03d}-{slug}.md"


def _sanitize_dirname(name: str) -> str:
    """Sanitize a string to be safe as a directory name."""
    return "".join(c for c in name if c.isalnum() or c in " _-+()（）,，.").strip() or "unnamed"


# ── GET  /api/palace/skills — 搜索技能 ────────────────────────────────


@router.get("/skills")
async def query_skills(
    q: Annotated[
        Optional[str],
        Query(description="搜索关键词（匹配名称和描述，模糊搜索）"),
    ] = None,
    category: Annotated[
        Optional[str],
        Query(description="分类过滤（如 cognitive, productivity, mlops, creative 等）"),
    ] = None,
    limit: Annotated[
        int, Query(description="每页数量（默认 50，最大 200）", ge=1, le=200)
    ] = 50,
    offset: Annotated[
        int, Query(description="分页偏移（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """搜索主记忆宫殿 ``skills/`` 目录下的技能。

    扫描每个技能目录中的 ``SKILL.md`` 和 ``DESCRIPTION.md``，
    解析其 frontmatter 以获取名称、描述、分类和标签。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int}``
    """
    skills_dir = _palace_path("skills")
    if not skills_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skills directory not found: {skills_dir}",
        )

    results: list[dict] = []
    for skill_dir in _safe_read_dir(skills_dir):
        skill_name = skill_dir.name
        description = ""
        tags: list[str] = []
        skill_category = "general"

        # Try SKILL.md first, then DESCRIPTION.md
        skill_md = skill_dir / "SKILL.md"
        desc_md = skill_dir / "DESCRIPTION.md"

        text = ""
        if skill_md.is_file():
            text = _safe_read_text(skill_md, max_lines=20)
        elif desc_md.is_file():
            text = _safe_read_text(desc_md, max_lines=20)

        if text:
            fm = _parse_frontmatter(text)
            description = fm.get("description", "")
            tags = fm.get("tags", [])
            skill_category = fm.get("category", "general")
            # Use name from frontmatter if available
            skill_name = fm.get("name", skill_name)

        # If still no description, try first non-frontmatter paragraph
        if not description and text:
            lines = text.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                    description = stripped[:200]
                    break

        # Filter by search query
        if q:
            q_lower = q.lower()
            name_match = q_lower in skill_name.lower()
            desc_match = q_lower in description.lower()
            tag_match = any(q_lower in t.lower() for t in (tags if isinstance(tags, list) else []))
            if not name_match and not desc_match and not tag_match:
                continue

        # Filter by category
        if category and category.lower() != skill_category.lower():
            continue

        results.append({
            "name": skill_name,
            "description": description[:500],
            "category": skill_category,
            "tags": tags if isinstance(tags, list) else [],
            "path": str(skill_dir.resolve()),
        })

    total = len(results)
    paged = results[offset : offset + limit]

    return {
        "results": paged,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ── GET  /api/palace/library — 查询 L1图书馆资源 ──────────────────────


@router.get("/library")
async def query_library(
    type: Annotated[
        Optional[str],
        Query(
            alias="type",
            description=(
                "资源类型过滤: ``skills_cards`` (技能吸收卡), "
                "``code_harvest`` (代码资产库), "
                "``adr`` (架构决策), "
                "``all`` (全部，默认)"
            ),
        ),
    ] = None,
    q: Annotated[
        Optional[str],
        Query(description="搜索关键词（可选）"),
    ] = None,
    limit: Annotated[
        int, Query(description="每页数量（默认 50，最大 200）", ge=1, le=200)
    ] = 50,
    offset: Annotated[
        int, Query(description="分页偏移（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """查询 L1图书馆 资源。

    支持按类型过滤和关键词搜索。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int}``
    """
    library_path = _palace_path("L1图书馆")
    if not library_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"L1图书馆 directory not found: {library_path}",
        )

    type_filter = (type or "all").lower()
    results: list[dict] = []

    # ── 技能吸收卡 ────────────────────────────────────────────────────
    if type_filter in ("all", "skills_cards"):
        cards_dir = library_path / "技能吸收卡"
        for card_dir in _safe_read_dir(cards_dir):
            name = card_dir.name
            desc = ""
            # Read .md files inside
            for f in sorted(card_dir.iterdir()):
                if f.suffix.lower() == ".md":
                    text = _safe_read_text(f, max_lines=10)
                    fm = _parse_frontmatter(text)
                    desc = fm.get("description", desc)
                    if not desc:
                        for line in text.split("\n")[:5]:
                            stripped = line.strip()
                            if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                                desc = stripped[:200]
                                break
                    break
            if not desc:
                # Try DESCRIPTION.md or .md files
                for f in card_dir.iterdir():
                    if f.suffix.lower() == ".md":
                        text = _safe_read_text(f, max_lines=15)
                        fm = _parse_frontmatter(text)
                        desc = fm.get("description", "")
                        break
            entry = {
                "type": "skills_cards",
                "name": name,
                "description": desc[:500],
                "path": str(card_dir.resolve()),
            }
            if q and q.lower() not in name.lower() and q.lower() not in desc.lower():
                continue
            results.append(entry)

    # ── 代码资产库 ────────────────────────────────────────────────────
    if type_filter in ("all", "code_harvest"):
        code_dir = library_path / "代码资产库"
        for code_subdir in _safe_read_dir(code_dir):
            name = code_subdir.name
            desc = ""
            readme = code_subdir / "README.md"
            if readme.is_file():
                desc = _safe_read_text(readme, max_lines=5)[:200]
            # Count files inside
            file_count = 0
            try:
                file_count = sum(1 for _ in code_subdir.rglob("*") if _.is_file())
            except OSError:
                pass
            entry = {
                "type": "code_harvest",
                "name": name,
                "description": desc,
                "file_count": file_count,
                "path": str(code_subdir.resolve()),
            }
            if q and q.lower() not in name.lower() and q.lower() not in desc.lower():
                continue
            results.append(entry)

    # ── ADR ───────────────────────────────────────────────────────────
    if type_filter in ("all", "adr"):
        adr_dir = library_path / "ADR"
        for adr_file in sorted(adr_dir.iterdir()):
            if adr_file.suffix.lower() != ".md":
                continue
            text = _safe_read_text(adr_file, max_lines=20)
            fm = _parse_frontmatter(text)
            title = fm.get("title", adr_file.stem)
            status_val = fm.get("status", "")
            decision = fm.get("decision", "")
            entry = {
                "type": "adr",
                "name": title,
                "filename": adr_file.name,
                "status": status_val,
                "description": decision[:300] if decision else title,
                "path": str(adr_file.resolve()),
            }
            if q and q.lower() not in title.lower() and q.lower() not in decision.lower():
                continue
            results.append(entry)

    total = len(results)
    paged = results[offset : offset + limit]

    return {
        "results": paged,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ── GET  /api/palace/models — 查询心智模型 ────────────────────────────


@router.get("/models")
async def query_models(
    q: Annotated[
        Optional[str],
        Query(description="搜索关键词（可选）"),
    ] = None,
    limit: Annotated[
        int, Query(description="每页数量（默认 50，最大 200）", ge=1, le=200)
    ] = 50,
    offset: Annotated[
        int, Query(description="分页偏移（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """查询 L3 心智模型。

    扫描 ``L3工作室/五池/模型池/`` 目录。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int}``
    """
    # Check multiple possible model pool locations
    candidates = [
        _palace_path("L3工作室", "五池", "模型池"),
        _palace_path("L0前厅", "五池", "模型池"),
        _palace_path("五池", "模型池"),
    ]

    model_dir: Optional[Path] = None
    for c in candidates:
        if c.is_dir():
            model_dir = c
            break

    if model_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No model pool directory found (checked L3/五池/模型池, L0前厅/五池/模型池, 五池/模型池)",
        )

    results: list[dict] = []
    for f in sorted(model_dir.iterdir()):
        if f.suffix.lower() not in (".md", ".txt"):
            continue
        text = _safe_read_text(f, max_lines=20)
        fm = _parse_frontmatter(text)
        name = fm.get("name", f.stem)
        description = fm.get("description", fm.get("desc", ""))
        applicable_scenarios = fm.get("applicable_scenarios", fm.get("scenarios", ""))
        tags = fm.get("tags", [])

        # Fallback: use first non-frontmatter paragraph as description
        if not description and text:
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                    description = stripped[:300]
                    break

        entry = {
            "name": name,
            "description": description[:500],
            "applicable_scenarios": applicable_scenarios[:500] if applicable_scenarios else "",
            "tags": tags if isinstance(tags, list) else [],
            "path": str(f.resolve()),
        }

        if q:
            q_lower = q.lower()
            if (
                q_lower not in name.lower()
                and q_lower not in description.lower()
                and q_lower not in applicable_scenarios.lower()
            ):
                continue

        results.append(entry)

    total = len(results)
    paged = results[offset : offset + limit]

    return {
        "results": paged,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ── GET  /api/palace/products — 查询产品资料 ──────────────────────────


@router.get("/products")
async def query_products(
    q: Annotated[
        Optional[str],
        Query(description="搜索关键词（可选）"),
    ] = None,
    status_filter: Annotated[
        Optional[str],
        Query(
            alias="status",
            description="状态过滤（如 active, incubating, archived, all）",
        ),
    ] = None,
    limit: Annotated[
        int, Query(description="每页数量（默认 50，最大 200）", ge=1, le=200)
    ] = 50,
    offset: Annotated[
        int, Query(description="分页偏移（默认 0）", ge=0)
    ] = 0,
) -> dict:
    """查询 L5 产品资料。

    扫描 ``L5孵化室/产品开发/`` 目录中的产品子目录。

    Returns
    -------
    dict
        ``{"results": [...], "total": int, "offset": int, "limit": int}``
    """
    products_dir = _palace_path("L5孵化室", "产品开发")
    if not products_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"L5孵化室/产品开发 directory not found: {products_dir}",
        )

    results: list[dict] = []
    for prod_dir in _safe_read_dir(products_dir):
        name = prod_dir.name
        description = ""
        status_val = "incubating"

        # Look for a README.md or .md file for description
        for f in sorted(prod_dir.iterdir()):
            if f.suffix.lower() == ".md":
                text = _safe_read_text(f, max_lines=15)
                fm = _parse_frontmatter(text)
                description = fm.get("description", "")
                status_val = fm.get("status", status_val)
                if not description:
                    for line in text.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("---") and not stripped.startswith("#"):
                            description = stripped[:300]
                            break
                break

        # Count files
        file_count = 0
        try:
            file_count = sum(1 for _ in prod_dir.rglob("*") if _.is_file())
        except OSError:
            pass

        entry = {
            "name": name,
            "description": description[:500],
            "status": status_val,
            "file_count": file_count,
            "path": str(prod_dir.resolve()),
        }

        # Apply filters
        if status_filter and status_filter.lower() != "all":
            if status_filter.lower() != status_val.lower():
                continue
        if q:
            q_lower = q.lower()
            if q_lower not in name.lower() and q_lower not in description.lower():
                continue

        results.append(entry)

    total = len(results)
    paged = results[offset : offset + limit]

    return {
        "results": paged,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


# ── POST  /api/palace/archive/code — 归档代码 ────────────────────────


@router.post("/archive/code", status_code=status.HTTP_201_CREATED)
async def archive_code(body: ArchiveCodeRequest, _auth: None = Depends(require_api_key)) -> dict:
    """将代码收割归档到 ``L1图书馆/代码资产库/``。

    原子写入模式：先写入临时文件，再重命名为目标文件。

    Returns
    -------
    dict
        ``{"status": "ok", "path": "...", "name": "..."}``
    """
    name_slug = _sanitize_dirname(body.name)
    target_dir = _palace_path("L1图书馆", "代码资产库", name_slug)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Write main code file
    lang_map = {
        "python": ".py",
        "typescript": ".ts",
        "javascript": ".js",
        "go": ".go",
        "rust": ".rs",
        "java": ".java",
        "cpp": ".cpp",
        "c": ".c",
        "shell": ".sh",
        "sql": ".sql",
        "yaml": ".yaml",
        "json": ".json",
        "markdown": ".md",
        "html": ".html",
        "css": ".css",
    }
    ext = lang_map.get((body.language or "").lower(), ".md")
    code_file = target_dir / f"main{ext}"

    _atomic_write(code_file, body.content)
    logger.info("Archived code to %s", code_file)

    # Write description / README if provided
    if body.description:
        readme_file = target_dir / "README.md"
        readme_content = f"# {body.name}\n\n{body.description}\n"
        if body.tags:
            readme_content += f"\nTags: {', '.join(body.tags)}\n"
        if body.language:
            readme_content += f"\nLanguage: {body.language}\n"
        _atomic_write(readme_file, readme_content)

    # Write metadata
    meta = {
        "name": body.name,
        "description": body.description,
        "language": body.language,
        "tags": body.tags,
    }
    _atomic_write(target_dir / ".meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    return {
        "status": "ok",
        "path": str(target_dir.resolve()),
        "name": body.name,
    }


# ── POST  /api/palace/archive/model — 归档心智模型 ────────────────────


@router.post("/archive/model", status_code=status.HTTP_201_CREATED)
async def archive_model(body: ArchiveModelRequest, _auth: None = Depends(require_api_key)) -> dict:
    """将心智模型归档到 ``L3五池/模型池/``。

    尝试按优先级写入：
    1. ``L3工作室/五池/模型池/``
    2. ``L0前厅/五池/模型池/``
    3. ``五池/模型池/``

    Returns
    -------
    dict
        ``{"status": "ok", "path": "...", "name": "..."}``
    """
    # Determine target directory
    candidates = [
        _palace_path("L3工作室", "五池", "模型池"),
        _palace_path("L0前厅", "五池", "模型池"),
        _palace_path("五池", "模型池"),
    ]

    target_dir: Optional[Path] = None
    for c in candidates:
        if c.is_dir():
            target_dir = c
            break

    if target_dir is None:
        # Use L3 as default and create it
        target_dir = candidates[0]
        target_dir.mkdir(parents=True, exist_ok=True)

    name_slug = _sanitize_dirname(body.name)
    model_file = target_dir / f"{name_slug}.md"

    # Build markdown content
    lines = ["---"]
    lines.append(f"name: {body.name}")
    lines.append(f"description: {body.description}")
    if body.applicable_scenarios:
        lines.append(f"applicable_scenarios: {body.applicable_scenarios}")
    if body.tags:
        lines.append(f"tags: [{', '.join(body.tags)}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {body.name}")
    lines.append("")
    lines.append(body.description)
    if body.applicable_scenarios:
        lines.append("")
        lines.append("## 适用场景")
        lines.append("")
        lines.append(body.applicable_scenarios)
    if body.content:
        lines.append("")
        lines.append(body.content)

    _atomic_write(model_file, "\n".join(lines))
    logger.info("Archived mental model to %s", model_file)

    return {
        "status": "ok",
        "path": str(model_file.resolve()),
        "name": body.name,
    }


# ── POST  /api/palace/archive/adr — 归档架构决策 ──────────────────────


@router.post("/archive/adr", status_code=status.HTTP_201_CREATED)
async def archive_adr(body: ArchiveAdrRequest, _auth: None = Depends(require_api_key)) -> dict:
    """将架构决策归档到 ``L1图书馆/ADR/``。

    自动生成顺序编号文件名（如 ``ADR-012-选型FastAPI-React.md``）。

    Returns
    -------
    dict
        ``{"status": "ok", "path": "...", "filename": "...", "title": "..."}``
    """
    adr_dir = _palace_path("L1图书馆", "ADR")
    adr_dir.mkdir(parents=True, exist_ok=True)

    filename = _build_adr_filename(body.title)
    adr_file = adr_dir / filename

    # Build ADR markdown
    lines = ["---"]
    lines.append(f"title: {body.title}")
    lines.append(f"status: {body.status}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {body.title}")
    lines.append("")
    lines.append("## 状态")
    lines.append("")
    lines.append(body.status)
    lines.append("")
    lines.append("## 上下文")
    lines.append("")
    lines.append(body.context)
    lines.append("")
    lines.append("## 决策")
    lines.append("")
    lines.append(body.decision)
    if body.consequences:
        lines.append("")
        lines.append("## 后果")
        lines.append("")
        lines.append(body.consequences)
    if body.alternatives:
        lines.append("")
        lines.append("## 备选方案")
        lines.append("")
        for alt in body.alternatives:
            lines.append(f"- {alt}")

    _atomic_write(adr_file, "\n".join(lines))
    logger.info("Archived ADR to %s", adr_file)

    return {
        "status": "ok",
        "path": str(adr_file.resolve()),
        "filename": filename,
        "title": body.title,
    }
