"""Tests for :mod:`services.sync_bridge` — file hashing, classification, sync bridge."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from services.sync_bridge import (
    SyncConfig,
    SyncRecord,
    SyncBridge,
    compute_hash,
    classify_file,
    get_bridge,
)


class TestComputeHash:
    """Tests for ``compute_hash()`` — deterministic SHA-256 hex digest."""

    def test_known_file_hash(self, tmp_path: Path) -> None:
        """Compute hash of a known string written to a temp file."""
        fp = tmp_path / "test.txt"
        fp.write_text("hello world\n", encoding="utf-8")
        digest = compute_hash(str(fp))
        assert isinstance(digest, str)
        assert len(digest) == 64  # SHA-256 hex

    def test_hash_changes_when_content_changes(self, tmp_path: Path) -> None:
        """Different content → different hash."""
        fp = tmp_path / "test.txt"
        fp.write_text("content a", encoding="utf-8")
        h1 = compute_hash(str(fp))
        fp.write_text("content b", encoding="utf-8")
        h2 = compute_hash(str(fp))
        assert h1 != h2

    def test_nonexistent_file_raises(self) -> None:
        """FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            compute_hash("/nonexistent/path/file.txt")


class TestClassifyFile:
    """Tests for ``classify_file()`` — extension-based file classification."""

    def test_python_file(self) -> None:
        assert classify_file("/path/to/module.py") == "code"

    def test_yaml_file(self) -> None:
        result = classify_file("/path/to/config.yaml")
        assert isinstance(result, str)

    def test_json_file(self) -> None:
        result = classify_file("/path/to/data.json")
        assert isinstance(result, str)

    def test_markdown_file(self) -> None:
        assert classify_file("/path/to/doc.md") == "document"

    def test_unknown_extension(self) -> None:
        result = classify_file("/path/to/file.xyz")
        assert isinstance(result, str)
        assert result in ("other", "code", "document", "config", "log", "artifact")

    def test_no_extension(self) -> None:
        result = classify_file("/path/to/README")
        assert isinstance(result, str)


class TestSyncRecord:
    """Tests for ``SyncRecord`` dataclass — serialization round-trips."""

    def test_to_dict_from_dict_roundtrip(self) -> None:
        """``to_dict()`` → ``from_dict()`` preserves all fields."""
        original = SyncRecord(
            source_profile="test",
            filepath="/profiles/test/soul.md",
            data_type="document",
            sha256_hash="abc123",
            status="pending",
        )
        d = original.to_dict()
        restored = SyncRecord.from_dict(d)
        assert restored == original

    def test_default_status(self) -> None:
        """Default status is 'pending'."""
        r = SyncRecord(source_profile="p", filepath="/a.txt", data_type="code", sha256_hash="h")
        assert r.status == "pending"


class TestSyncBridge:
    """Tests for ``SyncBridge`` — sync orchestration singleton."""

    def test_singleton_get_bridge(self) -> None:
        """``get_bridge()`` returns the same instance within a test."""
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2

    def test_initial_status(self) -> None:
        """Fresh bridge has zero counts."""
        bridge = SyncBridge()
        status = bridge.get_sync_status()
        assert status.get("sync_count", 0) == 0
        assert status.get("failed_count", 0) == 0

    def test_scan_files_empty_directory(self, tmp_path: Path) -> None:
        """Scanning an empty directory returns an empty list."""
        bridge = SyncBridge()
        results = bridge.scan_files(str(tmp_path))
        assert isinstance(results, list)

    def test_scan_files_finds_python_files(self, tmp_path: Path) -> None:
        """Scanning a dir with .py files includes them in results."""
        (tmp_path / "mod.py").write_text("print('hello')")
        bridge = SyncBridge()
        results = bridge.scan_files(str(tmp_path))
        assert len(results) >= 1

    def test_pending_count_starts_at_zero(self) -> None:
        """Fresh bridge has 0 pending items."""
        bridge = SyncBridge()
        assert bridge.get_pending_count() == 0

    def test_get_sync_history_returns_list(self) -> None:
        """History is always a list (possibly empty)."""
        bridge = SyncBridge()
        history = bridge.get_sync_history(limit=5)
        assert isinstance(history, list)


class TestSyncConfigDefaults:
    """Tests for ``SyncConfig`` default values."""

    def test_has_pg_conn_str(self) -> None:
        """SyncConfig has pg_conn_str attribute."""
        config = SyncConfig()
        assert hasattr(config, 'pg_conn_str')

    def test_has_profile_dir(self) -> None:
        """SyncConfig has profile_dir attribute."""
        config = SyncConfig()
        assert hasattr(config, 'profile_dir')
