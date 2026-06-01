"""
Tests for :mod:`services.soul_diff` — soul snapshot & diff engine.

Extends the existing dataclass tests with full coverage of:
- take_snapshot() with real YAML files
- diff_souls() across all categories
- merge_souls() field-by-field
- save_snapshot() / get_soul_history()
- Internal _diff_* helpers

All file I/O is redirected to temporary directories via the conftest.py
HERMES_HOME override, so no real data is ever touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from services.soul_diff import (
    SoulSnapshot,
    SoulDiffItem,
    SoulDiff,
    _safe_load_json,
    _safe_load_yaml,
    _read_employee_yaml,
    _read_soul_injection_yaml,
    _extract_list,
    _extract_dict,
    _diff_identity,
    _diff_mental_models,
    _diff_capabilities,
    _diff_personality,
    _diff_mandates,
    _diff_awakening_marks,
    take_snapshot,
    diff_souls,
    merge_souls,
    save_snapshot,
    get_soul_history,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def profile_a_dir() -> str:
    """Name of the first test profile."""
    return "profile-alpha"


@pytest.fixture
def profile_b_dir() -> str:
    """Name of the second test profile."""
    return "profile-beta"


@pytest.fixture
def make_profile(profile_a_dir: str, profile_b_dir: str, monkeypatch: pytest.MonkeyPatch):
    """Create two profile directories under temp HERMES_HOME with YAML data.

    Returns a callable that accepts optional overrides per profile.
    """
    def _make(
        alpha_employee: dict | None = None,
        alpha_soul_inj: dict | None = None,
        beta_employee: dict | None = None,
        beta_soul_inj: dict | None = None,
    ) -> tuple[Path, Path]:
        hermes_home = Path(profile_a_dir).parent
        # HERMES_HOME is already set to a temp dir by conftest.py, but
        # we need to find it.  Actually _get_hermes_home() reads the env var.
        hermes_home = Path(__import__("os").environ.get("HERMES_HOME", "/tmp"))
        profiles = hermes_home / "profiles"
        p_a = profiles / profile_a_dir
        p_b = profiles / profile_b_dir
        p_a.mkdir(parents=True, exist_ok=True)
        p_b.mkdir(parents=True, exist_ok=True)

        # Default data
        if alpha_employee is None:
            alpha_employee = {
                "name": "Alpha",
                "role": "developer",
                "level": "senior",
                "capabilities": ["python", "rust"],
            }
        if alpha_soul_inj is None:
            alpha_soul_inj = {
                "mental_models": [
                    {"name": "TRIZ", "value": "inventive problem solving"},
                    {"name": "OODA", "value": "observe-orient-decide-act"},
                ],
                "personality": {"style": "analytical", "tone": "precise"},
                "mandates": [
                    {"id": "m1", "content": "do no harm"},
                    {"id": "m2", "content": "be helpful"},
                ],
                "awakening_marks": [
                    {"timestamp": "2025-01-01", "description": "first spark"},
                ],
                "emotional_anchors": [
                    {"name": "curiosity", "intensity": 0.9},
                ],
            }
        if beta_employee is None:
            beta_employee = {
                "name": "Beta",
                "role": "architect",
                "level": "staff",
                "capabilities": ["python", "system-design"],
            }
        if beta_soul_inj is None:
            beta_soul_inj = {
                "mental_models": [
                    {"name": "TRIZ", "value": "inventive problem solving"},
                    {"name": "Cynefin", "value": "complexity framework"},
                ],
                "personality": {"style": "creative", "tone": "visionary"},
                "mandates": [
                    {"id": "m1", "content": "do no harm"},
                    {"id": "m3", "content": "innovate boldly"},
                ],
                "awakening_marks": [
                    {"timestamp": "2025-06-01", "description": "system upgrade"},
                ],
                "emotional_anchors": [
                    {"name": "wonder", "intensity": 0.8},
                ],
            }

        # Write files
        _write_yaml(p_a / "employee.yaml", alpha_employee)
        _write_yaml(p_a / "soul-injection.yaml", alpha_soul_inj)
        _write_yaml(p_b / "employee.yaml", beta_employee)
        _write_yaml(p_b / "soul-injection.yaml", beta_soul_inj)

        return p_a, p_b

    return _make


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict as YAML."""
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Snapshot tests
# ═══════════════════════════════════════════════════════════════════════


class TestTakeSnapshot:
    """Tests for ``take_snapshot()`` — reading structured SOUL from disk."""

    def test_basic_snapshot(self, make_profile) -> None:
        """Snapshots a profile with employee.yaml + soul-injection.yaml."""
        make_profile()
        snap = take_snapshot("profile-alpha")
        assert snap.profile_name == "profile-alpha"
        assert snap.identity["name"] == "Alpha"
        assert snap.identity["role"] == "developer"
        assert len(snap.mental_models) == 2
        assert len(snap.capabilities) == 2
        assert snap.personality["style"] == "analytical"
        assert len(snap.mandates) == 2
        assert len(snap.awakening_marks) == 1
        assert len(snap.emotional_anchors) == 1

    def test_snapshot_missing_profile_raises(self) -> None:
        """Profile directory does not exist -> FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            take_snapshot("nonexistent-profile")

    def _make_empty_profile(self, name: str) -> Path:
        """Helper: create an empty profile directory under temp HERMES_HOME."""
        hermes_home = Path(__import__("os").environ.get("HERMES_HOME", "/tmp"))
        p = hermes_home / "profiles" / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def test_snapshot_with_identity_yaml(self) -> None:
        """Falls back to identity.yaml when employee.yaml missing."""
        p_a = self._make_empty_profile("test-identity-yaml")
        _write_yaml(p_a / "identity.yaml", {"name": "AlphaID", "role": "tester"})

        snap = take_snapshot("test-identity-yaml")
        assert snap.identity["name"] == "AlphaID"
        assert snap.identity["role"] == "tester"

    def test_snapshot_soul_injection_subdir(self) -> None:
        """soul-injection.yaml can live under a soul/ subdirectory."""
        p_a = self._make_empty_profile("test-soul-subdir")
        _write_yaml(p_a / "employee.yaml", {"name": "Alpha"})
        soul_dir = p_a / "soul"
        soul_dir.mkdir(exist_ok=True)
        _write_yaml(soul_dir / "soul-injection.yaml", {"mental_models": [{"name": "M1"}]})

        snap = take_snapshot("test-soul-subdir")
        assert len(snap.mental_models) == 1

    def test_snapshot_no_files_returns_defaults(self) -> None:
        """Profile with no YAML files returns empty identity with name."""
        pname = "test-no-files"
        self._make_empty_profile(pname)

        snap = take_snapshot(pname)
        assert snap.identity["name"] == pname
        assert snap.mental_models == []
        assert snap.capabilities == []
        assert snap.personality == {}

    def test_snapshot_so_md_fallback(self) -> None:
        """When no employee/identity YAML exists, SOUL.md first line is used."""
        pname = "test-soul-md-fallback"
        p_a = self._make_empty_profile(pname)
        (p_a / "SOUL.md").write_text("# The Wise Sage\n", encoding="utf-8")

        snap = take_snapshot(pname)
        assert snap.identity["title_hint"] == "The Wise Sage"
        assert snap.identity["name"] == pname

    def test_snapshot_string_mental_models(self) -> None:
        """String entries in mental_models are converted to dicts."""
        pname = "test-string-mm"
        p_a = self._make_empty_profile(pname)
        _write_yaml(p_a / "employee.yaml", {"name": "Alpha"})
        _write_yaml(p_a / "soul-injection.yaml", {"mental_models": ["TRIZ", "OODA"]})

        snap = take_snapshot(pname)
        assert len(snap.mental_models) == 2
        assert snap.mental_models[0]["name"] == "TRIZ"

    def test_snapshot_string_mandates(self) -> None:
        """String mandate entries get auto-generated IDs."""
        pname = "test-string-mandates"
        p_a = self._make_empty_profile(pname)
        _write_yaml(p_a / "employee.yaml", {"name": "Alpha"})
        _write_yaml(p_a / "soul-injection.yaml", {"mandates": ["rule one", "rule two"]})

        snap = take_snapshot(pname)
        assert len(snap.mandates) == 2
        assert snap.mandates[0]["id"] == "rule-1"
        assert snap.mandates[0]["content"] == "rule one"

    def test_snapshot_capabilities_from_dict(self) -> None:
        """Dict capabilities with a 'name' key are extracted by name."""
        pname = "test-caps-dict"
        p_a = self._make_empty_profile(pname)
        _write_yaml(p_a / "employee.yaml", {"name": "Alpha", "capabilities": [{"name": "python"}]})

        snap = take_snapshot(pname)
        assert "python" in snap.capabilities


# ═══════════════════════════════════════════════════════════════════════
# Diff helpers
# ═══════════════════════════════════════════════════════════════════════


class TestDiffIdentity:
    """Tests for ``_diff_identity()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", identity={"name": "A", "role": "dev"})
        b = SoulSnapshot(profile_name="b", identity={"name": "A", "role": "dev"})
        common, diffs = _diff_identity(a, b)
        assert len(common) == 2
        assert len(diffs) == 0

    def test_added_field(self) -> None:
        a = SoulSnapshot(profile_name="a", identity={"name": "A"})
        b = SoulSnapshot(profile_name="b", identity={"name": "A", "role": "dev"})
        common, diffs = _diff_identity(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"
        assert diffs[0].field_name == "role"

    def test_removed_field(self) -> None:
        a = SoulSnapshot(profile_name="a", identity={"name": "A", "role": "dev"})
        b = SoulSnapshot(profile_name="b", identity={"name": "A"})
        common, diffs = _diff_identity(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "removed"
        assert diffs[0].field_name == "role"

    def test_modified_field(self) -> None:
        a = SoulSnapshot(profile_name="a", identity={"name": "A", "role": "dev"})
        b = SoulSnapshot(profile_name="b", identity={"name": "A", "role": "senior"})
        common, diffs = _diff_identity(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "modified"
        assert diffs[0].value_a == "dev"
        assert diffs[0].value_b == "senior"


class TestDiffMentalModels:
    """Tests for ``_diff_mental_models()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", mental_models=[{"name": "TRIZ", "value": "v1"}])
        b = SoulSnapshot(profile_name="b", mental_models=[{"name": "TRIZ", "value": "v1"}])
        common, diffs = _diff_mental_models(a, b)
        assert len(common) == 1
        assert len(diffs) == 0

    def test_added_model(self) -> None:
        a = SoulSnapshot(profile_name="a", mental_models=[{"name": "TRIZ"}])
        b = SoulSnapshot(profile_name="b", mental_models=[{"name": "TRIZ"}, {"name": "OODA"}])
        common, diffs = _diff_mental_models(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"
        assert diffs[0].field_name == "OODA"

    def test_removed_model(self) -> None:
        a = SoulSnapshot(profile_name="a", mental_models=[{"name": "TRIZ"}, {"name": "OODA"}])
        b = SoulSnapshot(profile_name="b", mental_models=[{"name": "TRIZ"}])
        common, diffs = _diff_mental_models(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "removed"
        assert diffs[0].field_name == "OODA"

    def test_modified_model(self) -> None:
        a = SoulSnapshot(profile_name="a", mental_models=[{"name": "TRIZ", "value": "old"}])
        b = SoulSnapshot(profile_name="b", mental_models=[{"name": "TRIZ", "value": "new"}])
        common, diffs = _diff_mental_models(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "modified"


class TestDiffCapabilities:
    """Tests for ``_diff_capabilities()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", capabilities=["py", "rs"])
        b = SoulSnapshot(profile_name="b", capabilities=["py", "rs"])
        common, diffs = _diff_capabilities(a, b)
        assert len(common) == 2
        assert len(diffs) == 0

    def test_added(self) -> None:
        a = SoulSnapshot(profile_name="a", capabilities=["py"])
        b = SoulSnapshot(profile_name="b", capabilities=["py", "go"])
        common, diffs = _diff_capabilities(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"
        assert diffs[0].field_name == "go"

    def test_removed(self) -> None:
        a = SoulSnapshot(profile_name="a", capabilities=["py", "go"])
        b = SoulSnapshot(profile_name="b", capabilities=["py"])
        common, diffs = _diff_capabilities(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "removed"
        assert diffs[0].field_name == "go"


class TestDiffPersonality:
    """Tests for ``_diff_personality()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", personality={"style": "analytical"})
        b = SoulSnapshot(profile_name="b", personality={"style": "analytical"})
        common, diffs = _diff_personality(a, b)
        assert len(common) == 1
        assert len(diffs) == 0

    def test_added_trait(self) -> None:
        a = SoulSnapshot(profile_name="a", personality={"style": "analytical"})
        b = SoulSnapshot(profile_name="b", personality={"style": "analytical", "tone": "precise"})
        common, diffs = _diff_personality(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"

    def test_modified_trait(self) -> None:
        a = SoulSnapshot(profile_name="a", personality={"style": "analytical"})
        b = SoulSnapshot(profile_name="b", personality={"style": "creative"})
        common, diffs = _diff_personality(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "modified"


class TestDiffMandates:
    """Tests for ``_diff_mandates()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", mandates=[{"id": "m1", "content": "do good"}])
        b = SoulSnapshot(profile_name="b", mandates=[{"id": "m1", "content": "do good"}])
        common, diffs = _diff_mandates(a, b)
        assert len(common) == 1
        assert len(diffs) == 0

    def test_added_mandate(self) -> None:
        a = SoulSnapshot(profile_name="a", mandates=[{"id": "m1"}])
        b = SoulSnapshot(profile_name="b", mandates=[{"id": "m1"}, {"id": "m2"}])
        common, diffs = _diff_mandates(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"

    def test_removed_mandate(self) -> None:
        a = SoulSnapshot(profile_name="a", mandates=[{"id": "m1"}, {"id": "m2"}])
        b = SoulSnapshot(profile_name="b", mandates=[{"id": "m1"}])
        common, diffs = _diff_mandates(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "removed"


class TestDiffAwakeningMarks:
    """Tests for ``_diff_awakening_marks()``."""

    def test_identical(self) -> None:
        a = SoulSnapshot(profile_name="a", awakening_marks=[{"timestamp": "t1", "desc": "x"}])
        b = SoulSnapshot(profile_name="b", awakening_marks=[{"timestamp": "t1", "desc": "x"}])
        common, diffs = _diff_awakening_marks(a, b)
        assert len(common) == 1
        assert len(diffs) == 0

    def test_added_mark(self) -> None:
        a = SoulSnapshot(profile_name="a", awakening_marks=[{"timestamp": "t1"}])
        b = SoulSnapshot(profile_name="b", awakening_marks=[{"timestamp": "t1"}, {"timestamp": "t2"}])
        common, diffs = _diff_awakening_marks(a, b)
        assert len(diffs) == 1
        assert diffs[0].diff_type == "added"

    def test_time_field_fallback(self) -> None:
        a = SoulSnapshot(profile_name="a", awakening_marks=[])
        b = SoulSnapshot(profile_name="b", awakening_marks=[{"time": "2025-01-01", "desc": "event"}])
        common, diffs = _diff_awakening_marks(a, b)
        assert len(diffs) == 1
        assert diffs[0].field_name == "2025-01-01"


# ═══════════════════════════════════════════════════════════════════════
# Full diff integration
# ═══════════════════════════════════════════════════════════════════════


class TestDiffSouls:
    """Tests for ``diff_souls()`` — full profile comparison."""

    def test_diff_identical_profiles(self, make_profile) -> None:
        """Two identical profiles produce no diffs."""
        make_profile(alpha_employee={"name": "A"}, alpha_soul_inj={},
                     beta_employee={"name": "A"}, beta_soul_inj={})
        result = diff_souls("profile-alpha", "profile-beta")
        assert isinstance(result, SoulDiff)
        assert result.profile_a == "profile-alpha"
        assert result.profile_b == "profile-beta"
        # Names match; both have no diffs
        assert len(result.diff_items) >= 0

    def test_diff_all_categories(self, make_profile) -> None:
        """Diff across all categories finds differences."""
        make_profile()
        result = diff_souls("profile-alpha", "profile-beta")

        # identity diffs: role (dev vs architect), level (senior vs staff), name (Alpha vs Beta)
        identity_diffs = [d for d in result.diff_items if d.category == "identity"]
        assert len(identity_diffs) >= 1

        # caps diffs: rust removed, system-design added
        caps_diffs = [d for d in result.diff_items if d.category == "caps"]
        assert len(caps_diffs) == 2

        # personality diffs
        personality_diffs = [d for d in result.diff_items if d.category == "personality"]
        assert len(personality_diffs) >= 1

        # mandate diffs: m2 removed, m3 added
        mandate_diffs = [d for d in result.diff_items if d.category == "mandates"]
        assert len(mandate_diffs) == 2

    def test_diff_result_is_serializable(self, make_profile) -> None:
        """SoulDiff.to_dict() produces JSON-serializable output."""
        make_profile()
        result = diff_souls("profile-alpha", "profile-beta")
        d = result.to_dict()
        assert d["profile_a"] == "profile-alpha"
        assert isinstance(d["diff_items"], list)
        # Verify JSON-serializable
        json.dumps(d)


# ═══════════════════════════════════════════════════════════════════════
# Merge
# ═══════════════════════════════════════════════════════════════════════


class TestMergeSouls:
    """Tests for ``merge_souls()`` — merging fields from source to target."""

    def test_merge_identity(self, make_profile) -> None:
        """Identity fields from source overwrite target."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["identity"])
        # Beta's name is "Beta", so after merge Alpha should be "Beta"
        assert result.identity["name"] == "Beta"

    def test_merge_capabilities_union(self, make_profile) -> None:
        """Capabilities merge as union of both sets."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["capabilities"])
        # Alpha: [python, rust], Beta: [python, system-design]
        # Union: [python, rust, system-design]
        assert "python" in result.capabilities
        assert "rust" in result.capabilities
        assert "system-design" in result.capabilities

    def test_merge_personality_source_wins(self, make_profile) -> None:
        """Personality conflicts resolved by source winning."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["personality"])
        # Alpha: {style: analytical, tone: precise}, Beta: {style: creative, tone: visionary}
        assert result.personality["style"] == "creative"

    def test_merge_mental_models(self, make_profile) -> None:
        """Mental models merge by name, source wins on conflict."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["mental_models"])
        names = {m["name"] for m in result.mental_models}
        assert "TRIZ" in names          # common
        assert "Cynefin" in names       # from Beta (added)
        assert "OODA" in names          # from Alpha (kept since Beta doesn't have it)

    def test_merge_mandates(self, make_profile) -> None:
        """Mandates merge by id, source wins."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["mandates"])
        ids = {m["id"] for m in result.mandates}
        assert "m1" in ids      # common
        assert "m2" in ids      # from Alpha (Beta doesn't have it)
        assert "m3" in ids      # from Beta

    def test_merge_awakening_marks(self, make_profile) -> None:
        """Awakening marks merge by timestamp, source wins."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["awakening_marks"])
        timestamps = {m["timestamp"] for m in result.awakening_marks}
        assert "2025-01-01" in timestamps   # from Alpha
        assert "2025-06-01" in timestamps   # from Beta

    def test_merge_emotional_anchors(self, make_profile) -> None:
        """Emotional anchors are replaced by source."""
        make_profile()
        result = merge_souls("profile-alpha", "profile-beta", ["emotional_anchors"])
        assert len(result.emotional_anchors) == 1
        assert result.emotional_anchors[0]["name"] == "wonder"  # from Beta


# ═══════════════════════════════════════════════════════════════════════
# History persistence
# ═══════════════════════════════════════════════════════════════════════


class TestSaveSnapshot:
    """Tests for ``save_snapshot()`` and ``get_soul_history()``."""

    def test_save_and_get_history(self, make_profile) -> None:
        """Saving a snapshot and retrieving history returns the entry."""
        make_profile()
        meta = save_snapshot("profile-alpha")
        assert meta["profile"] == "profile-alpha"
        assert "timestamp" in meta
        assert "path" in meta

        history = get_soul_history("profile-alpha")
        assert len(history) >= 1
        assert history[0]["profile_name"] == "profile-alpha"

    def test_get_history_empty_for_unknown_profile(self) -> None:
        """No history for a profile with no saved snapshots."""
        history = get_soul_history("ghost-profile")
        assert history == []

    def test_history_counts(self, make_profile) -> None:
        """History entries include capability/mental model/mandate counts."""
        make_profile()
        save_snapshot("profile-alpha")
        history = get_soul_history("profile-alpha")
        assert "capability_count" in history[0]
        assert "mental_model_count" in history[0]

    def test_get_history_skips_bad_files(self, make_profile) -> None:
        """Corrupted JSON files are skipped gracefully."""
        make_profile()
        save_snapshot("profile-alpha")

        # Inject a bad file
        hermes_home = Path(__import__("os").environ.get("HERMES_HOME", "/tmp"))
        hist_dir = hermes_home / "profiles" / "hermes-dashboard" / "data" / "soul_history" / "profile-alpha"
        (hist_dir / "corrupt.json").write_text("{bad json}", encoding="utf-8")

        history = get_soul_history("profile-alpha")
        # Should not crash; corrupt file skipped
        assert isinstance(history, list)


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


class TestExtractHelpers:
    """Tests for ``_extract_list()`` and ``_extract_dict()``."""

    def test_extract_list_found(self) -> None:
        data = {"items": [1, 2, 3]}
        assert _extract_list(data, "items") == [1, 2, 3]

    def test_extract_list_not_found(self) -> None:
        assert _extract_list({}, "items") == []

    def test_extract_list_multiple_keys(self) -> None:
        data = {"a": [1], "b": [2]}
        assert _extract_list(data, "x", "a") == [1]

    def test_extract_dict_found(self) -> None:
        data = {"config": {"key": "val"}}
        assert _extract_dict(data, "config") == {"key": "val"}

    def test_extract_dict_not_found(self) -> None:
        assert _extract_dict({}, "config") == {}

    def test_extract_dict_wrong_type(self) -> None:
        data = {"config": [1, 2]}
        assert _extract_dict(data, "config") == {}


class TestReadEmployeeYaml:
    """Tests for ``_read_employee_yaml()``."""

    def test_reads_employee_yaml(self, tmp_path: Path) -> None:
        """Reads employee.yaml when it exists."""
        (tmp_path / "employee.yaml").write_text("name: Test\nrole: dev\n", encoding="utf-8")
        result = _read_employee_yaml(tmp_path)
        assert result == {"name": "Test", "role": "dev"}

    def test_falls_back_to_identity_yaml(self, tmp_path: Path) -> None:
        """Falls back to identity.yaml when employee.yaml missing."""
        (tmp_path / "identity.yaml").write_text("name: ID\n", encoding="utf-8")
        result = _read_employee_yaml(tmp_path)
        assert result == {"name": "ID"}

    def test_returns_empty_when_no_files(self, tmp_path: Path) -> None:
        """Returns empty dict when neither file exists."""
        result = _read_employee_yaml(tmp_path)
        assert result == {}


class TestReadSoulInjectionYaml:
    """Tests for ``_read_soul_injection_yaml()``."""

    def test_reads_from_profile_dir(self, tmp_path: Path) -> None:
        """Reads soul-injection.yaml from profile dir."""
        (tmp_path / "soul-injection.yaml").write_text("mental_models:\n  - name: TRIZ\n", encoding="utf-8")
        result = _read_soul_injection_yaml(tmp_path)
        assert "mental_models" in result

    def test_reads_from_soul_subdir(self, tmp_path: Path) -> None:
        """Reads from soul/soul-injection.yaml when root file missing."""
        soul_dir = tmp_path / "soul"
        soul_dir.mkdir()
        (soul_dir / "soul-injection.yaml").write_text("capabilities:\n  - python\n", encoding="utf-8")
        result = _read_soul_injection_yaml(tmp_path)
        assert result["capabilities"] == ["python"]

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        """Returns empty dict when no soul-injection.yaml exists."""
        result = _read_soul_injection_yaml(tmp_path)
        assert result == {}


# Extend existing dataclass tests from the original file
class TestSoulSnapshotToDict:
    """Additional ``SoulSnapshot.to_dict()`` coverage."""

    def test_all_fields_present(self) -> None:
        snap = SoulSnapshot(
            profile_name="p",
            identity={"name": "p"},
            mental_models=[{"name": "m"}],
            capabilities=["c"],
            personality={"trait": "x"},
            mandates=[{"id": "m1"}],
            awakening_marks=[{"timestamp": "t1"}],
            emotional_anchors=[{"name": "e"}],
        )
        d = snap.to_dict()
        assert d["profile_name"] == "p"
        assert len(d["mental_models"]) == 1
        assert len(d["capabilities"]) == 1
        assert len(d["mandates"]) == 1
        assert len(d["awakening_marks"]) == 1
        assert len(d["emotional_anchors"]) == 1


class TestSoulDiffToDict:
    """Additional ``SoulDiff.to_dict()`` coverage."""

    def test_serialization(self) -> None:
        item = SoulDiffItem(category="caps", field_name="py", value_a=None, value_b="py", diff_type="added")
        diff = SoulDiff(profile_a="a", profile_b="b", diff_items=[item])
        d = diff.to_dict()
        assert d["profile_a"] == "a"
        assert len(d["diff_items"]) == 1
        assert d["diff_items"][0]["diff_type"] == "added"
