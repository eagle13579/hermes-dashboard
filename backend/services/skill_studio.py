"""
Skill Studio Service — Hermes skill development workbench.

Provides a complete toolkit for creating, editing, testing, and publishing
Hermes Agent skills.  Skills are stored as ``SKILL.md`` files under
``$HERMES_HOME/skills/{category}/{name}/SKILL.md``.

The service integrates with ``skill_manage`` (Hermes' CLI skill manager)
for registration and provides built-in templates for rapid skill creation.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "general",
        "data-pipeline",
        "api-integration",
        "analysis",
        "automation",
        "utility",
        "communication",
        "research",
    }
)
"""Allowed skill categories."""

DEFAULT_CATEGORY: str = "general"
"""Default category for new skills."""

PUBLISHED_MARKER: str = ".published"
"""Marker file name inside a skill directory indicating it is published."""


# ──────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────


@dataclass
class SkillTemplate:
    """A pre-defined skill template for rapid creation.

    Attributes
    ----------
    name : str
        Unique template identifier (e.g. ``\"basic-skill\"``).
    description : str
        Short description of what this template provides.
    category : str
        Default category for skills created from this template.
    template_content : str
        The SKILL.md content template (may contain ``{placeholder}``
        substitution markers).
    """

    name: str
    description: str
    category: str = DEFAULT_CATEGORY
    template_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillTemplate:
        return cls(**data)


@dataclass
class SkillInfo:
    """Summary information about a registered skill.

    Attributes
    ----------
    name : str
        Skill name (directory name).
    description : str
        Short description extracted from SKILL.md front matter or first line.
    category : str
        Category subdirectory the skill lives under.
    path : str
        Absolute filesystem path to the skill directory.
    is_published : bool
        Whether the skill is marked as published (``.published`` marker exists).
    created_at : str or None
        ISO-8601 timestamp of skill directory creation, if available.
    updated_at : str or None
        ISO-8601 timestamp of SKILL.md last modification, if available.
    """

    name: str
    description: str = ""
    category: str = DEFAULT_CATEGORY
    path: str = ""
    is_published: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillInfo:
        return cls(**data)


# ──────────────────────────────────────────────────────────────────────
# Path helpers
# ──────────────────────────────────────────────────────────────────────


def _get_hermes_home() -> Path:
    """Return the ``$HERMES_HOME`` directory path.

    Raises
    ------
    OSError
        If ``$HERMES_HOME`` is not set and no fallback is found.
    """
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        candidate = Path.home() / "向海容的知识库/wiki/wiki/记忆宫殿"
        if candidate.is_dir():
            return candidate.resolve()
        raise OSError(
            "HERMES_HOME environment variable is not set. "
            "Please set it to your Hermes knowledge base root, e.g.\n"
            '  export HERMES_HOME="D:\\\\\\\\向海容的知识库\\\\\\\\wiki\\\\\\\\wiki\\\\\\\\记忆宫殿"'
        )
    return Path(raw).expanduser().resolve()


def _skills_dir() -> Path:
    """Return the absolute path to ``$HERMES_HOME/skills/``."""
    skills = _get_hermes_home() / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    return skills


def _skill_dir(name: str, category: str = DEFAULT_CATEGORY) -> Path:
    """Return the directory for a specific skill under its category."""
    return _skills_dir() / category / name


def _skill_md_path(name: str, category: str = DEFAULT_CATEGORY) -> Path:
    """Return the full path to a skill's SKILL.md file."""
    return _skill_dir(name, category) / "SKILL.md"


# ──────────────────────────────────────────────────────────────────────
# Built-in templates
# ──────────────────────────────────────────────────────────────────────

_BUILTIN_TEMPLATES: list[SkillTemplate] = [
    SkillTemplate(
        name="basic-skill",
        description="Standard SKILL.md skeleton with metadata, description, and usage instructions.",
        category="general",
        template_content="""# {name}

## Metadata
- **Name**: {name}
- **Version**: 1.0.0
- **Category**: {category}
- **Description**: {description}

## Description
{description}

## Usage

```python
# Example usage
from hermes.core import skill

@skill("{name}")
def my_skill(**kwargs):
    \"\"\"{description}\"\"\"
    pass
```

## Configuration

This skill does not require any special configuration.

## Dependencies

- Python 3.10+
- hermes-core

## Notes

Add any additional notes or caveats here.
""",
    ),
    SkillTemplate(
        name="data-pipeline",
        description="File-scanning, processing, and output skill template for data pipeline tasks.",
        category="data-pipeline",
        template_content="""# {name}

## Metadata
- **Name**: {name}
- **Version**: 1.0.0
- **Category**: data-pipeline
- **Description**: {description}

## Description
{description}

## Data Flow

```
Input Path  →  [Scanner]  →  [Processor]  →  [Output Writer]  →  Output Path
```

## Configuration

```yaml
input_dir: "./input"
output_dir: "./output"
file_pattern: "*.{extension}"
batch_size: 100
encoding: "utf-8"
```

## Usage

```python
from hermes.core import skill

@skill("{name}")
def run_pipeline(**kwargs):
    \"\"\"Execute the data pipeline: scan → process → output.\"\"\"
    # 1. Scan input directory for matching files
    # 2. Process each file (transform, filter, aggregate)
    # 3. Write results to output directory
    pass
```

## Input Format

Describe the expected input file format here.

## Output Format

Describe the output file format here.

## Dependencies

- Python 3.10+
- hermes-core
- (Add any additional libraries here)
""",
    ),
    SkillTemplate(
        name="api-integration",
        description="Template for skills that call external REST APIs, with error handling and rate limiting.",
        category="api-integration",
        template_content="""# {name}

## Metadata
- **Name**: {name}
- **Version**: 1.0.0
- **Category**: api-integration
- **Description**: {description}

## Description
{description}

## API Details

- **Base URL**: `https://api.example.com/v1`
- **Authentication**: API Key (Bearer token)
- **Rate Limit**: 100 requests/minute

## Configuration

```yaml
api_base_url: "https://api.example.com/v1"
api_key_env_var: "{name_upper}_API_KEY"
timeout_seconds: 30
max_retries: 3
rate_limit_per_minute: 100
```

## Usage

```python
from hermes.core import skill
import os
import httpx

@skill("{name}")
def call_api(**kwargs):
    \"\"\"Call the external API and process the response.\"\"\"
    api_key = os.environ.get("{name_upper}_API_KEY")
    if not api_key:
        raise ValueError("{name_upper}_API_KEY environment variable not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "{api_url}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        response.raise_for_status()
        return response.json()
```

## Error Handling

- Network errors: retry up to 3 times with exponential backoff
- HTTP 4xx: check API key and request parameters
- HTTP 5xx: retry after delay; if persistent, alert operator

## Dependencies

- Python 3.10+
- hermes-core
- httpx (or requests)

## Notes

Store API keys in environment variables, never in code.
""",
    ),
]

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _get_iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _mtime_iso(path: Path) -> str | None:
    """Return modification time as ISO-8601, or None."""
    try:
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _ctime_iso(path: Path) -> str | None:
    """Return creation time as ISO-8601, or None."""
    try:
        ctime = os.path.getctime(path)
        return datetime.fromtimestamp(ctime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _call_skill_manage(action: str, **kwargs: Any) -> dict[str, Any]:
    """Invoke ``hermes skill_manage`` CLI subprocess.

    Parameters
    ----------
    action : str
        One of ``create``, ``edit``, ``delete``, ``publish``.
    **kwargs
        Additional arguments passed as JSON to the CLI.

    Returns
    -------
    dict[str, Any]
        Parsed JSON response from the CLI tool.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "hermes.cli", "skill_manage",
             "--action", action, "--json", json.dumps(kwargs)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(
                "skill_manage %s returned code %d: %s",
                action, result.returncode, result.stderr.strip(),
            )
            return {
                "success": False,
                "error": result.stderr.strip() or f"Exit code {result.returncode}",
            }

        if result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"success": True, "raw_output": result.stdout.strip()}

        return {"success": True}

    except FileNotFoundError:
        logger.warning("hermes CLI not found — skill_manage unavailable.")
        return {
            "success": False,
            "error": "hermes CLI not found. Is the Hermes package installed?",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "skill_manage timed out after 30s"}
    except Exception as exc:
        logger.error("skill_manage call failed: %s", exc)
        return {"success": False, "error": str(exc)}


def _parse_skill_description(skill_md: Path) -> str:
    """Extract a short description from a SKILL.md file.

    Tries to read the ``Description`` field from YAML-like front matter,
    then falls back to the first non-empty line after the heading.
    """
    if not skill_md.is_file():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    # Try to find a "Description:" line in front matter
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            desc = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            if desc:
                return desc

    # Fallback: first non-empty line after the heading
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("#") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line:
                return next_line[:200]

    return ""


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def list_skills() -> list[dict[str, Any]]:
    """List all Hermes-registered skills.

    Scans all category directories under ``$HERMES_HOME/skills/`` and
    returns a flat list of skill summaries.

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`SkillInfo` dictionaries.
    """
    skills: list[SkillInfo] = []
    skills_root = _skills_dir()

    if not skills_root.is_dir():
        return []

    for category_dir in sorted(skills_root.iterdir()):
        if not category_dir.is_dir():
            continue
        category = category_dir.name

        for skill_entry in sorted(category_dir.iterdir()):
            if not skill_entry.is_dir():
                continue

            skill_name = skill_entry.name
            skill_md = skill_entry / "SKILL.md"
            description = _parse_skill_description(skill_md) if skill_md.is_file() else ""
            is_published = (skill_entry / PUBLISHED_MARKER).is_file()

            skills.append(
                SkillInfo(
                    name=skill_name,
                    description=description,
                    category=category,
                    path=str(skill_entry),
                    is_published=is_published,
                    created_at=_ctime_iso(skill_entry),
                    updated_at=_mtime_iso(skill_md) if skill_md.is_file() else None,
                )
            )

    return [s.to_dict() for s in skills]


def get_skill_detail(name: str) -> dict[str, Any]:
    """Read the full content of a skill's SKILL.md file.

    Searches across all categories for a skill with the given name.

    Parameters
    ----------
    name : str
        Name of the skill to look up.

    Returns
    -------
    dict[str, Any]
        Full skill detail including name, category, path, published status,
        and the raw SKILL.md content.

    Raises
    ------
    FileNotFoundError
        If no skill with the given name is found in any category.
    """
    skills_root = _skills_dir()

    # Search across all categories
    for category_dir in skills_root.iterdir():
        if not category_dir.is_dir():
            continue
        skill_dir = category_dir / name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            try:
                content = skill_md.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                raise OSError(f"Failed to read SKILL.md for '{name}': {exc}")

            is_published = (skill_dir / PUBLISHED_MARKER).is_file()

            return {
                "name": name,
                "category": category_dir.name,
                "path": str(skill_md),
                "is_published": is_published,
                "created_at": _ctime_iso(skill_dir),
                "updated_at": _mtime_iso(skill_md),
                "content": content,
            }

    raise FileNotFoundError(
        f"Skill '{name}' not found in any category under {skills_root}"
    )


def create_skill(
    name: str,
    description: str,
    category: str = DEFAULT_CATEGORY,
    content: str | None = None,
) -> dict[str, Any]:
    """Create a new Hermes skill.

    Steps:
    1. Call ``skill_manage(action='create', ...)`` to register the skill.
    2. Write the SKILL.md content to ``$HERMES_HOME/skills/{category}/{name}/SKILL.md``.
    3. If no content is provided, use the basic-skill template.

    Parameters
    ----------
    name : str
        Name for the new skill.
    description : str
        Short description of what the skill does.
    category : str
        Category to place the skill under (default: ``general``).
    content : str or None
        Optional SKILL.md content. If None, the basic-skill template is used.

    Returns
    -------
    dict[str, Any]
        Result with ``success``, ``name``, ``path``, and ``skill_manage_result``.

    Raises
    ------
    ValueError
        If the category is invalid or the skill already exists.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. "
            f"Valid categories: {sorted(VALID_CATEGORIES)}"
        )

    # Check if skill already exists
    target_dir = _skill_dir(name, category)
    target_md = target_dir / "SKILL.md"
    if target_md.is_file():
        raise ValueError(
            f"Skill '{name}' already exists in category '{category}' at {target_md}"
        )

    # 1. Register via skill_manage
    manage_result = _call_skill_manage(
        action="create",
        name=name,
        description=description,
        category=category,
    )

    # 2. Ensure directory exists and write SKILL.md
    target_dir.mkdir(parents=True, exist_ok=True)

    if content is None:
        # Use basic-skill template as default
        template = next(
            (t for t in _BUILTIN_TEMPLATES if t.name == "basic-skill"),
            _BUILTIN_TEMPLATES[0],
        )
        content = template.template_content.format(
            name=name,
            category=category,
            description=description,
        )

    try:
        target_md.write_text(content, encoding="utf-8")
        logger.info("Created skill '%s' at %s", name, target_md)
    except OSError as exc:
        raise OSError(f"Failed to write SKILL.md for '{name}': {exc}")

    return {
        "success": True,
        "name": name,
        "category": category,
        "path": str(target_md),
        "description": description,
        "skill_manage_result": manage_result,
    }


def edit_skill(name: str, content: str) -> dict[str, Any]:
    """Edit an existing skill's SKILL.md content.

    Searches across all categories for the skill.

    Parameters
    ----------
    name : str
        Name of the skill to edit.
    content : str
        New SKILL.md content (replaces the entire file).

    Returns
    -------
    dict[str, Any]
        Result with ``success``, ``name``, ``path``, and ``skill_manage_result``.

    Raises
    ------
    FileNotFoundError
        If no skill with the given name is found.
    """
    skills_root = _skills_dir()
    target_md: Path | None = None
    target_category: str | None = None

    for category_dir in skills_root.iterdir():
        if not category_dir.is_dir():
            continue
        candidate = category_dir / name / "SKILL.md"
        if candidate.is_file():
            target_md = candidate
            target_category = category_dir.name
            break

    if target_md is None or target_category is None:
        raise FileNotFoundError(f"Skill '{name}' not found in any category.")

    # 1. Call skill_manage
    manage_result = _call_skill_manage(action="edit", name=name, category=target_category)

    # 2. Write updated content
    try:
        target_md.write_text(content, encoding="utf-8")
        logger.info("Updated skill '%s' at %s", name, target_md)
    except OSError as exc:
        raise OSError(f"Failed to write SKILL.md for '{name}': {exc}")

    return {
        "success": True,
        "name": name,
        "category": target_category,
        "path": str(target_md),
        "skill_manage_result": manage_result,
    }


def delete_skill(name: str) -> dict[str, Any]:
    """Delete a skill and its directory.

    Searches across all categories for the skill, removes the entire
    skill directory, and calls ``skill_manage(action='delete', ...)``.

    Parameters
    ----------
    name : str
        Name of the skill to delete.

    Returns
    -------
    dict[str, Any]
        Result with ``success``, ``name``, and ``skill_manage_result``.

    Raises
    ------
    FileNotFoundError
        If no skill with the given name is found.
    """
    skills_root = _skills_dir()
    target_dir: Path | None = None
    target_category: str | None = None

    for category_dir in skills_root.iterdir():
        if not category_dir.is_dir():
            continue
        candidate = category_dir / name
        if candidate.is_dir():
            target_dir = candidate
            target_category = category_dir.name
            break

    if target_dir is None or target_category is None:
        raise FileNotFoundError(f"Skill '{name}' not found in any category.")

    # 1. Call skill_manage
    manage_result = _call_skill_manage(action="delete", name=name, category=target_category)

    # 2. Remove the directory
    try:
        shutil.rmtree(target_dir)
        logger.info("Deleted skill '%s' from %s", name, target_dir)
    except OSError as exc:
        raise OSError(f"Failed to delete skill directory for '{name}': {exc}")

    return {
        "success": True,
        "name": name,
        "category": target_category,
        "skill_manage_result": manage_result,
    }


def test_skill(name: str, test_input: str = "") -> dict[str, Any]:
    """Test a skill by simulating a load-and-execute cycle.

    Locates the skill's SKILL.md, parses it, and attempts to execute
    a basic validation run.  This is a *simulated* test — it validates
    that the skill file is well-formed and logs what would happen.

    Parameters
    ----------
    name : str
        Name of the skill to test.
    test_input : str
        Optional test input string to simulate passing to the skill.

    Returns
    -------
    dict[str, Any]
        Test result with ``success``, ``skill``, ``test_input``,
        ``execution_log``, and any errors encountered.
    """
    detail = get_skill_detail(name)
    content = detail.get("content", "")

    # Simulated validation
    issues: list[str] = []

    # Check for required sections
    if "# " not in content:
        issues.append("Missing top-level heading (# Title)")
    if "## Description" not in content:
        issues.append("Missing '## Description' section")
    if "## Usage" not in content:
        issues.append("Missing '## Usage' section")

    # Check for basic structure
    lines = content.split("\n")
    if len(lines) < 10:
        issues.append("SKILL.md is very short (< 10 lines)")

    # Build execution log
    exec_log = [
        f"[LOAD]  Loading skill '{name}'...",
        f"[PARSE] Parsing SKILL.md ({len(content)} bytes, {len(lines)} lines)...",
    ]
    if issues:
        exec_log.append(f"[WARN]  Validation found {len(issues)} issue(s):")
        for issue in issues:
            exec_log.append(f"        - {issue}")
    else:
        exec_log.append("[PASS]  Validation passed — all required sections present.")
        exec_log.append("[READY] Skill is syntactically well-formed.")

    if test_input:
        exec_log.append(f"[INPUT] Received test input ({len(test_input)} chars).")
        exec_log.append(f"[EXEC]  Simulated execution with input: {test_input[:100]}...")
        exec_log.append("[DONE]  Execution completed (simulated — no real side effects).")
    else:
        exec_log.append("[INFO]  No test input provided; skip execution simulation.")
        exec_log.append("[DONE]  Dry-run completed.")

    return {
        "success": len(issues) == 0,
        "skill": name,
        "category": detail.get("category", ""),
        "path": detail.get("path", ""),
        "test_input": test_input,
        "execution_log": exec_log,
        "warnings": issues,
        "errors": [] if len(issues) == 0 else issues,
    }


def publish_skill(name: str) -> dict[str, Any]:
    """Publish a skill by marking it as ready.

    Creates a ``.published`` marker file in the skill directory and
    calls ``skill_manage(action='publish', ...)``.

    Parameters
    ----------
    name : str
        Name of the skill to publish.

    Returns
    -------
    dict[str, Any]
        Result with ``success``, ``name``, ``is_published``, and
        ``skill_manage_result``.

    Raises
    ------
    FileNotFoundError
        If the skill is not found.
    """
    detail = get_skill_detail(name)
    skill_dir = Path(detail["path"]).parent
    marker = skill_dir / PUBLISHED_MARKER

    # Create marker file
    try:
        marker.write_text(
            f"Published: {_get_iso_now()}\n", encoding="utf-8"
        )
        logger.info("Published skill '%s' (marker: %s)", name, marker)
    except OSError as exc:
        raise OSError(f"Failed to create publish marker for '{name}': {exc}")

    # Call skill_manage
    manage_result = _call_skill_manage(
        action="publish",
        name=name,
        category=detail.get("category", DEFAULT_CATEGORY),
    )

    return {
        "success": True,
        "name": name,
        "category": detail.get("category", DEFAULT_CATEGORY),
        "is_published": True,
        "path": str(marker),
        "skill_manage_result": manage_result,
    }


def get_skill_templates() -> list[dict[str, Any]]:
    """Return the list of available skill templates.

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`SkillTemplate` dictionaries.
    """
    return [t.to_dict() for t in _BUILTIN_TEMPLATES]


def create_from_template(
    name: str,
    template_id: str,
    description: str = "",
    category: str = "",
    extra_context: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a new skill from a pre-defined template.

    Parameters
    ----------
    name : str
        Name for the new skill.
    template_id : str
        Template identifier (e.g. ``\"basic-skill\"``, ``\"data-pipeline\"``,
        ``\"api-integration\"``).
    description : str
        Optional description for the skill (overrides template defaults).
    category : str
        Optional category (overrides template defaults).
    extra_context : dict[str, str] or None
        Additional substitution variables for the template content.

    Returns
    -------
    dict[str, Any]
        Result from :func:`create_skill`.

    Raises
    ------
    ValueError
        If the template ID is not found.
    """
    template = next(
        (t for t in _BUILTIN_TEMPLATES if t.name == template_id),
        None,
    )
    if template is None:
        raise ValueError(
            f"Template '{template_id}' not found. "
            f"Available templates: {[t.name for t in _BUILTIN_TEMPLATES]}"
        )

    resolved_category = category if category else template.category
    resolved_description = description if description else template.description

    # Build substitution context
    context: dict[str, str] = {
        "name": name,
        "name_upper": name.upper().replace("-", "_"),
        "category": resolved_category,
        "description": resolved_description,
        "extension": "csv",
        "api_url": "https://api.example.com/v1/endpoint",
    }
    if extra_context:
        context.update(extra_context)

    content = template.template_content.format(**context)

    return create_skill(
        name=name,
        description=resolved_description,
        category=resolved_category,
        content=content,
    )
