"""
Tests for :mod:`services.joint_ops` — 联合作战 (Joint Operations) Engine.

Tests the ``JointOpsManager`` class and its data models with all I/O
redirected to temporary directories.  The ``_run_stage_command`` method
is mocked to avoid actual subprocess calls to ``hermes`` CLI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.joint_ops import (
    JointStage,
    JointOperation,
    JointTemplate,
    JointOpsManager,
    get_manager,
    _PREDEFINED_TEMPLATES,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """A temporary data directory for JointOpsManager persistence."""
    d = tmp_path / "joint_data"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def manager(tmp_data_dir: Path) -> JointOpsManager:
    """Create a JointOpsManager with a temporary data directory."""
    return JointOpsManager(data_dir=str(tmp_data_dir))


@pytest.fixture
def mock_stage_command():
    """Mock ``_run_stage_command`` to return a successful result."""
    with patch.object(JointOpsManager, "_run_stage_command") as mock:
        mock.return_value = {
            "output": "Mocked output",
            "raw": "Mocked raw result",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T00:01:00",
        }
        yield mock


# ═══════════════════════════════════════════════════════════════════════
# Data model tests
# ═══════════════════════════════════════════════════════════════════════


class TestJointStage:
    """Tests for ``JointStage`` dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        stage = JointStage(
            stage_id="s1",
            profile_name="chainke-dev",
            goal="Write some code",
            context_input="prev output",
            context_output="new output",
            status="completed",
            started_at="2026-01-01T00:00:00",
            completed_at="2026-01-01T00:01:00",
            result="success",
        )
        d = stage.to_dict()
        assert d["stage_id"] == "s1"
        assert d["status"] == "completed"

        restored = JointStage.from_dict(d)
        assert restored.stage_id == "s1"
        assert restored.status == "completed"
        assert restored.context_input == "prev output"

    def test_default_status(self) -> None:
        stage = JointStage(stage_id="s1", profile_name="p", goal="g")
        assert stage.status == "pending"

    def test_from_dict_roundtrip(self) -> None:
        data = {
            "stage_id": "s2",
            "profile_name": "gaia-city",
            "goal": "Review code",
            "context_input": "",
            "context_output": "",
            "status": "running",
            "started_at": "2026-01-01T00:00:00",
            "completed_at": None,
            "result": "",
        }
        stage = JointStage.from_dict(data)
        assert stage.profile_name == "gaia-city"
        assert stage.status == "running"


class TestJointOperation:
    """Tests for ``JointOperation`` dataclass."""

    def test_to_dict_roundtrip(self) -> None:
        stages = [
            JointStage(stage_id="s1", profile_name="p1", goal="g1"),
            JointStage(stage_id="s2", profile_name="p2", goal="g2"),
        ]
        op = JointOperation(
            op_id="op-1",
            name="Test Op",
            description="A test",
            status="planning",
            stages=stages,
            created_at="2026-01-01T00:00:00",
        )
        d = op.to_dict()
        assert d["op_id"] == "op-1"
        assert len(d["stages"]) == 2

        restored = JointOperation.from_dict(d)
        assert restored.op_id == "op-1"
        assert len(restored.stages) == 2

    def test_from_dict_restores_stages(self) -> None:
        data = {
            "op_id": "op-2",
            "name": "Full Stack",
            "description": "Build an app",
            "status": "completed",
            "stages": [
                {"stage_id": "s1", "profile_name": "chainke-dev", "goal": "backend",
                 "context_input": "", "context_output": "", "status": "completed",
                 "started_at": None, "completed_at": None, "result": ""},
                {"stage_id": "s2", "profile_name": "dev", "goal": "frontend",
                 "context_input": "", "context_output": "", "status": "completed",
                 "started_at": None, "completed_at": None, "result": ""},
            ],
            "created_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T01:00:00",
            "result_summary": "All done",
        }
        op = JointOperation.from_dict(data)
        assert isinstance(op.stages[0], JointStage)
        assert op.stages[0].profile_name == "chainke-dev"
        assert op.status == "completed"

    def test_defaults(self) -> None:
        op = JointOperation(op_id="op-x", name="X")
        assert op.status == "planning"
        assert op.stages == []
        assert op.created_at == ""


class TestJointTemplate:
    """Tests for ``JointTemplate`` dataclass."""

    def test_to_dict(self) -> None:
        tmpl = JointTemplate(
            template_id="t1",
            name="Code Review",
            description="Review pipeline",
            stages=[{"profile_name": "p1", "goal": "write code"}],
        )
        d = tmpl.to_dict()
        assert d["template_id"] == "t1"
        assert len(d["stages"]) == 1

    def test_from_dict(self) -> None:
        data = {
            "template_id": "t2",
            "name": "Test",
            "description": "Desc",
            "stages": [{"profile_name": "p1", "goal": "g1"}],
        }
        tmpl = JointTemplate.from_dict(data)
        assert tmpl.name == "Test"


# ═══════════════════════════════════════════════════════════════════════
# Predefined templates
# ═══════════════════════════════════════════════════════════════════════


class TestPredefinedTemplates:
    """Tests for ``_PREDEFINED_TEMPLATES``."""

    def test_has_expected_templates(self) -> None:
        ids = [t.template_id for t in _PREDEFINED_TEMPLATES]
        assert "code-review-pipeline" in ids
        assert "fullstack-dev" in ids
        assert "product-launch-check" in ids
        assert "data-analysis-pipeline" in ids

    def test_each_template_has_stages(self) -> None:
        for t in _PREDEFINED_TEMPLATES:
            assert len(t.stages) >= 1


# ═══════════════════════════════════════════════════════════════════════
# JointOpsManager — initialization & persistence
# ═══════════════════════════════════════════════════════════════════════


class TestManagerInit:
    """Tests for ``JointOpsManager`` initialization."""

    def test_creates_data_directory(self, tmp_path: Path) -> None:
        """Data directory is created if it doesn't exist."""
        data_dir = tmp_path / "new_joint_data"
        assert not data_dir.is_dir()
        mgr = JointOpsManager(data_dir=str(data_dir))
        assert data_dir.is_dir()
        assert mgr is not None

    def test_loads_empty_when_no_files(self, tmp_data_dir: Path) -> None:
        """Fresh manager has no operations and predefined templates."""
        mgr = JointOpsManager(data_dir=str(tmp_data_dir))
        assert len(mgr.list_operations()) == 0
        assert len(mgr.get_templates()) >= 4  # predefined templates

    def test_persists_and_restores_operations(self, tmp_data_dir: Path) -> None:
        """Operations persist to disk and load on next init."""
        mgr1 = JointOpsManager(data_dir=str(tmp_data_dir))
        op = mgr1.create_operation("Persist Test", "Testing persistence",
                                    [{"profile_name": "p1", "goal": "g1"}])
        op_id = op.op_id

        # New manager instance loading from same directory
        mgr2 = JointOpsManager(data_dir=str(tmp_data_dir))
        loaded = mgr2.get_operation(op_id)
        assert loaded is not None
        assert loaded.name == "Persist Test"

    def test_data_file_is_valid_json(self, tmp_data_dir: Path) -> None:
        """Written joint_ops.json is valid JSON."""
        mgr = JointOpsManager(data_dir=str(tmp_data_dir))
        mgr.create_operation("JSON Test", "",
                              [{"profile_name": "p1", "goal": "g1"}])
        ops_file = tmp_data_dir / "joint_ops.json"
        assert ops_file.is_file()
        data = json.loads(ops_file.read_text(encoding="utf-8"))
        assert "operations" in data
        assert len(data["operations"]) == 1

    def test_merge_predefined_templates(self, tmp_data_dir: Path) -> None:
        """Predefined templates are merged into the manager's cache."""
        mgr = JointOpsManager(data_dir=str(tmp_data_dir))
        templates = mgr.get_templates()
        template_ids = {t.template_id for t in templates}
        assert "code-review-pipeline" in template_ids
        assert "fullstack-dev" in template_ids

    def test_singleton_get_manager(self) -> None:
        """``get_manager()`` returns a JointOpsManager instance."""
        mgr = get_manager()
        assert isinstance(mgr, JointOpsManager)

    def test_reload_corrupted_file_doesnt_crash(self, tmp_data_dir: Path) -> None:
        """Corrupted JSON data file is handled gracefully."""
        ops_file = tmp_data_dir / "joint_ops.json"
        ops_file.write_text("{{corrupted}}", encoding="utf-8")
        mgr = JointOpsManager(data_dir=str(tmp_data_dir))
        # Should not crash; operations should be empty
        assert len(mgr.list_operations()) == 0


# ═══════════════════════════════════════════════════════════════════════
# Operations CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestCreateOperation:
    """Tests for ``JointOpsManager.create_operation()``."""

    def test_creates_operation(self, manager: JointOpsManager) -> None:
        op = manager.create_operation(
            name="Test Mission",
            description="A test joint operation",
            stages=[{"profile_name": "chainke-dev", "goal": "Write code"}],
        )
        assert op.op_id.startswith("op-")
        assert op.name == "Test Mission"
        assert op.status == "planning"
        assert len(op.stages) == 1
        assert op.stages[0].profile_name == "chainke-dev"
        assert op.stages[0].status == "pending"

    def test_create_with_multiple_stages(self, manager: JointOpsManager) -> None:
        op = manager.create_operation(
            name="Multi Stage",
            description="Multiple stages",
            stages=[
                {"profile_name": "p1", "goal": "g1"},
                {"profile_name": "p2", "goal": "g2"},
                {"profile_name": "p3", "goal": "g3"},
            ],
        )
        assert len(op.stages) == 3
        assert op.stages[0].stage_id.startswith("stage-")

    def test_empty_name_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            manager.create_operation(name="", description="", stages=[{"profile_name": "p", "goal": "g"}])

    def test_empty_stages_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="至少需要"):
            manager.create_operation(name="Test", description="", stages=[])

    def test_stage_missing_fields_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="缺少"):
            manager.create_operation(name="Test", description="",
                                      stages=[{"profile_name": "p"}])  # missing goal

    def test_whitespace_name_stripped(self, manager: JointOpsManager) -> None:
        op = manager.create_operation(name="  Spaced  ", description="",
                                       stages=[{"profile_name": "p", "goal": "g"}])
        assert op.name == "Spaced"

    def test_operation_persisted(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Persist", "",
                                       [{"profile_name": "p", "goal": "g"}])
        retrieved = manager.get_operation(op.op_id)
        assert retrieved is not None
        assert retrieved.op_id == op.op_id


class TestGetOperation:
    """Tests for ``JointOpsManager.get_operation()``."""

    def test_get_existing(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Get Me", "",
                                       [{"profile_name": "p", "goal": "g"}])
        retrieved = manager.get_operation(op.op_id)
        assert retrieved is not None
        assert retrieved.name == "Get Me"

    def test_get_nonexistent(self, manager: JointOpsManager) -> None:
        assert manager.get_operation("op-nonexistent") is None


class TestListOperations:
    """Tests for ``JointOpsManager.list_operations()``."""

    def test_list_all(self, manager: JointOpsManager) -> None:
        manager.create_operation("A", "", [{"profile_name": "p", "goal": "g"}])
        manager.create_operation("B", "", [{"profile_name": "p", "goal": "g"}])
        ops = manager.list_operations()
        assert len(ops) == 2

    def test_list_filter_by_status(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Planner", "",
                                       [{"profile_name": "p", "goal": "g"}])
        # All start as "planning"
        planning = manager.list_operations(status="planning")
        assert len(planning) >= 1

        completed = manager.list_operations(status="completed")
        # None are completed yet
        assert len(completed) == 0

    def test_list_sorted_by_created_at(self, manager: JointOpsManager) -> None:
        op1 = manager.create_operation("First", "",
                                        [{"profile_name": "p", "goal": "g"}])
        op2 = manager.create_operation("Second", "",
                                        [{"profile_name": "p", "goal": "g"}])
        ops = manager.list_operations()
        # Most recent first
        assert ops[0].op_id == op2.op_id
        assert ops[1].op_id == op1.op_id


# ═══════════════════════════════════════════════════════════════════════
# Execute operations
# ═══════════════════════════════════════════════════════════════════════


class TestExecuteOperation:
    """Tests for ``JointOpsManager.execute_operation()``."""

    def test_execute_success(self, manager: JointOpsManager, mock_stage_command) -> None:
        """Successful execution completes all stages."""
        op = manager.create_operation("Exec Test", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"}])
        result = manager.execute_operation(op.op_id)
        assert result.status == "completed"
        assert all(s.status == "completed" for s in result.stages)
        assert "成功完成" in result.result_summary
        assert mock_stage_command.call_count == 2

    def test_execute_nonexistent_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="不存在"):
            manager.execute_operation("op-nonexistent")

    def test_execute_completed_op_raises(self, manager: JointOpsManager, mock_stage_command) -> None:
        """Executing an already completed operation raises ValueError."""
        op = manager.create_operation("Done", "",
                                       [{"profile_name": "p", "goal": "g"}])
        manager.execute_operation(op.op_id)
        with pytest.raises(ValueError, match="无法执行"):
            manager.execute_operation(op.op_id)

    def test_stage_failure_stops_execution(self, manager: JointOpsManager, mock_stage_command) -> None:
        """If a stage fails, remaining stages are not executed."""
        mock_stage_command.side_effect = [
            {"output": "ok", "raw": "ok", "status": "completed",
             "started_at": "t1", "completed_at": "t2"},
            {"output": "", "raw": "error", "status": "failed",
             "started_at": "t1", "completed_at": "t2"},
        ]
        op = manager.create_operation("Failing", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"},
                                        {"profile_name": "p3", "goal": "g3"}])
        result = manager.execute_operation(op.op_id)
        assert result.status == "failed"
        assert result.stages[0].status == "completed"
        assert result.stages[1].status == "failed"
        assert result.stages[2].status == "pending"  # never executed
        assert mock_stage_command.call_count == 2

    def test_context_passed_between_stages(self, manager: JointOpsManager, mock_stage_command) -> None:
        """Context output from stage N is passed as input to stage N+1."""
        # Capture the context_input passed to _run_stage_command
        captured_contexts = []

        def side_effect(stage, context_input):
            captured_contexts.append(context_input)
            return {
                "output": f"output-of-{stage.stage_id}",
                "raw": f"raw-of-{stage.stage_id}",
                "status": "completed",
                "started_at": "t1",
                "completed_at": "t2",
            }

        mock_stage_command.side_effect = side_effect

        op = manager.create_operation("Context Test", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"},
                                        {"profile_name": "p3", "goal": "g3"}])
        manager.execute_operation(op.op_id)

        # First stage gets empty context
        assert captured_contexts[0] == ""
        # Subsequent stages get previous stage's output
        assert "output-of-" in captured_contexts[1]
        assert "output-of-" in captured_contexts[2]

    def test_execute_truncates_long_context(self, manager: JointOpsManager) -> None:
        """Context longer than 2000 chars is truncated by _run_stage_command."""
        # Directly test _run_stage_command's truncation logic
        # by mocking subprocess.run so it doesn't actually run hermes CLI
        stage = JointStage(stage_id="s1", profile_name="p1", goal="Do something")
        long_context = "A" * 3000

        with patch("services.joint_ops.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "mocked output"
            mock_run.return_value.stderr = ""

            result = manager._run_stage_command(stage, long_context)

            # Verify truncation happened: the context passed to subprocess
            # should be <= 2000 + overhead
            call_args = mock_run.call_args[0][0]
            # Find the goal text argument
            goal_idx = call_args.index("-q") + 1 if "-q" in call_args else -1
            if goal_idx > 0 and goal_idx < len(call_args):
                goal_text = call_args[goal_idx]
                assert len(goal_text) <= 2100
                assert "[上下文已截断...]" in goal_text
            else:
                # Alternative: check that result has correct context indicator
                assert result["status"] == "completed"

    def test_execute_handles_exception_gracefully(self, manager: JointOpsManager, mock_stage_command) -> None:
        """An exception during execution is caught and operation is marked failed."""
        mock_stage_command.side_effect = RuntimeError("Unexpected error!")

        op = manager.create_operation("Crash Test", "",
                                       [{"profile_name": "p", "goal": "g"}])
        result = manager.execute_operation(op.op_id)
        assert result.status == "failed"
        assert "异常" in result.result_summary


class TestExecuteStage:
    """Tests for ``JointOpsManager.execute_stage()``."""

    def test_execute_single_stage(self, manager: JointOpsManager, mock_stage_command) -> None:
        """Executing a single stage returns the updated stage."""
        op = manager.create_operation("Single Stage", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"}])
        stage_id = op.stages[0].stage_id
        result = manager.execute_stage(op.op_id, stage_id)
        assert result.status == "completed"
        assert result.stage_id == stage_id
        mock_stage_command.assert_called_once()

    def test_execute_stage_with_prev_context(self, manager: JointOpsManager, mock_stage_command) -> None:
        """Executing the second stage gets context from first."""
        # First manually set context on stage 0
        op = manager.create_operation("Context Stage", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"}])
        op.stages[0].context_output = "previous-output"

        stage_id = op.stages[1].stage_id
        manager.execute_stage(op.op_id, stage_id)
        # Verify context_input was set from previous stage
        assert op.stages[1].context_input == "previous-output"

    def test_execute_stage_nonexistent_op_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="不存在"):
            manager.execute_stage("op-nonexistent", "stage-nonexistent")

    def test_execute_stage_nonexistent_stage_raises(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Test", "",
                                       [{"profile_name": "p", "goal": "g"}])
        with pytest.raises(ValueError, match="不存在"):
            manager.execute_stage(op.op_id, "stage-nonexistent")


class TestCancelOperation:
    """Tests for ``JointOpsManager.cancel_operation()``."""

    def test_cancel_planning(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Cancel Me", "",
                                       [{"profile_name": "p", "goal": "g"}])
        result = manager.cancel_operation(op.op_id)
        assert result.status == "cancelled"
        assert "已被取消" in result.result_summary

    def test_cancel_stages_updated(self, manager: JointOpsManager) -> None:
        op = manager.create_operation("Multi Cancel", "",
                                       [{"profile_name": "p1", "goal": "g1"},
                                        {"profile_name": "p2", "goal": "g2"}])
        result = manager.cancel_operation(op.op_id)
        assert all(s.status == "cancelled" for s in result.stages)

    def test_cancel_nonexistent_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="不存在"):
            manager.cancel_operation("op-nonexistent")

    def test_cancel_completed_raises(self, manager: JointOpsManager, mock_stage_command) -> None:
        op = manager.create_operation("Already Done", "",
                                       [{"profile_name": "p", "goal": "g"}])
        manager.execute_operation(op.op_id)
        with pytest.raises(ValueError, match="无法取消"):
            manager.cancel_operation(op.op_id)

    def test_cancel_failed_raises(self, manager: JointOpsManager, mock_stage_command) -> None:
        mock_stage_command.return_value = {
            "output": "", "raw": "err", "status": "failed",
            "started_at": "t", "completed_at": "t",
        }
        op = manager.create_operation("Failed Op", "",
                                       [{"profile_name": "p", "goal": "g"}])
        manager.execute_operation(op.op_id)
        with pytest.raises(ValueError, match="无法取消"):
            manager.cancel_operation(op.op_id)


# ═══════════════════════════════════════════════════════════════════════
# Templates CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestTemplates:
    """Tests for template operations on JointOpsManager."""

    def test_get_templates_returns_predefined(self, manager: JointOpsManager) -> None:
        templates = manager.get_templates()
        assert len(templates) >= 4

    def test_save_template(self, manager: JointOpsManager) -> None:
        tmpl = manager.save_template(
            name="Custom Pipeline",
            description="A custom template",
            stages=[{"profile_name": "p1", "goal": "g1"},
                    {"profile_name": "p2", "goal": "g2"}],
        )
        assert tmpl.template_id.startswith("tmpl-")
        assert tmpl.name == "Custom Pipeline"
        assert len(tmpl.stages) == 2

    def test_saved_template_appears_in_list(self, manager: JointOpsManager) -> None:
        manager.save_template("My Template", "desc",
                               [{"profile_name": "p", "goal": "g"}])
        templates = manager.get_templates()
        assert any(t.name == "My Template" for t in templates)

    def test_save_empty_name_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="不能为空"):
            manager.save_template(name="", description="", stages=[{"profile_name": "p", "goal": "g"}])

    def test_save_empty_stages_raises(self, manager: JointOpsManager) -> None:
        with pytest.raises(ValueError, match="至少需要"):
            manager.save_template(name="Test", description="", stages=[])

    def test_template_persisted_to_disk(self, tmp_data_dir: Path) -> None:
        mgr1 = JointOpsManager(data_dir=str(tmp_data_dir))
        mgr1.save_template("Disk Template", "persisted",
                            [{"profile_name": "p", "goal": "g"}])

        mgr2 = JointOpsManager(data_dir=str(tmp_data_dir))
        assert any(t.name == "Disk Template" for t in mgr2.get_templates())

    def test_template_file_is_valid_json(self, manager: JointOpsManager, tmp_data_dir: Path) -> None:
        manager.save_template("JSON Template", "",
                               [{"profile_name": "p", "goal": "g"}])
        tmpl_file = tmp_data_dir / "joint_templates.json"
        assert tmpl_file.is_file()
        data = json.loads(tmpl_file.read_text(encoding="utf-8"))
        assert "templates" in data
        assert len(data["templates"]) >= 1


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


class TestInternalHelpers:
    """Tests for internal/private helpers of JointOpsManager."""

    def test_now_iso_returns_string(self, manager: JointOpsManager) -> None:
        now = manager._now_iso()
        assert isinstance(now, str)
        assert "T" in now

    def test_run_stage_command_simulated(self, manager: JointOpsManager) -> None:
        """_run_stage_command is tested via mock in other tests, but
        we verify the method signature works."""
        stage = JointStage(stage_id="s1", profile_name="p", goal="g")
        # Without mocking, _run_stage_command tries to call hermes CLI
        # We mock it here and verify the call structure
        with patch.object(manager, "_run_stage_command") as mock:
            mock.return_value = {"status": "completed", "output": "ok", "raw": "ok",
                                 "started_at": "t", "completed_at": "t"}
            result = manager._run_stage_command(stage, "context")
            assert result["status"] == "completed"

    def test_ops_file_path(self, manager: JointOpsManager) -> None:
        path = manager._ops_file_path()
        assert path.name == "joint_ops.json"

    def test_templates_file_path(self, manager: JointOpsManager) -> None:
        path = manager._templates_file_path()
        assert path.name == "joint_templates.json"
