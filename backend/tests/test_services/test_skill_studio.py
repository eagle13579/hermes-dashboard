"""
Tests for :mod:`services.skill_studio` — skill CRUD, templates, and testing.

All file I/O is redirected to temporary directories via the conftest.py
HERMES_HOME override, so no real data is ever touched.

We mock ``_call_skill_manage`` to avoid depending on the hermes CLI tool.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from services.skill_studio import (
    SkillInfo,
    SkillTemplate,
    VALID_CATEGORIES,
    DEFAULT_CATEGORY,
    _get_iso_now,
    _mtime_iso,
    _ctime_iso,
    _parse_skill_description,
    list_skills,
    get_skill_detail,
    create_skill,
    edit_skill,
    delete_skill,
    publish_skill,
    get_skill_templates,
    create_from_template,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _auto_mock_skill_manage():
    """Auto-mock ``_call_skill_manage`` for all tests in this module.

    Returns a default success response for any action.
    """
    with patch("services.skill_studio._call_skill_manage") as mock:
        mock.return_value = {"success": True, "raw_output": "mocked"}
        yield mock


@pytest.fixture
def mock_skill_manage(_auto_mock_skill_manage):
    """Convenience alias for the mocked skill_manage."""
    return _auto_mock_skill_manage


@pytest.fixture
def skills_root() -> Path:
    """Return the ``$HERMES_HOME/skills/`` path from the temp env."""
    import os
    hermes_home = Path(os.environ["HERMES_HOME"])
    return hermes_home / "skills"


@pytest.fixture
def isolated_hermes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Set HERMES_HOME to an isolated temp dir for a single test."""
    isolated = tmp_path / "hermes_home"
    isolated.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(isolated))
    # Also override the settings if relevant
    return isolated


@pytest.fixture
def create_test_skill(skills_root: Path) -> callable:
    """Create a real skill directory + SKILL.md for testing."""
    def _create(name: str, category: str = "general", content: str | None = None) -> Path:
        skill_dir = skills_root / category / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        md = skill_dir / "SKILL.md"
        if content is None:
            content = (
                f"# {name}\n\n"
                f"## Description\n"
                f"A test skill.\n\n"
                f"## Usage\n"
                f"Example usage here.\n"
                f"\n"
                f"## Configuration\n"
                f"No special config needed.\n"
                f"\n"
                f"## Dependencies\n"
                f"- Python 3.10+\n"
            )
        md.write_text(content, encoding="utf-8")
        return md
    return _create


# ═══════════════════════════════════════════════════════════════════════
# Data model tests
# ═══════════════════════════════════════════════════════════════════════


class TestSkillTemplate:
    """Tests for ``SkillTemplate`` dataclass."""

    def test_to_dict(self) -> None:
        t = SkillTemplate(name="test", description="desc", category="general", template_content="# {name}")
        d = t.to_dict()
        assert d["name"] == "test"
        assert d["category"] == "general"

    def test_from_dict(self) -> None:
        data = {"name": "t1", "description": "d1", "category": "utility", "template_content": "x"}
        t = SkillTemplate.from_dict(data)
        assert t.name == "t1"
        assert t.category == "utility"


class TestSkillInfo:
    """Tests for ``SkillInfo`` dataclass."""

    def test_to_dict(self) -> None:
        info = SkillInfo(name="my-skill", description="does stuff", category="general",
                         path="/tmp/skills/general/my-skill", is_published=True)
        d = info.to_dict()
        assert d["name"] == "my-skill"
        assert d["is_published"] is True

    def test_from_dict(self) -> None:
        data = {"name": "s1", "description": "d1", "category": "utility", "path": "/p", "is_published": False}
        info = SkillInfo.from_dict(data)
        assert info.name == "s1"


class TestValidCategories:
    """Tests for ``VALID_CATEGORIES`` constant."""

    def test_known_categories(self) -> None:
        assert "general" in VALID_CATEGORIES
        assert "data-pipeline" in VALID_CATEGORIES
        assert "api-integration" in VALID_CATEGORIES
        assert "analysis" in VALID_CATEGORIES
        assert len(VALID_CATEGORIES) == 8


# ═══════════════════════════════════════════════════════════════════════
# Path & time helpers
# ═══════════════════════════════════════════════════════════════════════


class TestTimeHelpers:
    """Tests for ``_get_iso_now()``, ``_mtime_iso()``, ``_ctime_iso()``."""

    def test_get_iso_now_returns_string(self) -> None:
        now = _get_iso_now()
        assert isinstance(now, str)
        assert "T" in now

    def test_mtime_iso_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        iso = _mtime_iso(f)
        assert isinstance(iso, str)
        assert "T" in iso

    def test_mtime_iso_nonexistent_file(self) -> None:
        assert _mtime_iso(Path("/nonexistent/file")) is None

    def test_ctime_iso_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello", encoding="utf-8")
        iso = _ctime_iso(f)
        assert isinstance(iso, str)
        assert "T" in iso

    def test_ctime_iso_nonexistent(self, tmp_path: Path) -> None:
        """Nonexistent path returns None (no crash)."""
        assert _ctime_iso(tmp_path / "does_not_exist") is None


class TestParseSkillDescription:
    """Tests for ``_parse_skill_description()``."""

    def test_finds_description_line(self, tmp_path: Path) -> None:
        md = tmp_path / "SKILL.md"
        md.write_text(
            "# My Skill\n"
            "**Name**: My Skill\n"
            "Description: A useful skill for testing\n"
            "## Usage\n",
            encoding="utf-8",
        )
        desc = _parse_skill_description(md)
        assert desc == "A useful skill for testing"

    def test_fallback_after_heading(self, tmp_path: Path) -> None:
        md = tmp_path / "SKILL.md"
        md.write_text("# My Skill\nThis is the first non-empty line after the heading.\n", encoding="utf-8")
        desc = _parse_skill_description(md)
        assert "first non-empty" in desc

    def test_no_heading_returns_empty(self, tmp_path: Path) -> None:
        md = tmp_path / "SKILL.md"
        md.write_text("Just some text without a heading.\n", encoding="utf-8")
        desc = _parse_skill_description(md)
        assert desc == ""

    def test_nonexistent_file(self) -> None:
        assert _parse_skill_description(Path("/nonexistent/SKILL.md")) == ""


# ═══════════════════════════════════════════════════════════════════════
# list_skills
# ═══════════════════════════════════════════════════════════════════════


class TestListSkills:
    """Tests for ``list_skills()``."""

    def test_empty_when_no_skills_dir(self, skills_root: Path) -> None:
        """No skills directory returns empty list."""
        skills = list_skills()
        assert skills == []

    def test_lists_skills_in_categories(self, create_test_skill) -> None:
        """Skills in multiple categories are all listed."""
        create_test_skill("skill-a", "general")
        create_test_skill("skill-b", "utility")
        skills = list_skills()
        names = {s["name"] for s in skills}
        assert "skill-a" in names
        assert "skill-b" in names

    def test_skill_info_has_all_fields(self, isolated_hermes: Path) -> None:
        """Each skill dict contains expected fields."""
        from services.skill_studio import list_skills as _list
        # Create a skill in the isolated hermes
        skills_root_iso = isolated_hermes / "skills"
        skill_dir = skills_root_iso / "general" / "my-skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        md = skill_dir / "SKILL.md"
        md.write_text("# My Skill\n\n## Description\nA test skill.\n\n## Usage\nExample.\n", encoding="utf-8")

        skills = _list()
        assert len(skills) == 1
        s = skills[0]
        assert s["name"] == "my-skill"
        assert s["category"] == "general"
        assert "path" in s
        assert "is_published" in s
        assert "description" in s

    def test_skill_with_published_marker(self, create_test_skill, skills_root: Path) -> None:
        """Skills with .published marker show is_published=True."""
        create_test_skill("pub-skill", "general")
        (skills_root / "general" / "pub-skill" / ".published").write_text("published", encoding="utf-8")
        skills = list_skills()
        pub = [s for s in skills if s["name"] == "pub-skill"][0]
        assert pub["is_published"] is True

    def test_ignores_non_directory_entries(self, isolated_hermes: Path) -> None:
        """Non-directory entries under skills/ are ignored."""
        from services.skill_studio import list_skills as _list
        skills_root_iso = isolated_hermes / "skills"
        skills_root_iso.mkdir(parents=True, exist_ok=True)
        (skills_root_iso / "not-a-dir.txt").write_text("x", encoding="utf-8")
        skills = _list()
        assert skills == []


# ═══════════════════════════════════════════════════════════════════════
# get_skill_detail
# ═══════════════════════════════════════════════════════════════════════


class TestGetSkillDetail:
    """Tests for ``get_skill_detail()``."""

    def test_finds_skill_content(self, create_test_skill) -> None:
        """Returns full content of SKILL.md."""
        create_test_skill("detail-skill", "general", content="# Detail Skill\n\nDetailed content here.")
        detail = get_skill_detail("detail-skill")
        assert detail["name"] == "detail-skill"
        assert detail["category"] == "general"
        assert "Detailed content here." in detail["content"]

    def test_not_found_raises(self) -> None:
        """Non-existent skill raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            get_skill_detail("nonexistent-skill")

    def test_skill_in_utility_category(self, create_test_skill) -> None:
        """Finds skill across different categories."""
        create_test_skill("cross-skill", "utility")
        detail = get_skill_detail("cross-skill")
        assert detail["category"] == "utility"
        assert detail["name"] == "cross-skill"


# ═══════════════════════════════════════════════════════════════════════
# create_skill
# ═══════════════════════════════════════════════════════════════════════


class TestCreateSkill:
    """Tests for ``create_skill()``."""

    def test_creates_skill_with_defaults(self, mock_skill_manage, skills_root: Path) -> None:
        """Creates a skill with auto-generated template content."""
        result = create_skill(name="new-skill", description="A brand new skill")
        assert result["success"] is True
        assert result["name"] == "new-skill"
        assert result["category"] == "general"
        md_path = skills_root / "general" / "new-skill" / "SKILL.md"
        assert md_path.is_file()
        assert "# new-skill" in md_path.read_text(encoding="utf-8")
        mock_skill_manage.assert_called_once()

    def test_creates_skill_with_custom_content(self, mock_skill_manage, skills_root: Path) -> None:
        """Creates a skill with provided content."""
        custom = "# Custom Skill\n\nMy custom content."
        result = create_skill(name="custom-skill", description="Custom", category="utility", content=custom)
        assert result["success"] is True
        md_path = skills_root / "utility" / "custom-skill" / "SKILL.md"
        assert md_path.read_text(encoding="utf-8") == custom
        mock_skill_manage.assert_called_once()

    def test_invalid_category_raises(self) -> None:
        """Invalid category causes ValueError."""
        with pytest.raises(ValueError, match="Invalid category"):
            create_skill(name="bad-skill", description="x", category="INVALID")

    def test_duplicate_skill_raises(self, create_test_skill) -> None:
        """Creating a skill that already exists raises ValueError."""
        create_test_skill("dupe-skill", "general")
        with pytest.raises(ValueError, match="already exists"):
            create_skill(name="dupe-skill", description="duplicate", category="general")

    def test_skill_manage_failure_still_writes_file(self, mock_skill_manage, skills_root: Path) -> None:
        """Even if skill_manage fails, the SKILL.md file is created."""
        mock_skill_manage.return_value = {"success": False, "error": "CLI error"}
        result = create_skill(name="partial-skill", description="partial")
        assert result["success"] is True  # creation succeeds despite skill_manage failure
        md_path = skills_root / "general" / "partial-skill" / "SKILL.md"
        assert md_path.is_file()


# ═══════════════════════════════════════════════════════════════════════
# edit_skill
# ═══════════════════════════════════════════════════════════════════════


class TestEditSkill:
    """Tests for ``edit_skill()``."""

    def test_edit_updates_content(self, create_test_skill, mock_skill_manage) -> None:
        """Editing a skill updates its SKILL.md content."""
        create_test_skill("edit-me", "general")
        new_content = "# Edited Skill\n\nUpdated content."
        result = edit_skill(name="edit-me", content=new_content)
        assert result["success"] is True
        assert result["name"] == "edit-me"
        # Verify the file was updated
        skill_dir = Path(result["path"]).parent
        updated = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "Updated content." in updated

    def test_edit_nonexistent_raises(self) -> None:
        """Editing a non-existent skill raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            edit_skill(name="ghost", content="nothing")


# ═══════════════════════════════════════════════════════════════════════
# delete_skill
# ═══════════════════════════════════════════════════════════════════════


class TestDeleteSkill:
    """Tests for ``delete_skill()``."""

    def test_deletes_skill_directory(self, create_test_skill, skills_root: Path) -> None:
        """Deleting a skill removes its directory."""
        create_test_skill("delete-me", "general")
        result = delete_skill(name="delete-me")
        assert result["success"] is True
        assert not (skills_root / "general" / "delete-me").is_dir()

    def test_delete_nonexistent_raises(self) -> None:
        """Deleting a non-existent skill raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            delete_skill(name="ghost-skill")

    def test_delete_skill_in_utility_category(self, create_test_skill, skills_root: Path) -> None:
        """Delete works across categories."""
        create_test_skill("tool-skill", "utility")
        delete_skill(name="tool-skill")
        assert not (skills_root / "utility" / "tool-skill").is_dir()


# ═══════════════════════════════════════════════════════════════════════
# test_skill
# ═══════════════════════════════════════════════════════════════════════


class TestTestSkill:
    """Tests for ``test_skill()``."""

    def test_valid_skill_passes(self, create_test_skill) -> None:
        """A well-formed skill passes validation."""
        from services.skill_studio import test_skill as _test
        create_test_skill("valid-skill", "general")
        result = _test(name="valid-skill")
        assert result["success"] is True
        assert len(result["warnings"]) == 0

    def test_skill_without_sections_shows_warnings(self, create_test_skill) -> None:
        """A minimal skill file generates warnings."""
        from services.skill_studio import test_skill as _test
        create_test_skill("minimal-skill", "general", content="# Minimal")
        result = _test(name="minimal-skill")
        assert result["success"] is False
        assert len(result["warnings"]) >= 1

    def test_skill_with_test_input(self, create_test_skill) -> None:
        """Test input is included in execution log."""
        from services.skill_studio import test_skill as _test
        create_test_skill("input-skill", "general")
        result = _test(name="input-skill", test_input="hello world")
        assert result["test_input"] == "hello world"
        assert any("INPUT" in line for line in result["execution_log"])

    def test_nonexistent_skill_raises(self) -> None:
        """Test on non-existent skill raises FileNotFoundError."""
        from services.skill_studio import test_skill as _test
        with pytest.raises(FileNotFoundError):
            _test(name="no-such-skill")


# ═══════════════════════════════════════════════════════════════════════
# publish_skill
# ═══════════════════════════════════════════════════════════════════════


class TestPublishSkill:
    """Tests for ``publish_skill()``."""

    def test_publish_creates_marker(self, create_test_skill, skills_root: Path) -> None:
        """Publishing creates a .published marker file."""
        create_test_skill("pub-me", "general")
        result = publish_skill(name="pub-me")
        assert result["success"] is True
        assert result["is_published"] is True
        marker = skills_root / "general" / "pub-me" / ".published"
        assert marker.is_file()

    def test_publish_nonexistent_raises(self) -> None:
        """Publishing a non-existent skill raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            publish_skill(name="ghost")

    def test_publish_in_utility(self, create_test_skill, skills_root: Path) -> None:
        """Publish works across categories."""
        create_test_skill("util-pub", "utility")
        publish_skill(name="util-pub")
        marker = skills_root / "utility" / "util-pub" / ".published"
        assert marker.is_file()


# ═══════════════════════════════════════════════════════════════════════
# get_skill_templates & create_from_template
# ═══════════════════════════════════════════════════════════════════════


class TestGetSkillTemplates:
    """Tests for ``get_skill_templates()``."""

    def test_returns_all_templates(self) -> None:
        templates = get_skill_templates()
        assert len(templates) >= 3
        names = [t["name"] for t in templates]
        assert "basic-skill" in names
        assert "data-pipeline" in names
        assert "api-integration" in names

    def test_each_template_has_fields(self) -> None:
        templates = get_skill_templates()
        for t in templates:
            assert "name" in t
            assert "description" in t
            assert "category" in t
            assert "template_content" in t


class TestCreateFromTemplate:
    """Tests for ``create_from_template()``."""

    def test_creates_from_basic_skill(self, mock_skill_manage, skills_root: Path) -> None:
        """Creating from 'basic-skill' template works."""
        result = create_from_template(name="template-skill", template_id="basic-skill",
                                      description="From template")
        assert result["success"] is True
        md_path = skills_root / "general" / "template-skill" / "SKILL.md"
        assert md_path.is_file()
        content = md_path.read_text(encoding="utf-8")
        assert "# template-skill" in content

    def test_creates_from_data_pipeline(self, mock_skill_manage, skills_root: Path) -> None:
        """Creating from 'data-pipeline' template."""
        result = create_from_template(name="pipeline-skill", template_id="data-pipeline",
                                      description="Pipeline skill")
        assert result["success"] is True
        md_path = skills_root / "data-pipeline" / "pipeline-skill" / "SKILL.md"
        assert md_path.is_file()

    def test_unknown_template_raises(self) -> None:
        """Unknown template ID raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            create_from_template(name="x", template_id="nonexistent-template")

    def test_with_extra_context(self, mock_skill_manage, skills_root: Path) -> None:
        """Extra context is substituted into template content."""
        result = create_from_template(
            name="ctx-skill",
            template_id="basic-skill",
            description="Context substituted",
            extra_context={"version": "2.0"},
        )
        assert result["success"] is True

    def test_with_custom_category_overrides(self, mock_skill_manage, skills_root: Path) -> None:
        """Custom category overrides the template's default."""
        result = create_from_template(
            name="custom-cat-skill",
            template_id="basic-skill",
            description="Custom cat",
            category="analysis",
        )
        assert result["category"] == "analysis"
        md_path = skills_root / "analysis" / "custom-cat-skill" / "SKILL.md"
        assert md_path.is_file()


# ═══════════════════════════════════════════════════════════════════════
# Path helper integration (skills directory creation)
# ═══════════════════════════════════════════════════════════════════════


class TestSkillsDirAutoCreate:
    """``_skills_dir()`` creates the directory if it doesn't exist."""

    def test_skills_dir_created_on_list(self, isolated_hermes: Path) -> None:
        """Calling list_skills creates the skills directory."""
        from services.skill_studio import list_skills as _list
        assert not (isolated_hermes / "skills").is_dir()
        _list()
        assert (isolated_hermes / "skills").is_dir()
