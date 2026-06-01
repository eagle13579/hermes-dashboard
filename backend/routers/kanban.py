"""
Kanban Router — REST API for the Hermes dashboard project board.

Endpoints
---------
========================  =====  ========================================
Path                      Method  Description
========================  =====  ========================================
/api/kanban                GET    List all board entries
/api/kanban/stats          GET    Aggregate board statistics
/api/kanban/{project}      GET    Single project board detail
/api/kanban/{project}      PUT    Update a project's board entry
/api/kanban                POST   Register a new project on the board
/api/kanban/refresh        POST   Trigger a manual full refresh
========================  =====  ========================================
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from models.request import RegisterBoardItemRequest, UpdateBoardItemRequest
from security.auth import require_api_key
from services.kanban_manager import KanbanManager, BoardItem

logger = logging.getLogger(__name__)

router: APIRouter = APIRouter(prefix="/api/kanban", tags=["Kanban"])


# ──────────────────────────────────────────────────────────────────────
# GET  /api/kanban — list all
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_boards() -> list[dict[str, Any]]:
    """Return every project currently tracked on the Kanban board.

    Entries are sorted alphabetically by project name.  Each entry
    includes the project name, status, description, team members,
    progress percentage, last-updated timestamp, and block reason.

    Returns
    -------
    list[dict[str, Any]]
        List of board item dictionaries.
    """
    try:
        boards: list[BoardItem] = KanbanManager.get_all_boards()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load board data: {exc}",
        )
    return [item.to_dict() for item in boards]


# ──────────────────────────────────────────────────────────────────────
# GET  /api/kanban/stats — statistics
# ──────────────────────────────────────────────────────────────────────


@router.get("/stats")
async def get_board_stats() -> dict[str, Any]:
    """Return aggregate statistics for the Kanban board.

    Provides total project count, a breakdown by status, average
    progress percentage, and the timestamp of the stats computation.

    Returns
    -------
    dict[str, Any]
        Statistics dictionary (see :meth:`KanbanManager.get_stats`).
    """
    try:
        stats = KanbanManager.get_stats()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute stats: {exc}",
        )
    return stats


# ──────────────────────────────────────────────────────────────────────
# GET  /api/kanban/{project} — single
# ──────────────────────────────────────────────────────────────────────


@router.get("/{project}")
async def get_board_item(project: str) -> dict[str, Any]:
    """Return the Kanban board entry for a single project.

    Parameters
    ----------
    project : str
        Project (profile) name.

    Returns
    -------
    dict[str, Any]
        Board item dictionary.

    Raises
    ------
    404
        If the project is not registered on the board.
    """
    try:
        item: BoardItem = KanbanManager.get_board(project)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read board data: {exc}",
        )
    return item.to_dict()


# ──────────────────────────────────────────────────────────────────────
# PUT  /api/kanban/{project} — update
# ──────────────────────────────────────────────────────────────────────


@router.put("/{project}")
async def update_board_item(
    project: str,
    data: UpdateBoardItemRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Update an existing project's Kanban board entry.

    Only the keys provided in the request body are updated; omitted
    fields retain their current values.  The ``last_updated`` timestamp
    is always refreshed.

    Example request body::

        {
            "status": "in_progress",
            "progress_pct": 45,
            "team_members": ["Alice", "Bob"]
        }

    Parameters
    ----------
    project : str
        Project name to update.
    data : UpdateBoardItemRequest
        JSON body with fields to update (see :class:`BoardItem`).

    Returns
    -------
    dict[str, Any]
        The updated board item dictionary.

    Raises
    ------
    404
        If the project is not found.
    422
        If the data contains invalid values (e.g. bad status).
    """
    # Convert to dict, dropping None values (fields not provided)
    update_data = data.model_dump(exclude_none=True)
    try:
        updated: BoardItem = KanbanManager.update_board(project, update_data)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist update: {exc}",
        )
    return updated.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/kanban — register new
# ──────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def register_board_item(
    body: RegisterBoardItemRequest,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Register a new project on the Kanban board.

    If an optional JSON body is provided, its keys are used to initialise
    the board entry (e.g. ``status``, ``description``, ``team_members``).
    Otherwise sensible defaults are applied.

    Parameters
    ----------
    body : RegisterBoardItemRequest
        Project registration payload.

    Returns
    -------
    dict[str, Any]
        The newly created board item dictionary.

    Raises
    ------
    409
        If the project is already registered.
    422
        If the data contains invalid values.
    """
    # Build initial data dict from body (exclude project_name)
    init_data = body.model_dump(exclude={"project_name"}, exclude_none=True)
    try:
        item: BoardItem = KanbanManager.add_board(body.project_name, init_data)
    except ValueError as exc:
        # "already registered" → 409, invalid values → 422
        if "already registered" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist board entry: {exc}",
        )
    return item.to_dict()


# ──────────────────────────────────────────────────────────────────────
# POST  /api/kanban/refresh — manual refresh
# ──────────────────────────────────────────────────────────────────────


@router.post("/refresh")
async def refresh_board(
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Trigger a manual full refresh of the Kanban board.

    Scans all profile directories under ``$HERMES_HOME/profiles/``,
    updates statuses and descriptions based on heuristics, recalculates
    progress, and archives stale done entries.

    Returns
    -------
    dict[str, Any]
        Summary of the refresh operation (see :meth:`KanbanManager.auto_refresh`).
    """
    try:
        summary = KanbanManager.auto_refresh()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Refresh failed: {exc}",
        )
    return summary


# ──────────────────────────────────────────────────────────────────────
# Auto-Rule CRUD
# ──────────────────────────────────────────────────────────────────────


from services.kanban_manager import (
    AutoRule,
    create_rule,
    list_rules,
    get_rule,
    update_rule,
    delete_rule,
    auto_apply_rules,
)


@router.get("/rules")
async def list_all_rules() -> list[dict]:
    """Return all auto-rules.

    Returns
    -------
    list[dict]
        List of rule dictionaries (id, name, trigger_event, condition,
        action, enabled).
    """
    return [r.to_dict() for r in list_rules()]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_new_rule(body: dict) -> dict:
    """Create a new auto-rule.

    Example body::

        {
            "name": "Auto-review completed tasks",
            "trigger_event": "task_moved",
            "condition": "status == done",
            "action": "move_to(review)",
            "enabled": true
        }

    Returns
    -------
    dict
        The created rule with its assigned ``id``.
    """
    try:
        rule = AutoRule(
            name=body["name"],
            trigger_event=body["trigger_event"],
            condition=body.get("condition", ""),
            action=body["action"],
            enabled=body.get("enabled", True),
        )
        created = create_rule(rule)
        return created.to_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.put("/rules/{rule_id}")
async def update_existing_rule(rule_id: int, body: dict) -> dict:
    """Update an existing auto-rule by id.

    Only the keys provided in the request body are updated.
    """
    updated = update_rule(rule_id, body)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule #{rule_id} not found",
        )
    return updated.to_dict()


@router.delete("/rules/{rule_id}")
async def delete_existing_rule(rule_id: int) -> dict:
    """Delete an auto-rule by id."""
    deleted = delete_rule(rule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule #{rule_id} not found",
        )
    return {"deleted": True, "id": rule_id}


# ──────────────────────────────────────────────────────────────────────
# PUT  /api/kanban/{project}/move — move task with auto-rule trigger
# ──────────────────────────────────────────────────────────────────────


@router.put("/{project}/move")
async def move_board_item(
    project: str,
    body: dict,
    _auth: None = Depends(require_api_key),
) -> dict[str, Any]:
    """Move a task to a new status, triggering auto-rule evaluation.

    When a task is dragged to a new column, this endpoint updates the
    status and automatically evaluates all enabled ``task_moved`` rules.

    Example body::

        {"status": "in_progress"}

    Returns
    -------
    dict
        Updated board item with ``_rules_triggered`` metadata.
    """
    update_data = body.copy()
    try:
        item: BoardItem = KanbanManager.get_board(project)
        old_status = item.status
        updated: BoardItem = KanbanManager.update_board(project, update_data)

        # Auto-apply rules on task_moved event
        rules_results = auto_apply_rules("task_moved", updated)

        result = updated.to_dict()
        if rules_results:
            result["_rules_triggered"] = rules_results
        logger.info("Moved '%s': %s -> %s (rules fired: %d)",
                     project, old_status, updated.status, len(rules_results))
        return result
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to move task: {exc}",
        )
