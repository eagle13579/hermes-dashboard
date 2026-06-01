"""
Soul Diff — SOUL comparison and merge service for Hermes profiles.

Provides data models and logic to snapshot, diff, and merge the structured
SOUL data (soul-injection.yaml + employee.yaml / identity.yaml) between
two Hermes profiles.

Data persistence: ``$HERMES_HOME/profiles/hermes-dashboard/data/soul_history/``
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════


@dataclass
class SoulSnapshot:
    """A point-in-time snapshot of a profile's structured SOUL data.

    Attributes
    ----------
    profile_name : str
        Name of the profile.
    identity : dict
        Identity metadata parsed from ``employee.yaml`` / ``identity.yaml``
        (name, role, type, level, …).
    mental_models : list[dict]
        Mental model entries (each with ``name``, ``value``, …).
    capabilities : list[str]
        List of capability names / descriptions.
    personality : dict
        Personality traits as key-value pairs.
    mandates : list[dict]
        Mandate / directive entries (with ``id``, ``content``, …).
    awakening_marks : list[dict]
        Awakening milestone marks (with ``timestamp``, ``description``, …).
    emotional_anchors : list[dict]
        Emotional anchor entries.
    """

    profile_name: str
    identity: dict[str, Any] = field(default_factory=dict)
    mental_models: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    personality: dict[str, Any] = field(default_factory=dict)
    mandates: list[dict[str, Any]] = field(default_factory=list)
    awakening_marks: list[dict[str, Any]] = field(default_factory=list)
    emotional_anchors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return asdict(self)


@dataclass
class SoulDiffItem:
    """A single difference between two SOUL snapshots.

    Attributes
    ----------
    category : str
        Section category: ``identity``, ``models``, ``caps``, ``personality``,
        or ``mandates``.
    field_name : str
        Name of the field, model name, capability, etc.
    value_a : Any
        Value in profile A (or ``None`` if added).
    value_b : Any
        Value in profile B (or ``None`` if removed).
    diff_type : str
        Type of difference: ``added``, ``removed``, or ``modified``.
    """

    category: str
    field_name: str
    value_a: Any = None
    value_b: Any = None
    diff_type: str = "modified"


@dataclass
class SoulDiff:
    """Result of comparing two SOUL snapshots.

    Attributes
    ----------
    profile_a : str
        Name of the first profile.
    profile_b : str
        Name of the second profile.
    common_items : list[dict]
        Items that exist identically in both profiles (for reference).
    diff_items : list[SoulDiffItem]
        List of differences between the two profiles.
    """

    profile_a: str
    profile_b: str
    common_items: list[dict[str, Any]] = field(default_factory=list)
    diff_items: list[SoulDiffItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary."""
        return {
            "profile_a": self.profile_a,
            "profile_b": self.profile_b,
            "common_items": self.common_items,
            "diff_items": [asdict(d) for d in self.diff_items],
        }


# ══════════════════════════════════════════════════════════════════════
# Path helpers
# ══════════════════════════════════════════════════════════════════════


def _get_hermes_home() -> Path:
    """Return the ``$HERMES_HOME`` directory path.

    Raises
    ------
    EnvironmentError
        If ``$HERMES_HOME`` is not set.
    """
    raw = os.environ.get("HERMES_HOME")
    if not raw:
        raise OSError(
            "HERMES_HOME environment variable is not set. "
            "Please set it to your Hermes knowledge base root, e.g.\n"
            '  export HERMES_HOME="D:\\向海容的知识库\\wiki\\wiki\\记忆宫殿"'
        )
    return Path(raw).expanduser().resolve()


def _profiles_dir() -> Path:
    """Return the absolute path to ``$HERMES_HOME/profiles/``."""
    return _get_hermes_home() / "profiles"


def _profile_path(profile_name: str) -> Path:
    """Return the absolute path to a profile directory.

    Parameters
    ----------
    profile_name : str
        Profile directory name.

    Returns
    -------
    Path
        Absolute path to the profile directory.

    Raises
    ------
    FileNotFoundError
        If the profile directory does not exist.
    """
    p = _profiles_dir() / profile_name
    if not p.is_dir():
        raise FileNotFoundError(f"Profile '{profile_name}' not found at {p}")
    return p


def _soul_history_dir() -> Path:
    """Return the soul history persistence directory, creating it if needed.

    Path: ``$HERMES_HOME/profiles/hermes-dashboard/data/soul_history/``
    """
    d = _profiles_dir() / "hermes-dashboard" / "data" / "soul_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ══════════════════════════════════════════════════════════════════════
# YAML / JSON file readers
# ══════════════════════════════════════════════════════════════════════


def _safe_load_yaml(path: Path) -> dict[str, Any] | list[Any] | None:
    """Safely load a YAML file, returning ``None`` on any error."""
    try:
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="replace")
            cleaned = raw.replace("\x00", "")
            return yaml.safe_load(cleaned)
    except Exception as exc:
        logger.warning("Failed to load YAML %s: %s", path, exc)
    return None


def _safe_load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    """Safely load a JSON file, returning ``None`` on any error."""
    try:
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="replace")
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to load JSON %s: %s", path, exc)
    return None


# ══════════════════════════════════════════════════════════════════════
# Snapshot — read structured SOUL from a profile directory
# ══════════════════════════════════════════════════════════════════════


def _read_employee_yaml(profile_dir: Path) -> dict[str, Any]:
    """Read ``employee.yaml`` or ``identity.yaml`` from the profile dir.

    Checks for ``employee.yaml`` first, then ``identity.yaml``.
    Returns an empty dict if neither exists.
    """
    for name in ("employee.yaml", "identity.yaml"):
        path = profile_dir / name
        if path.is_file():
            result = _safe_load_yaml(path)
            if isinstance(result, dict):
                return result
            if result is None:
                return {}
            return {}
    return {}


def _read_soul_injection_yaml(profile_dir: Path) -> dict[str, Any]:
    """Read ``soul-injection.yaml`` from the profile directory.

    Checks two locations:
    1. ``<profile_dir>/soul-injection.yaml``
    2. ``<profile_dir>/soul/soul-injection.yaml``

    Returns an empty dict if neither exists.
    """
    candidates = [
        profile_dir / "soul-injection.yaml",
        profile_dir / "soul" / "soul-injection.yaml",
    ]
    for path in candidates:
        if path.is_file():
            result = _safe_load_yaml(path)
            if isinstance(result, dict):
                return result
            if result is None:
                return {}
            return {}
    return {}


def _extract_list(data: dict[str, Any], *keys: str) -> list[Any]:
    """Extract a list value from nested dict, trying multiple keys."""
    for key in keys:
        val = data.get(key)
        if isinstance(val, list):
            return val
    return []


def _extract_dict(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Extract a dict value from nested dict, trying multiple keys."""
    for key in keys:
        val = data.get(key)
        if isinstance(val, dict):
            return val
    return {}


def take_snapshot(profile_name: str) -> SoulSnapshot:
    """Read a profile's structured SOUL data and produce a snapshot.

    Parses ``soul-injection.yaml`` + ``employee.yaml`` / ``identity.yaml``
    from the profile directory.  Gracefully handles missing files by
    returning empty collections.

    Parameters
    ----------
    profile_name : str
        Name of the profile (directory under ``$HERMES_HOME/profiles/``).

    Returns
    -------
    SoulSnapshot
        The parsed snapshot.  All list/dict fields will be empty if no
        SOUL data files are found.
    """
    pdir = _profile_path(profile_name)

    # ── Load raw data ────────────────────────────────────────────────
    employee = _read_employee_yaml(pdir)
    soul_inj = _read_soul_injection_yaml(pdir)

    # ── Identity ─────────────────────────────────────────────────────
    identity: dict[str, Any] = {}
    # Merge: employee.yaml identity fields take precedence
    if employee:
        identity.update(employee)
    # soul-injection may have identity-like fields
    inj_identity = _extract_dict(soul_inj, "identity", "identity_meta", "info")
    if inj_identity:
        # Don't overwrite employee fields
        for k, v in inj_identity.items():
            identity.setdefault(k, v)

    # If still empty, populate minimal identity from SOUL.md fallback
    if not identity:
        soul_md = pdir / "SOUL.md"
        if soul_md.is_file():
            first_line = soul_md.read_text(encoding="utf-8", errors="replace").split("\n")[0]
            identity = {"name": profile_name, "title_hint": first_line.strip("# \t")}
        else:
            identity = {"name": profile_name}

    # ── Mental models ────────────────────────────────────────────────
    mental_models: list[dict[str, Any]] = []
    raw_mm = _extract_list(soul_inj, "mental_models", "mental-models")
    for m in raw_mm:
        if isinstance(m, dict):
            mental_models.append(m)
        elif isinstance(m, str):
            mental_models.append({"name": m, "value": ""})

    # ── Capabilities ─────────────────────────────────────────────────
    capabilities: list[str] = []
    raw_caps = _extract_list(employee, "capabilities")
    if not raw_caps:
        raw_caps = _extract_list(soul_inj, "capabilities")
    for c in raw_caps:
        if isinstance(c, str):
            capabilities.append(c)
        elif isinstance(c, dict):
            capabilities.append(c.get("name", str(c)))

    # ── Personality ──────────────────────────────────────────────────
    personality: dict[str, Any] = _extract_dict(
        soul_inj, "personality", "personality_traits", "traits"
    )

    # ── Mandates ─────────────────────────────────────────────────────
    mandates: list[dict[str, Any]] = []
    raw_mandates = _extract_list(soul_inj, "mandates", "directives", "rules")
    for m in raw_mandates:
        if isinstance(m, dict):
            mandates.append(m)
        elif isinstance(m, str):
            mandates.append({"id": f"rule-{len(mandates)+1}", "content": m})

    # ── Awakening marks ──────────────────────────────────────────────
    awakening_marks: list[dict[str, Any]] = []
    raw_marks = _extract_list(
        soul_inj, "awakening_marks", "awakening-marks", "awakening"
    )
    for m in raw_marks:
        if isinstance(m, dict):
            awakening_marks.append(m)

    # ── Emotional anchors ────────────────────────────────────────────
    emotional_anchors: list[dict[str, Any]] = []
    raw_anchors = _extract_list(
        soul_inj, "emotional_anchors", "emotional-anchors", "anchors"
    )
    for a in raw_anchors:
        if isinstance(a, dict):
            emotional_anchors.append(a)

    return SoulSnapshot(
        profile_name=profile_name,
        identity=identity,
        mental_models=mental_models,
        capabilities=capabilities,
        personality=personality,
        mandates=mandates,
        awakening_marks=awakening_marks,
        emotional_anchors=emotional_anchors,
    )


# ══════════════════════════════════════════════════════════════════════
# Diff logic
# ══════════════════════════════════════════════════════════════════════


def _diff_identity(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare identity fields between two snapshots."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    all_keys = set(snapshot_a.identity.keys()) | set(snapshot_b.identity.keys())

    for key in sorted(all_keys):
        va = snapshot_a.identity.get(key)
        vb = snapshot_b.identity.get(key)

        if va == vb:
            common.append({"field": key, "value": va})
        elif va is None and vb is not None:
            diffs.append(
                SoulDiffItem(
                    category="identity",
                    field_name=key,
                    value_a=None,
                    value_b=vb,
                    diff_type="added",
                )
            )
        elif va is not None and vb is None:
            diffs.append(
                SoulDiffItem(
                    category="identity",
                    field_name=key,
                    value_a=va,
                    value_b=None,
                    diff_type="removed",
                )
            )
        else:
            diffs.append(
                SoulDiffItem(
                    category="identity",
                    field_name=key,
                    value_a=va,
                    value_b=vb,
                    diff_type="modified",
                )
            )

    return common, diffs


def _diff_mental_models(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare mental models by ``name`` key, highlighting value changes."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    # Index by name
    models_a: dict[str, dict] = {}
    for m in snapshot_a.mental_models:
        name = m.get("name", str(m))
        models_a[name] = m

    models_b: dict[str, dict] = {}
    for m in snapshot_b.mental_models:
        name = m.get("name", str(m))
        models_b[name] = m

    all_names = set(models_a.keys()) | set(models_b.keys())

    for name in sorted(all_names):
        ma = models_a.get(name)
        mb = models_b.get(name)

        if ma is not None and mb is not None:
            if ma == mb:
                common.append({"name": name, "value": ma})
            else:
                diffs.append(
                    SoulDiffItem(
                        category="models",
                        field_name=name,
                        value_a=ma,
                        value_b=mb,
                        diff_type="modified",
                    )
                )
        elif ma is not None and mb is None:
            diffs.append(
                SoulDiffItem(
                    category="models",
                    field_name=name,
                    value_a=ma,
                    value_b=None,
                    diff_type="removed",
                )
            )
        else:  # ma is None, mb is not None
            diffs.append(
                SoulDiffItem(
                    category="models",
                    field_name=name,
                    value_a=None,
                    value_b=mb,
                    diff_type="added",
                )
            )

    return common, diffs


def _diff_capabilities(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare capabilities as a set (A vs B)."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    set_a = set(snapshot_a.capabilities)
    set_b = set(snapshot_b.capabilities)

    for cap in sorted(set_a & set_b):
        common.append({"capability": cap})

    for cap in sorted(set_b - set_a):
        diffs.append(
            SoulDiffItem(
                category="caps", field_name=cap, value_a=None, value_b=cap, diff_type="added"
            )
        )

    for cap in sorted(set_a - set_b):
        diffs.append(
            SoulDiffItem(
                category="caps", field_name=cap, value_a=cap, value_b=None, diff_type="removed"
            )
        )

    return common, diffs


def _diff_personality(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare personality fields field-by-field."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    all_keys = set(snapshot_a.personality.keys()) | set(snapshot_b.personality.keys())

    for key in sorted(all_keys):
        va = snapshot_a.personality.get(key)
        vb = snapshot_b.personality.get(key)

        if va == vb:
            common.append({"field": key, "value": va})
        elif va is None and vb is not None:
            diffs.append(
                SoulDiffItem(
                    category="personality",
                    field_name=key,
                    value_a=None,
                    value_b=vb,
                    diff_type="added",
                )
            )
        elif va is not None and vb is None:
            diffs.append(
                SoulDiffItem(
                    category="personality",
                    field_name=key,
                    value_a=va,
                    value_b=None,
                    diff_type="removed",
                )
            )
        else:
            diffs.append(
                SoulDiffItem(
                    category="personality",
                    field_name=key,
                    value_a=va,
                    value_b=vb,
                    diff_type="modified",
                )
            )

    return common, diffs


def _diff_mandates(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare mandates by ``id`` key."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    # Index by id
    mandates_a: dict[str, dict] = {}
    for m in snapshot_a.mandates:
        mid = m.get("id", str(m))
        mandates_a[mid] = m

    mandates_b: dict[str, dict] = {}
    for m in snapshot_b.mandates:
        mid = m.get("id", str(m))
        mandates_b[mid] = m

    all_ids = set(mandates_a.keys()) | set(mandates_b.keys())

    for mid in sorted(all_ids):
        ma = mandates_a.get(mid)
        mb = mandates_b.get(mid)

        if ma is not None and mb is not None:
            if ma == mb:
                common.append({"id": mid, "value": ma})
            else:
                diffs.append(
                    SoulDiffItem(
                        category="mandates",
                        field_name=mid,
                        value_a=ma,
                        value_b=mb,
                        diff_type="modified",
                    )
                )
        elif ma is not None and mb is None:
            diffs.append(
                SoulDiffItem(
                    category="mandates",
                    field_name=mid,
                    value_a=ma,
                    value_b=None,
                    diff_type="removed",
                )
            )
        else:
            diffs.append(
                SoulDiffItem(
                    category="mandates",
                    field_name=mid,
                    value_a=None,
                    value_b=mb,
                    diff_type="added",
                )
            )

    return common, diffs


def _diff_awakening_marks(
    snapshot_a: SoulSnapshot, snapshot_b: SoulSnapshot
) -> tuple[list[dict[str, Any]], list[SoulDiffItem]]:
    """Compare awakening marks by timestamp key."""
    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    # Index by timestamp
    marks_a: dict[str, dict] = {}
    for m in snapshot_a.awakening_marks:
        ts = m.get("timestamp", m.get("time", str(len(marks_a))))
        marks_a[str(ts)] = m

    marks_b: dict[str, dict] = {}
    for m in snapshot_b.awakening_marks:
        ts = m.get("timestamp", m.get("time", str(len(marks_b))))
        marks_b[str(ts)] = m

    all_ts = set(marks_a.keys()) | set(marks_b.keys())

    for ts in sorted(all_ts):
        ma = marks_a.get(ts)
        mb = marks_b.get(ts)

        if ma is not None and mb is not None:
            if ma == mb:
                common.append({"timestamp": ts, "value": ma})
            else:
                diffs.append(
                    SoulDiffItem(
                        category="awakening",
                        field_name=ts,
                        value_a=ma,
                        value_b=mb,
                        diff_type="modified",
                    )
                )
        elif ma is not None and mb is None:
            diffs.append(
                SoulDiffItem(
                    category="awakening",
                    field_name=ts,
                    value_a=ma,
                    value_b=None,
                    diff_type="removed",
                )
            )
        else:
            diffs.append(
                SoulDiffItem(
                    category="awakening",
                    field_name=ts,
                    value_a=None,
                    value_b=mb,
                    diff_type="added",
                )
            )

    return common, diffs


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════


def diff_souls(profile_a: str, profile_b: str) -> SoulDiff:
    """Compare the structured SOUL data of two profiles.

    Parameters
    ----------
    profile_a : str
        Name of the first profile.
    profile_b : str
        Name of the second profile.

    Returns
    -------
    SoulDiff
        Full diff result with common items and per-category differences.
    """
    snap_a = take_snapshot(profile_a)
    snap_b = take_snapshot(profile_b)

    common: list[dict[str, Any]] = []
    diffs: list[SoulDiffItem] = []

    # ── identity ─────────────────────────────────────────────────────
    c, d = _diff_identity(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    # ── mental models ────────────────────────────────────────────────
    c, d = _diff_mental_models(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    # ── capabilities ─────────────────────────────────────────────────
    c, d = _diff_capabilities(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    # ── personality ──────────────────────────────────────────────────
    c, d = _diff_personality(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    # ── mandates ─────────────────────────────────────────────────────
    c, d = _diff_mandates(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    # ── awakening marks ──────────────────────────────────────────────
    c, d = _diff_awakening_marks(snap_a, snap_b)
    common.extend(c)
    diffs.extend(d)

    return SoulDiff(
        profile_a=profile_a,
        profile_b=profile_b,
        common_items=common,
        diff_items=diffs,
    )


# ══════════════════════════════════════════════════════════════════════
# Merge
# ══════════════════════════════════════════════════════════════════════


def _write_employee_yaml(profile_dir: Path, data: dict[str, Any]) -> None:
    """Write (or update) ``employee.yaml`` in the profile directory."""
    path = profile_dir / "employee.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info("Wrote %s", path)


def _write_soul_injection_yaml(profile_dir: Path, data: dict[str, Any]) -> None:
    """Write (or update) ``soul-injection.yaml`` in the profile directory."""
    path = profile_dir / "soul-injection.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    logger.info("Wrote %s", path)


def merge_souls(
    target_profile: str, source_profile: str, merge_fields: list[str]
) -> SoulSnapshot:
    """Merge specified SOUL fields from *source_profile* into *target_profile*.

    The merge is applied directly: target's ``employee.yaml`` and
    ``soul-injection.yaml`` are updated in place.

    Supported fields in *merge_fields*:
      - ``identity`` — merge top-level identity keys
      - ``mental_models`` — merge mental models (by name, source wins)
      - ``capabilities`` — merge capabilities (union of both sets)
      - ``personality`` — merge personality fields (source wins on conflict)
      - ``mandates`` — merge mandates (by id, source wins)
      - ``awakening_marks`` — merge awakening marks (by timestamp, source wins)
      - ``emotional_anchors`` — merge emotional anchors

    Parameters
    ----------
    target_profile : str
        Name of the target profile (receives merged data).
    source_profile : str
        Name of the source profile (data provider).
    merge_fields : list[str]
        List of field categories to merge.

    Returns
    -------
    SoulSnapshot
        Snapshot of the *target* profile **after** the merge.
    """
    target_dir = _profile_path(target_profile)
    source_dir = _profile_path(source_profile)

    target_snap = take_snapshot(target_profile)
    source_snap = take_snapshot(source_profile)

    # ── Read existing files ──────────────────────────────────────────
    target_employee = _read_employee_yaml(target_dir)
    target_soul_inj = _read_soul_injection_yaml(target_dir)
    source_employee = _read_employee_yaml(source_dir)
    source_soul_inj = _read_soul_injection_yaml(source_dir)

    # ── Identity merge ───────────────────────────────────────────────
    if "identity" in merge_fields:
        for k, v in source_snap.identity.items():
            target_employee[k] = v
        _write_employee_yaml(target_dir, target_employee)

    # ── Mental models merge ──────────────────────────────────────────
    if "mental_models" in merge_fields:
        # Merge by name: source wins
        merged: dict[str, dict] = {}
        for m in target_snap.mental_models:
            name = m.get("name", str(m))
            merged[name] = m
        for m in source_snap.mental_models:
            name = m.get("name", str(m))
            merged[name] = m  # source overwrites
        target_soul_inj["mental_models"] = list(merged.values())
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # ── Capabilities merge (union) ───────────────────────────────────
    if "capabilities" in merge_fields:
        merged_caps = list(set(target_snap.capabilities) | set(source_snap.capabilities))
        target_employee["capabilities"] = merged_caps
        target_soul_inj["capabilities"] = merged_caps
        _write_employee_yaml(target_dir, target_employee)
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # ── Personality merge ────────────────────────────────────────────
    if "personality" in merge_fields:
        merged_personality = dict(target_snap.personality)
        merged_personality.update(source_snap.personality)  # source wins
        target_soul_inj["personality"] = merged_personality
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # ── Mandates merge (by id, source wins) ──────────────────────────
    if "mandates" in merge_fields:
        merged_mandates: dict[str, dict] = {}
        for m in target_snap.mandates:
            mid = m.get("id", str(m))
            merged_mandates[mid] = m
        for m in source_snap.mandates:
            mid = m.get("id", str(m))
            merged_mandates[mid] = m  # source overwrites
        target_soul_inj["mandates"] = list(merged_mandates.values())
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # ── Awakening marks merge (by timestamp, source wins) ────────────
    if "awakening_marks" in merge_fields:
        merged_marks: dict[str, dict] = {}
        for m in target_snap.awakening_marks:
            ts = m.get("timestamp", m.get("time", str(len(merged_marks))))
            merged_marks[str(ts)] = m
        for m in source_snap.awakening_marks:
            ts = m.get("timestamp", m.get("time", str(len(merged_marks))))
            merged_marks[str(ts)] = m  # source overwrites
        target_soul_inj["awakening_marks"] = list(merged_marks.values())
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # ── Emotional anchors merge ──────────────────────────────────────
    if "emotional_anchors" in merge_fields:
        # Simple list-level merge: source list replaces
        target_soul_inj["emotional_anchors"] = source_snap.emotional_anchors
        _write_soul_injection_yaml(target_dir, target_soul_inj)

    # Return post-merge snapshot
    return take_snapshot(target_profile)


# ══════════════════════════════════════════════════════════════════════
# History (snapshot persistence)
# ══════════════════════════════════════════════════════════════════════


def save_snapshot(profile_name: str) -> dict[str, Any]:
    """Take a snapshot of the profile's SOUL and persist it to history.

    Each snapshot is saved as a timestamped JSON file in the soul history
    directory: ``<soul_history_dir>/<profile_name>/<timestamp>.json``.

    Parameters
    ----------
    profile_name : str
        Name of the profile to snapshot.

    Returns
    -------
    dict
        Metadata about the saved snapshot: ``{"profile": ..., "timestamp": ..., "path": ...}``
    """
    snapshot = take_snapshot(profile_name)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")

    history_dir = _soul_history_dir() / profile_name
    history_dir.mkdir(parents=True, exist_ok=True)

    path = history_dir / f"{ts}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot.to_dict(), fh, ensure_ascii=False, indent=2)

    logger.info("Saved SOUL snapshot for '%s' to %s", profile_name, path)
    return {
        "profile": profile_name,
        "timestamp": ts,
        "path": str(path),
    }


def get_soul_history(profile_name: str) -> list[dict[str, Any]]:
    """Return a list of historical SOUL snapshots for the given profile.

    Snapshots are sorted oldest-first.  Each entry contains snapshot
    metadata plus a truncated view of the data.

    Parameters
    ----------
    profile_name : str
        Name of the profile.

    Returns
    -------
    list[dict]
        Chronological list of ``{"timestamp": ..., "profile_name": ..., "identity": ..., "capability_count": ...}``
        entries.  An empty list if no history exists.
    """
    history_dir = _soul_history_dir() / profile_name
    if not history_dir.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for json_file in sorted(history_dir.iterdir()):
        if json_file.suffix != ".json":
            continue
        try:
            with open(json_file, encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
            entries.append(
                {
                    "timestamp": json_file.stem,
                    "profile_name": data.get("profile_name", profile_name),
                    "identity": data.get("identity", {}),
                    "capability_count": len(data.get("capabilities", [])),
                    "mental_model_count": len(data.get("mental_models", [])),
                    "mandate_count": len(data.get("mandates", [])),
                    "path": str(json_file),
                }
            )
        except Exception as exc:
            logger.warning("Failed to read history snapshot %s: %s", json_file, exc)

    return entries
