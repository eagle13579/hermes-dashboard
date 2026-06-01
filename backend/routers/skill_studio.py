"""
Skill Studio Router — REST API for the Hermes skill development workbench.

Endpoints
---------
====================================  =====  =====================================
Path                                  Method  Description
====================================  =====  =====================================
/api/skills                            GET    List all registered skills
/api/skills/templates                  GET    List available skill templates
/api/skills/{name}                     GET    Get skill detail (SKILL.md content)
/api/skills                            POST   Create a new skill
/api/skills/{name}                     PUT    Edit an existing skill
/api/skills/{name}                    DELETE  Delete a skill
/api/skills/{name}/test               POST   Test a skill
/api/skills/from-template             POST   Create a skill from a template
====================================  =====  =====================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import (
    CreateSkillFromTemplateRequest,
    CreateSkillRequest,
    EditSkillRequest,
    TestSkillRequest,
)
from security.auth import require_api_key
from services.skill_studio import (
    VALID_CATEGORIES,
    create_from_template,
    create_skill,
    delete_skill,
    edit_skill,
    get_skill_detail,
    get_skill_templates,
    list_skills,
    publish_skill,
    test_skill,
)

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/skills", tags=["Skill Studio"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/skills — list all skills
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_all_skills() -> list[dict[str, Any]]:
    """List all Hermes-registered skills.

    Scans all category directories under ``$HERMES_HOME/skills/`` and
    returns a flat list of skill summaries.

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`SkillInfo` dictionaries.
    """
    try:
        return list_skills()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skills: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# GET  /api/skills/templates — list available templates
# ──────────────────────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates() -> list[dict[str, Any]]:
    """Return the list of available skill templates.

    These are pre-defined SKILL.md skeletons for rapid skill creation.

    Returns
    -------
    list[dict[str, Any]]
        List of :class:`SkillTemplate` dictionaries.
    """
    return get_skill_templates()


# ──────────────────────────────────────────────────────────────────────
# GET  /api/skills/{name} — get skill detail
# ──────────────────────────────────────────────────────────────────────


@router.get("/{name}")
async def skill_detail(name: str) -> dict[str, Any]:
    """Get the full detail of a skill, including its SKILL.md content.

    Searches across all categories for the skill name.

    Parameters
    ----------
    name : str
        Name of the skill to retrieve.

    Returns
    -------
    dict[str, Any]
        Full skill detail with content, metadata, and published status.
    """
    try:
        return get_skill_detail(name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read skill details: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills — create a new skill
# ──────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_skill(
    body: CreateSkillRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Create a new Hermes skill.

    Accepts a JSON body with:

    - ``name`` (str, required): skill name
    - ``description`` (str, required): short description
    - ``category`` (str, optional): skill category (default: ``general``)
    - ``content`` (str, optional): SKILL.md content (default: uses template)

    Parameters
    ----------
    body : CreateSkillRequest
        Skill creation payload.

    Returns
    -------
    dict[str, Any]
        Result with success status, path, and skill_manage response.
    """
    try:
        return create_skill(
            name=body.name,
            description=body.description,
            category=body.category,
            content=body.content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create skill: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/from-template — create from template
# ──────────────────────────────────────────────────────────────────────


@router.post("/from-template", status_code=status.HTTP_201_CREATED)
async def create_from_skill_template(
    body: CreateSkillFromTemplateRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Create a new skill from a pre-defined template.

    Accepts a JSON body with:

    - ``name`` (str, required): skill name
    - ``template_id`` (str, required): template identifier
    - ``description`` (str, optional): override template description
    - ``category`` (str, optional): override template category
    - ``extra_context`` (dict, optional): additional template variables

    Parameters
    ----------
    body : CreateSkillFromTemplateRequest
        Template-based creation payload.

    Returns
    -------
    dict[str, Any]
        Result from :func:`create_skill`.
    """
    try:
        return create_from_template(
            name=body.name,
            template_id=body.template_id,
            description=body.description,
            category=body.category,
            extra_context=body.extra_context,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create skill from template: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# PUT  /api/skills/{name} — edit a skill
# ──────────────────────────────────────────────────────────────────────


@router.put("/{name}")
async def edit_existing_skill(
    name: str,
    body: EditSkillRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Edit an existing skill's SKILL.md content.

    Accepts a JSON body with a ``content`` key containing the full
    new SKILL.md content.

    Parameters
    ----------
    name : str
        Name of the skill to edit.
    body : EditSkillRequest
        Must contain ``content`` (str) with the new SKILL.md content.

    Returns
    -------
    dict[str, Any]
        Result with success status, path, and skill_manage response.
    """
    try:
        return edit_skill(name=name, content=body.content)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to edit skill: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# DELETE  /api/skills/{name} — delete a skill
# ──────────────────────────────────────────────────────────────────────


@router.delete("/{name}")
async def delete_existing_skill(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Delete a skill and all its files.

    Parameters
    ----------
    name : str
        Name of the skill to delete.

    Returns
    -------
    dict[str, Any]
        Result with success status.
    """
    try:
        return delete_skill(name=name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete skill: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/{name}/test — test a skill
# ──────────────────────────────────────────────────────────────────────


@router.post("/{name}/test")
async def test_skill_endpoint(
    name: str,
    body: TestSkillRequest = TestSkillRequest(),
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Test a skill by performing a simulated load-and-execute cycle.

    Validates the SKILL.md structure and reports any issues found.

    Parameters
    ----------
    name : str
        Name of the skill to test.
    body : TestSkillRequest
        Optional test input to simulate execution.

    Returns
    -------
    dict[str, Any]
        Test result with execution log, warnings, and errors.
    """
    try:
        return test_skill(name=name, test_input=body.test_input)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test skill: {exc}",
        )


# ──────────────────────────────────────────────────────────────────────
# POST  /api/skills/{name}/publish — publish a skill
# ──────────────────────────────────────────────────────────────────────


@router.post("/{name}/publish")
async def publish_skill_endpoint(
    name: str,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Publish a skill, marking it as ready for production use.

    Creates a ``.published`` marker file in the skill's directory and
    registers the published status with Hermes.

    Parameters
    ----------
    name : str
        Name of the skill to publish.

    Returns
    -------
    dict[str, Any]
        Result with success status and published state.
    """
    try:
        return publish_skill(name=name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish skill: {exc}",
        )
