"""
Pydantic Request Models — typed request schemas for all POST / PUT endpoints.

Each model replaces a ``body: dict`` parameter with a validated Pydantic v2 model,
providing automatic documentation, type-safety, and validation without altering
the downstream service logic.

Import these in routers and use them as the request body type:

.. code-block:: python

    from models.request import CreateSkillRequest
    from fastapi import Depends
    from security import require_api_key

    @router.post("/api/skills")
    async def create_skill(
        body: CreateSkillRequest,
        _auth: None = Depends(require_api_key),
    ):
        ...
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════
# Profiles
# ═══════════════════════════════════════════════════════════════════════


class CreateProfileRequest(BaseModel):
    """Request body for ``POST /api/profiles``."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="New profile name (lowercase, alphanumeric, hyphens/underscores)",
    )
    clone_from: str | None = Field(
        None,
        description="Optional source profile to clone config from",
    )


# ═══════════════════════════════════════════════════════════════════════
# Kanban
# ═══════════════════════════════════════════════════════════════════════


class UpdateBoardItemRequest(BaseModel):
    """Request body for ``PUT /api/kanban/{project}``."""

    status: str | None = Field(None, description="Project status")
    description: str | None = Field(None, description="Project description")
    progress_pct: int | None = Field(
        None, ge=0, le=100, description="Progress percentage (0-100)"
    )
    team_members: list[str] | None = Field(None, description="Team member names")
    block_reason: str | None = Field(None, description="Reason the project is blocked")
    priority: str | None = Field(None, description="Priority level")


class RegisterBoardItemRequest(BaseModel):
    """Request body for ``POST /api/kanban``."""

    project_name: str = Field(
        ...,
        min_length=1,
        description="Unique project name (matches a profile directory name)",
    )
    status: str | None = "backlog"
    description: str | None = None
    team_members: list[str] | None = None
    progress_pct: int | None = Field(None, ge=0, le=100)


# ═══════════════════════════════════════════════════════════════════════
# Joint Operations
# ═══════════════════════════════════════════════════════════════════════


class OperationStage(BaseModel):
    """A single stage in a joint operation."""

    profile_name: str = Field(..., min_length=1, description="Profile to execute")
    goal: str = Field(..., min_length=1, description="Goal for this stage")


class CreateOperationRequest(BaseModel):
    """Request body for ``POST /api/joint-ops``."""

    name: str = Field(..., min_length=1, description="Operation name")
    description: str = Field("", description="Operation description")
    stages: list[OperationStage] = Field(
        ..., min_length=1, description="At least one stage required"
    )

    @field_validator("stages")
    @classmethod
    def _validate_stages(cls, v: list[OperationStage]) -> list[OperationStage]:
        if not v:
            raise ValueError("At least one stage is required")
        for i, stage in enumerate(v):
            if not stage.profile_name or not stage.goal:
                raise ValueError(f"Stage {i + 1} requires both 'profile_name' and 'goal'")
        return v


class SaveTemplateRequest(BaseModel):
    """Request body for ``POST /api/joint-ops/templates``."""

    name: str = Field(..., min_length=1, description="Template name")
    description: str = Field("", description="Template description")
    stages: list[OperationStage] = Field(
        ..., min_length=1, description="At least one stage required"
    )


# ═══════════════════════════════════════════════════════════════════════
# Memory Replay
# ═══════════════════════════════════════════════════════════════════════


class CompareTimeframesRequest(BaseModel):
    """Request body for ``POST /api/replay/{profile}/compare``."""

    ts_a: str = Field(..., description="ISO-8601 timestamp (before)")
    ts_b: str = Field(..., description="ISO-8601 timestamp (after)")


# ═══════════════════════════════════════════════════════════════════════
# Skill Studio
# ═══════════════════════════════════════════════════════════════════════


class CreateSkillRequest(BaseModel):
    """Request body for ``POST /api/skills``."""

    name: str = Field(..., min_length=1, description="Skill name")
    description: str = Field(..., min_length=1, description="Short description")
    category: str = Field("general", description="Skill category")
    content: str | None = Field(None, description="SKILL.md content (template if empty)")


class CreateSkillFromTemplateRequest(BaseModel):
    """Request body for ``POST /api/skills/from-template``."""

    name: str = Field(..., min_length=1, description="Skill name")
    template_id: str = Field(..., min_length=1, description="Template identifier")
    description: str = Field("", description="Override template description")
    category: str = Field("", description="Override template category")
    extra_context: dict[str, Any] | None = Field(
        None, description="Additional template variables"
    )


class EditSkillRequest(BaseModel):
    """Request body for ``PUT /api/skills/{name}``."""

    content: str = Field(..., min_length=1, description="Full new SKILL.md content")


class TestSkillRequest(BaseModel):
    """Request body for ``POST /api/skills/{name}/test``."""

    test_input: str = Field("", description="Optional test input to simulate execution")


# ═══════════════════════════════════════════════════════════════════════
# Soul Diff
# ═══════════════════════════════════════════════════════════════════════


class MergeSoulRequest(BaseModel):
    """Request body for ``POST /api/soul/merge``."""

    target: str = Field(..., min_length=1, description="Profile receiving the merged data")
    source: str = Field(..., min_length=1, description="Profile providing the data")
    fields: list[str] = Field(
        ...,
        min_length=1,
        description="SOUL fields to merge (e.g. identity, capabilities, mental_models)",
    )

    VALID_FIELDS: set[str] = {
        "identity",
        "mental_models",
        "capabilities",
        "personality",
        "mandates",
        "awakening_marks",
        "emotional_anchors",
    }

    @field_validator("fields")
    @classmethod
    def _validate_fields(cls, v: list[str]) -> list[str]:
        invalid = [f for f in v if f not in cls.VALID_FIELDS]
        if invalid:
            raise ValueError(
                f"Invalid field(s): {', '.join(invalid)}. "
                f"Valid: {', '.join(sorted(cls.VALID_FIELDS))}"
            )
        return v


# ═══════════════════════════════════════════════════════════════════════
# Profile Soul / Memory
# ═══════════════════════════════════════════════════════════════════════


class AddEvolutionRequest(BaseModel):
    """Request body for ``POST /api/profiles/{name}/soul/evolve``."""

    type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Evolution type (e.g. awakening, merge, insight, skill_acquired)",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Human-readable description of the evolution event",
    )
    details: dict[str, Any] | None = Field(
        None,
        description="Optional structured details attached to this entry",
    )


class SetEnabledSkillsRequest(BaseModel):
    """Request body for ``PUT /api/profiles/{name}/skills/enabled``."""

    skill_names: list[str] = Field(
        ...,
        min_length=0,
        description="List of skill names to enable for this profile",
    )


# ═══════════════════════════════════════════════════════════════════════
# Palace — 记忆宫殿查询/归档
# ═══════════════════════════════════════════════════════════════════════


class ArchiveCodeRequest(BaseModel):
    """Request body for ``POST /api/palace/archive/code``."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Code asset name (used as directory name in 代码资产库)",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Code content to archive",
    )
    description: str | None = Field(
        None,
        max_length=1024,
        description="Optional description / README content",
    )
    language: str | None = Field(
        None,
        max_length=64,
        description="Programming language (e.g. python, typescript)",
    )
    tags: list[str] | None = Field(
        None,
        description="Optional tags for categorization",
    )


class ArchiveModelRequest(BaseModel):
    """Request body for ``POST /api/palace/archive/model``."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Mental model name",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Description of the mental model",
    )
    applicable_scenarios: str | None = Field(
        None,
        max_length=4096,
        description="Applicable scenarios for this mental model",
    )
    content: str | None = Field(
        None,
        description="Full mental model content / markdown body",
    )
    tags: list[str] | None = Field(
        None,
        description="Optional tags for categorization",
    )


# ═══════════════════════════════════════════════════════════════════════
# Legion — 员工注册/任务分配
# ═══════════════════════════════════════════════════════════════════════


class RegisterEmployeeRequest(BaseModel):
    """Request body for ``POST /api/legion/employees``."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\u4e00-\u9fff]+$",
        description="员工名称（支持中文、英文、数字、下划线、连字符）",
    )
    role: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="员工角色（如 engineer, analyst, designer）",
    )
    skill_tags: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="技能标签列表（如 [\"python\", \"fastapi\", \"nlp\"]）",
    )
    personality: str | None = Field(
        None,
        max_length=512,
        description="人格特征描述（可选）",
    )

    @field_validator("skill_tags")
    @classmethod
    def _validate_skill_tags(
        cls, v: list[str]
    ) -> list[str]:
        if not v:
            raise ValueError("至少需要一个技能标签")
        cleaned = []
        for tag in v:
            t = tag.strip().lower()
            if t:
                cleaned.append(t)
        return cleaned


class AssignTaskRequest(BaseModel):
    """Request body for ``POST /api/legion/employees/{name}/assign``."""

    task: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="任务描述",
    )
    priority: int = Field(
        default=3,
        ge=1,
        le=5,
        description="任务优先级（1 最低 ~ 5 最高，默认 3）",
    )
    deadline: str | None = Field(
        None,
        description="截止时间（ISO-8601 格式，可选，如 2026-06-15T18:00:00）",
    )


class ArchiveAdrRequest(BaseModel):
    """Request body for ``POST /api/palace/archive/adr``."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="ADR title (e.g. '选型FastAPI-React')",
    )
    status: str = Field(
        "proposed",
        description="ADR status: proposed / accepted / deprecated / superseded",
    )
    context: str = Field(
        ...,
        min_length=1,
        description="Decision context / problem statement",
    )
    decision: str = Field(
        ...,
        min_length=1,
        description="The decision made",
    )
    consequences: str | None = Field(
        None,
        description="Consequences of the decision",
    )
    alternatives: list[str] | None = Field(
        None,
        description="Alternative options considered",
    )
