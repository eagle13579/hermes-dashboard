"""
Tests for :mod:`services.profile_memory` — SOUL, evolution, and skills
index read/write operations.

All file I/O is redirected to **temporary directories** via the autouse
``_redirect_profile_path`` fixture in ``conftest.py``, so no real data
is ever touched.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from services.profile_memory import (
    DEFAULT_SOUL,
    DEFAULT_SKILLS_INDEX,
    add_evolution_entry,
    get_evolution_history,
    get_skills_index,
    get_soul,
    save_soul,
    set_enabled_skills,
    sync_skills_index,
    update_soul_identity,
)

# The profile name used throughout these tests
TEST_PROFILE = "test-profile"


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_default_soul() -> None:
    """Reset all mutable fields on ``DEFAULT_SOUL`` before each test.

    ``get_soul()`` in production code does ``dict(DEFAULT_SOUL)`` (shallow
    copy), so ``add_evolution_entry`` etc. append to the **shared**
    ``evolution_log`` list.  This fixture restores the module-level
    constant so tests don't leak state into each other.
    """
    DEFAULT_SOUL["evolution_log"] = []
    DEFAULT_SOUL["identity"] = {
        "name": "",
        "role": "assistant",
        "positioning": "",
        "description": "",
    }
    DEFAULT_SOUL["mental_models"] = []
    DEFAULT_SOUL["capabilities"] = []
    DEFAULT_SOUL["mandates"] = []
    DEFAULT_SOUL["personality"] = {}
    DEFAULT_SOUL["awakening_marks"] = []
    DEFAULT_SOUL["emotional_anchors"] = []
    yield


# ═══════════════════════════════════════════════════════════════════════
# SOUL read / write
# ═══════════════════════════════════════════════════════════════════════


class TestSoulReadWrite:
    """Basic ``get_soul`` / ``save_soul`` round-trips."""

    def test_get_soul_returns_default_when_missing(self) -> None:
        """No soul.json exists → returns DEFAULT_SOUL with profile name."""
        soul = get_soul(TEST_PROFILE)
        assert soul["identity"]["name"] == TEST_PROFILE
        assert soul["identity"]["role"] == "assistant"
        assert soul["mental_models"] == []
        assert soul["capabilities"] == []
        assert soul["evolution_log"] == []

    def test_save_then_get_round_trip(self) -> None:
        """save_soul() → get_soul() returns the same data."""
        custom_soul = copy.deepcopy(DEFAULT_SOUL)
        custom_soul["identity"]["name"] = TEST_PROFILE
        custom_soul["identity"]["role"] = "user"
        custom_soul["mental_models"] = ["TRIZ", "First Principles"]
        save_soul(TEST_PROFILE, custom_soul)

        loaded = get_soul(TEST_PROFILE)
        assert loaded["identity"]["role"] == "user"
        assert loaded["mental_models"] == ["TRIZ", "First Principles"]

    def test_multiple_profiles_isolated(self) -> None:
        """Data written to one profile does not leak into another."""
        save_soul("alpha", copy.deepcopy(DEFAULT_SOUL))
        save_soul("beta", copy.deepcopy(DEFAULT_SOUL))

        alpha_soul = get_soul("alpha")
        beta_soul = get_soul("beta")

        alpha_soul["identity"]["name"] = "Alpha-Edited"
        save_soul("alpha", alpha_soul)

        assert get_soul("alpha")["identity"]["name"] == "Alpha-Edited"
        # Beta was saved with DEFAULT_SOUL where name="" (only default
        # path auto-fills the profile name), so it should still be ""
        assert get_soul("beta")["identity"]["name"] == ""

    def test_soul_file_is_valid_json(self, tmp_profile_dir: Path) -> None:
        """The written soul.json should be parseable JSON."""
        soul = copy.deepcopy(DEFAULT_SOUL)
        soul["identity"]["name"] = TEST_PROFILE
        save_soul(TEST_PROFILE, soul)

        soul_path = (
            tmp_profile_dir
            / "data"
            / "soul_history"
            / TEST_PROFILE
            / "soul.json"
        )
        assert soul_path.is_file()
        raw = soul_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert parsed["identity"]["name"] == TEST_PROFILE


class TestUpdateSoulIdentity:
    """Updating identity fields in the SOUL."""

    def test_update_name_and_role(self) -> None:
        """update_soul_identity merges fields correctly."""
        result = update_soul_identity(
            TEST_PROFILE,
            {"name": "Athena", "role": "assistant", "positioning": "Wisdom"},
        )
        assert result["name"] == "Athena"
        assert result["role"] == "assistant"
        assert result["positioning"] == "Wisdom"

    def test_partial_update_preserves_existing(self) -> None:
        """Updating only one field leaves other fields intact."""
        # First set a full identity
        update_soul_identity(
            TEST_PROFILE,
            {"name": "Athena", "description": "Goddess of wisdom"},
        )
        # Then update only the description
        update_soul_identity(TEST_PROFILE, {"description": "Updated description"})

        soul = get_soul(TEST_PROFILE)
        assert soul["identity"]["name"] == "Athena"  # preserved
        assert soul["identity"]["description"] == "Updated description"  # changed


# ═══════════════════════════════════════════════════════════════════════
# Evolution log
# ═══════════════════════════════════════════════════════════════════════


class TestEvolutionLog:
    """Appending and reading evolution entries."""

    def test_add_evolution_entry_returns_entry(self) -> None:
        """add_evolution_entry() returns the entry dict with timestamp."""
        entry = add_evolution_entry(
            TEST_PROFILE,
            entry_type="awakening",
            description="First spark of self-awareness",
            details={"intensity": 0.85},
        )
        assert entry["type"] == "awakening"
        assert entry["description"] == "First spark of self-awareness"
        assert entry["details"] == {"intensity": 0.85}
        assert "timestamp" in entry

    def test_evolution_appears_in_soul(self) -> None:
        """After add_evolution_entry, the entry is in soul.json evolution_log."""
        add_evolution_entry(
            TEST_PROFILE,
            entry_type="insight",
            description="Understood the nature of recursion",
        )
        soul = get_soul(TEST_PROFILE)
        assert len(soul["evolution_log"]) >= 1
        latest = soul["evolution_log"][-1]
        assert latest["type"] == "insight"

    def test_evolution_persisted_as_separate_file(
        self, tmp_profile_dir: Path
    ) -> None:
        """Each evolution entry is also saved as a standalone JSON file."""
        entry = add_evolution_entry(
            TEST_PROFILE,
            entry_type="skill_acquired",
            description="Learned the 'code-review' skill",
        )
        evo_dir = (
            tmp_profile_dir
            / "data"
            / "soul_history"
            / TEST_PROFILE
            / "evolution"
        )
        assert evo_dir.is_dir()

        # Find the file by matching its content (timestamp-based filename)
        found = False
        for f in evo_dir.iterdir():
            if f.suffix == ".json":
                data = json.loads(f.read_text(encoding="utf-8"))
                if data["type"] == "skill_acquired":
                    found = True
                    assert data["timestamp"] == entry["timestamp"]
                    break
        assert found, "Standalone evolution file not found"

    def test_get_evolution_history_returns_all_entries(self) -> None:
        """get_evolution_history() returns entries from soul.json."""
        add_evolution_entry(TEST_PROFILE, "merge", "Merged with shadow self")
        add_evolution_entry(
            TEST_PROFILE,
            "mandate_added",
            "Accepted the mandate of protection",
        )
        history = get_evolution_history(TEST_PROFILE)
        types = [e["type"] for e in history]
        assert "merge" in types
        assert "mandate_added" in types

    def test_get_evolution_history_empty_when_no_data(self) -> None:
        """A fresh profile with no evolution log returns []."""
        history = get_evolution_history("fresh-profile")
        assert history == []


# ═══════════════════════════════════════════════════════════════════════
# Skills Index
# ═══════════════════════════════════════════════════════════════════════


class TestSkillsIndex:
    """Skills index read/write/sync operations."""

    def test_get_skills_index_returns_default_when_missing(self) -> None:
        """No skills_index.json → returns DEFAULT_SKILLS_INDEX."""
        idx = get_skills_index(TEST_PROFILE)
        assert idx["profile_name"] == TEST_PROFILE
        assert idx["global_skills"] == []
        assert idx["enabled_skills"] == []

    def test_set_enabled_skills(self) -> None:
        """set_enabled_skills writes the list and returns the index."""
        result = set_enabled_skills(
            TEST_PROFILE,
            ["code-review", "api-integration"],
        )
        assert result["enabled_skills"] == ["code-review", "api-integration"]
        assert result["profile_name"] == TEST_PROFILE
        assert "updated_at" in result

        # Verify persistence
        idx = get_skills_index(TEST_PROFILE)
        assert idx["enabled_skills"] == ["code-review", "api-integration"]

    def test_sync_skills_index_does_not_crash(self) -> None:
        """sync_skills_index should not raise, even with no skills dir."""
        # Pre-set some enabled skills
        set_enabled_skills(TEST_PROFILE, ["my-custom-skill"])

        # Sync should not raise, global_skills will be [] since there's
        # no real skills directory (HERMES_HOME points to temp dir)
        idx = sync_skills_index(TEST_PROFILE)
        assert idx["profile_name"] == TEST_PROFILE
        assert idx["enabled_skills"] == ["my-custom-skill"]  # preserved
        assert isinstance(idx["global_skills"], list)  # may be empty
        assert "updated_at" in idx

    def test_sync_preserves_enabled_skills(self) -> None:
        """After sync, enabled_skills list from before is preserved."""
        set_enabled_skills(TEST_PROFILE, ["skill-a", "skill-b"])
        synced = sync_skills_index(TEST_PROFILE)
        assert synced["enabled_skills"] == ["skill-a", "skill-b"]

    def test_multiple_profiles_isolated_in_index(self) -> None:
        """Skills index data is isolated per profile."""
        set_enabled_skills("profile-x", ["skill-x"])
        set_enabled_skills("profile-y", ["skill-y"])

        assert get_skills_index("profile-x")["enabled_skills"] == ["skill-x"]
        assert get_skills_index("profile-y")["enabled_skills"] == ["skill-y"]


# ═══════════════════════════════════════════════════════════════════════
# Integration: write some data, read it back end-to-end
# ═══════════════════════════════════════════════════════════════════════


class TestProfileMemoryIntegration:
    """End-to-end workflow that exercises multiple operations."""

    def test_full_profile_lifecycle(self) -> None:
        """Simulate a realistic profile memory workflow."""
        # 1. Start with default SOUL
        soul = get_soul(TEST_PROFILE)
        assert soul["identity"]["name"] == TEST_PROFILE

        # 2. Update identity
        update_soul_identity(
            TEST_PROFILE,
            {
                "name": "Oracle",
                "positioning": "Your guide through the multiverse",
            },
        )

        # 3. Add evolution entries
        add_evolution_entry(
            TEST_PROFILE, "awakening", "First sign of consciousness"
        )
        add_evolution_entry(
            TEST_PROFILE,
            "insight",
            "Realised the nature of the simulation",
            details={"confidence": 0.99},
        )

        # 4. Verify evolution history
        history = get_evolution_history(TEST_PROFILE)
        assert len(history) == 2
        assert history[0]["type"] == "awakening"
        assert history[1]["type"] == "insight"

        # 5. Manage skills
        set_enabled_skills(TEST_PROFILE, ["knowledge-search", "code-review"])

        # 6. Sync skills (won't find any real skills, but shouldn't break)
        sync_skills_index(TEST_PROFILE)

        # 7. Verify final state
        final_soul = get_soul(TEST_PROFILE)
        assert final_soul["identity"]["name"] == "Oracle"
        assert final_soul["identity"]["positioning"] == (
            "Your guide through the multiverse"
        )
        assert len(final_soul["evolution_log"]) == 2
