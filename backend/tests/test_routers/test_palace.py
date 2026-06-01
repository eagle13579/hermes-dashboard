"""
Tests for the Palace Router — 记忆宫殿 L1-L5 query and archive endpoints.

All file I/O is redirected to **temporary directories** via the conftest
``_HERMES_HOME_TMP`` / ``_redirect_profile_path`` setup, so no real
memory palace data is ever touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def palace_home() -> Path:
    """Return the temp hermes_home path and create basic palace structure."""
    home = settings.hermes_home
    _ensure(home / "skills" / "code-review" / "SKILL.md")
    _ensure(home / "skills" / "api-design" / "DESCRIPTION.md")
    _ensure(home / "L1图书馆" / "技能吸收卡" / "fastapi-basics" / "note.md")
    _ensure(home / "L1图书馆" / "代码资产库" / "auth-service" / "README.md")
    _ensure(home / "L1图书馆" / "ADR" / "ADR-001-use-fastapi.md")
    _ensure(home / "L3工作室" / "五池" / "模型池" / "first-principles.md")
    _ensure(home / "L5孵化室" / "产品开发" / "hermes-dashboard" / "README.md")
    _write_file(
        home / "skills" / "code-review" / "SKILL.md",
        "---\nname: Code Review\ndescription: Systematic code review skill\ncategory: productivity\ntags: [python, review]\n---\n# Code Review\n\nReview code systematically.",
    )
    _write_file(
        home / "skills" / "api-design" / "DESCRIPTION.md",
        "---\nname: API Design\ndescription: RESTful API design patterns\ncategory: backend\ntags: [api, rest]\n---\n# API Design",
    )
    _write_file(
        home / "skills" / "untagged-skill" / "SKILL.md",
        "---\nname: Untagged\ndescription: A skill with no tags\ncategory: general\n---\n# Untagged",
    )
    _write_file(
        home / "L1图书馆" / "技能吸收卡" / "fastapi-basics" / "note.md",
        "---\ndescription: FastAPI fundamentals guide\n---\n# FastAPI Basics",
    )
    _write_file(
        home / "L1图书馆" / "代码资产库" / "auth-service" / "README.md",
        "# Auth Service\n\nAuthentication service with JWT support",
    )
    _write_file(
        home / "L1图书馆" / "代码资产库" / "auth-service" / "main.py",
        "print('hello')",
    )
    _write_file(
        home / "L1图书馆" / "ADR" / "ADR-001-use-fastapi.md",
        "---\ntitle: Use FastAPI for backend\nstatus: accepted\ndecision: Use FastAPI with Pydantic v2\n---\n# ADR-001",
    )
    _write_file(
        home / "L3工作室" / "五池" / "模型池" / "first-principles.md",
        "---\nname: First Principles\ndescription: Break down problems to fundamental truths\napplicable_scenarios: Problem-solving, Innovation\ntags: [thinking, framework]\n---\n# First Principles\n\nBreak down complex problems.",
    )
    _write_file(
        home / "L3工作室" / "五池" / "模型池" / "inverted-rule.txt",
        "---\nname: Inverted Rule\ndescription: Think in opposites\n---\n# Inverted Rule",
    )
    _write_file(
        home / "L5孵化室" / "产品开发" / "hermes-dashboard" / "README.md",
        "---\ndescription: Dashboard for Hermes AI profiles\nstatus: active\n---\n# Hermes Dashboard\n\nMain dashboard product.",
    )
    return home


def _ensure(path: str | Path) -> None:
    """Create parent directories for *path* and touch the file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.is_file():
        p.write_text("", encoding="utf-8")


def _write_file(path: str | Path, content: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# GET  /api/palace/skills
# ═══════════════════════════════════════════════════════════════════════


class TestQuerySkills:
    """Search skills in the palace."""

    def test_returns_all_skills(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["total"] >= 3
        names = [r["name"] for r in data["results"]]
        assert "Code Review" in names
        assert "API Design" in names

    def test_search_by_query(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/skills?q=review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert any("review" in r["name"].lower() for r in data["results"])

    def test_filter_by_category(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/skills?category=backend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for r in data["results"]:
            assert r["category"] == "backend"

    def test_pagination(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/skills?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["total"] >= 3
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_404_when_skills_dir_missing(self, test_client: TestClient, palace_home: Path) -> None:
        import shutil
        skills_dir = palace_home / "skills"
        if skills_dir.exists():
            shutil.rmtree(skills_dir)
        resp = test_client.get("/api/palace/skills")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# GET  /api/palace/library
# ═══════════════════════════════════════════════════════════════════════


class TestQueryLibrary:
    """Query L1图书馆 resources."""

    def test_returns_all_types(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/library")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        types = {r["type"] for r in data["results"]}
        assert "skills_cards" in types
        assert "code_harvest" in types
        assert "adr" in types

    def test_filter_by_type_skills_cards(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.get("/api/palace/library?type=skills_cards")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["type"] == "skills_cards" for r in data["results"])

    def test_filter_by_type_code_harvest(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.get("/api/palace/library?type=code_harvest")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["type"] == "code_harvest" for r in data["results"])

    def test_filter_by_type_adr(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/library?type=adr")
        assert resp.status_code == 200
        data = resp.json()
        assert all(r["type"] == "adr" for r in data["results"])

    def test_search_query(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/library?q=fastapi")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_404_when_library_missing(self, test_client: TestClient, palace_home: Path) -> None:
        import shutil
        lib_dir = palace_home / "L1图书馆"
        if lib_dir.exists():
            shutil.rmtree(lib_dir)
        resp = test_client.get("/api/palace/library")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# GET  /api/palace/models
# ═══════════════════════════════════════════════════════════════════════


class TestQueryModels:
    """Query L3 mental models."""

    def test_returns_models(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["total"] >= 2
        names = [r["name"] for r in data["results"]]
        assert "First Principles" in names

    def test_search_models(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/models?q=principles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_404_when_model_dir_missing(self, test_client: TestClient, palace_home: Path) -> None:
        import shutil
        model_dir = palace_home / "L3工作室" / "五池" / "模型池"
        if model_dir.exists():
            shutil.rmtree(model_dir)
        resp = test_client.get("/api/palace/models")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# GET  /api/palace/products
# ═══════════════════════════════════════════════════════════════════════


class TestQueryProducts:
    """Query L5 product development items."""

    def test_returns_products(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/products")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert data["total"] >= 1
        names = [r["name"] for r in data["results"]]
        assert "hermes-dashboard" in names

    def test_filter_by_status(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/products?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_search_products(self, test_client: TestClient, palace_home: Path) -> None:
        resp = test_client.get("/api/palace/products?q=dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    def test_404_when_products_dir_missing(self, test_client: TestClient, palace_home: Path) -> None:
        import shutil
        products_dir = palace_home / "L5孵化室" / "产品开发"
        if products_dir.exists():
            shutil.rmtree(products_dir)
        resp = test_client.get("/api/palace/products")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# POST  /api/palace/archive/code
# ═══════════════════════════════════════════════════════════════════════


class TestArchiveCode:
    """Archive code to L1图书馆/代码资产库."""

    def test_archive_code_with_all_fields(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.post(
            "/api/palace/archive/code",
            json={
                "name": "test-script",
                "content": "print('hello world')",
                "description": "A simple test script",
                "language": "python",
                "tags": ["test", "script"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "test-script"
        # Verify file was created
        code_dir = palace_home / "L1图书馆" / "代码资产库" / "test-script"
        assert code_dir.is_dir()
        assert (code_dir / "main.py").is_file()
        assert (code_dir / "README.md").is_file()
        assert (code_dir / ".meta.json").is_file()

    def test_archive_code_minimal(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.post(
            "/api/palace/archive/code",
            json={
                "name": "minimal-script",
                "content": "echo hello",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
# POST  /api/palace/archive/model
# ═══════════════════════════════════════════════════════════════════════


class TestArchiveModel:
    """Archive mental model to L3五池/模型池."""

    def test_archive_model_to_existing_pool(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.post(
            "/api/palace/archive/model",
            json={
                "name": "Occam's Razor",
                "description": "Simplest explanation is often correct",
                "applicable_scenarios": "Debugging, Decision-making",
                "tags": ["logic", "simplicity"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"
        # Should have been written to the existing L3 pool
        model_file = (
            palace_home / "L3工作室" / "五池" / "模型池" / "Occam's Razor.md"
        )
        assert model_file.is_file()

    def test_archive_model_creates_default_pool(
        self, test_client: TestClient
    ) -> None:
        """When no model pool dir exists, it creates the default L3 path."""
        resp = test_client.post(
            "/api/palace/archive/model",
            json={
                "name": "New Model",
                "description": "A brand new mental model",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
# POST  /api/palace/archive/adr
# ═══════════════════════════════════════════════════════════════════════


class TestArchiveAdr:
    """Archive ADR to L1图书馆/ADR."""

    def test_archive_adr_with_all_fields(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.post(
            "/api/palace/archive/adr",
            json={
                "title": "Use PostgreSQL for persistence",
                "status": "accepted",
                "context": "Need a reliable database",
                "decision": "Use PostgreSQL with SQLAlchemy",
                "consequences": "Increased operational complexity",
                "alternatives": ["MySQL", "SQLite"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"
        assert "use-postgresql" in data["filename"].lower()
        # Verify file exists
        adr_dir = palace_home / "L1图书馆" / "ADR"
        adr_files = list(adr_dir.glob("ADR-*.md"))
        assert len(adr_files) >= 1

    def test_archive_adr_minimal(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        resp = test_client.post(
            "/api/palace/archive/adr",
            json={
                "title": "Minimal Decision",
                "context": "Simple context",
                "decision": "Simple decision",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "ok"

    def test_archive_adr_auto_increments_number(
        self, test_client: TestClient, palace_home: Path
    ) -> None:
        """Sequential ADR numbers should auto-increment."""
        # First ADR
        resp1 = test_client.post(
            "/api/palace/archive/adr",
            json={
                "title": "First Decision",
                "context": "Context A",
                "decision": "Decision A",
            },
        )
        assert resp1.status_code == 201
        f1 = resp1.json()["filename"]

        # Second ADR
        resp2 = test_client.post(
            "/api/palace/archive/adr",
            json={
                "title": "Second Decision",
                "context": "Context B",
                "decision": "Decision B",
            },
        )
        assert resp2.status_code == 201
        f2 = resp2.json()["filename"]

        assert f1 != f2
        # The second should have a higher number
        import re

        n1 = int(re.search(r"ADR-(\d+)", f1).group(1))  # type: ignore[union-attr]
        n2 = int(re.search(r"ADR-(\d+)", f2).group(1))  # type: ignore[union-attr]
        assert n2 > n1
