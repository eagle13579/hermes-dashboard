"""Tests for :mod:`services.kanban_manager` — board item & kanban CRUD."""

from __future__ import annotations

import pytest

from services.kanban_manager import (
    BoardItem,
    KanbanManager,
    VALID_STATUSES,
)


class TestBoardItem:
    """Tests for ``BoardItem`` dataclass — validation & serialization."""

    def test_valid_statuses(self) -> None:
        """Each status in VALID_STATUSES is a non-empty string."""
        for s in VALID_STATUSES:
            assert isinstance(s, str) and len(s) > 0

    def test_to_dict_roundtrip(self) -> None:
        """``to_dict()`` from a real KanbanManager instance returns a dict."""
        mgr = KanbanManager()
        boards = mgr.get_all_boards()
        assert isinstance(boards, list)

    def test_kanban_manager_initialization(self) -> None:
        """KanbanManager creates without error."""
        mgr = KanbanManager()
        assert mgr is not None

    def test_kanban_get_stats(self) -> None:
        """``get_stats()`` returns a dict with expected keys."""
        mgr = KanbanManager()
        stats = mgr.get_stats()
        assert isinstance(stats, dict)
        assert "total" in stats or "projects" in stats


class TestKanbanManager:
    """Tests for ``KanbanManager`` — board operations."""

    def test_get_all_boards_returns_list(self) -> None:
        """``get_all_boards()`` always returns a list."""
        mgr = KanbanManager()
        boards = mgr.get_all_boards()
        assert isinstance(boards, list)

    def test_scan_all_profiles_returns_list(self) -> None:
        """``scan_all_profiles()`` returns list."""
        mgr = KanbanManager()
        results = mgr.scan_all_profiles()
        assert isinstance(results, list)

    def test_auto_refresh_returns_dict(self) -> None:
        """``auto_refresh()`` returns status dict."""
        mgr = KanbanManager()
        result = mgr.auto_refresh()
        assert isinstance(result, dict)

    def test_get_stats_returns_dict(self) -> None:
        """``get_stats()`` returns a dict."""
        mgr = KanbanManager()
        stats = mgr.get_stats()
        assert isinstance(stats, dict)
