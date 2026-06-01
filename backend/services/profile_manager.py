"""
Profile Manager — Hermes profile lifecycle service.

Provides an asynchronous interface for listing, creating, deleting, starting,
stopping, and querying the status of Hermes agent profiles.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ProfileInfo:
    """Summary of a single Hermes profile."""

    name: str
    """Directory name of the profile."""
    soul_summary: str | None = None
    """First 200 characters of SOUL.md (truncated)."""
    config: dict[str, Any] = field(default_factory=dict)
    """Parsed contents of config.yaml."""
    pid: int | None = None
    """Process ID if the profile is currently running, else ``None``."""
    port: int | None = None
    """Port number if a socket listener is detected, else ``None``."""
    running: bool = False
    """``True`` if the profile process is alive and listening."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary."""
        return asdict(self)


@dataclass
class ProfileDetail(ProfileInfo):
    """Full detail of a single profile including the complete SOUL.md text."""

    soul_full: str | None = None
    """Complete content of SOUL.md."""
    config_path: str | None = None
    """Absolute path to the profile's config.yaml."""
    soul_path: str | None = None
    """Absolute path to the profile's SOUL.md."""
    profile_dir: str | None = None
    """Absolute path to the profile directory."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Running-process registry (in-memory, non-persistent)
# ──────────────────────────────────────────────────────────────────────

_running_processes: dict[str, subprocess.Popen[bytes]] = {}
"""In-memory mapping of profile name → Popen handle for started processes."""


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


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


def _find_hermes_cli() -> str:
    """Locate the ``hermes`` CLI executable.

    Returns
    -------
    str
        Absolute path to the ``hermes`` binary.
    """
    import shutil

    exe = shutil.which("hermes")
    if exe:
        return exe
    # Fallback: check common locations
    candidates = [
        Path.home() / "AppData/Local/hermes/hermes-agent/venv/Scripts/hermes",
        Path.home() / ".local/bin/hermes",
        Path.home() / "bin/hermes",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    msg = (
        "hermes CLI not found on PATH.  "
        "Ensure Hermes Agent is installed and the venv is activated."
    )
    raise FileNotFoundError(msg)


def _detect_port_sync(profile_dir: Path) -> int | None:
    """Synchronous port detection — run via ``asyncio.to_thread()``."""
    config_path = profile_dir / "config.yaml"
    if config_path.is_file():
        try:
            with open(config_path, encoding="utf-8") as fh:
                cfg: dict[str, Any] = yaml.safe_load(fh) or {}
            explicit_port = cfg.get("gateway", {}).get("port")
            if explicit_port is not None:
                ports_to_check = [int(explicit_port)]
            else:
                ports_to_check = list(range(18080, 18091))
        except Exception:
            ports_to_check = list(range(18080, 18091))
    else:
        ports_to_check = list(range(18080, 18091))

    for port in ports_to_check:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return port
    return None


async def _detect_port(profile_dir: Path) -> int | None:
    """Async wrapper around the blocking port scan."""
    return await asyncio.to_thread(_detect_port_sync, profile_dir)


async def _read_yaml_sync(path: Path) -> dict[str, Any]:
    """Read and parse a YAML file in a thread pool."""
    def _read() -> dict[str, Any]:
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return await asyncio.to_thread(_read)


async def _read_text_sync(path: Path) -> str:
    """Read a text file in a thread pool."""
    return await asyncio.to_thread(
        lambda p=path: p.read_text(encoding="utf-8", errors="replace")
    )


async def _run_subprocess_sync(args: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    """Run a blocking subprocess in a thread pool."""
    import subprocess as _subprocess
    return await asyncio.to_thread(
        lambda: _subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    )


async def _run_hermes_cli(*args: str, timeout: int = 30) -> str:
    """Run ``hermes`` CLI as a subprocess and return stdout.

    Parameters
    ----------
    *args
        Command-line arguments passed after ``hermes``.
    timeout : int
        Maximum seconds to wait for completion.

    Returns
    -------
    str
        Decoded stdout of the command.

    Raises
    ------
    RuntimeError
        If the CLI returns a non-zero exit code.
    """
    hermes_bin = _find_hermes_cli()
    cmd = [hermes_bin, *args]
    logger.debug("Running: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"hermes CLI timed out after {timeout}s: {' '.join(cmd)}")

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        raise RuntimeError(
            f"hermes CLI failed (exit code {proc.returncode}):\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stderr: {stderr or '(empty)'}"
        )
    return stdout


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


class ProfileManager:
    """Manages Hermes agent profiles — CRUD, lifecycle, and status checks.

    All public methods are ``async`` and safe to call from FastAPI route
    handlers.
    """

    # ── List ──────────────────────────────────────────────────────────

    @staticmethod
    async def list_profiles() -> list[ProfileInfo]:
        """Scan the profiles directory and return a summary for each profile.

        Reads ``SOUL.md`` (first 200 chars) and ``config.yaml`` from every
        subdirectory under ``$HERMES_HOME/profiles/``.  Also checks whether
        the profile is currently running (PID + port detection).

        Returns
        -------
        list[ProfileInfo]
            One entry per discovered profile directory.
        """
        profiles_dir = _profiles_dir()
        if not profiles_dir.is_dir():
            logger.warning("Profiles directory does not exist: %s", profiles_dir)
            return []

        results: list[ProfileInfo] = []
        for entry in sorted(profiles_dir.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            info = await ProfileManager.get_profile_status(name)
            soul_summary: str | None = None
            config_data: dict[str, Any] = {}

            soul_path = entry / "SOUL.md"
            if soul_path.is_file():
                try:
                    text = await asyncio.to_thread(
                        lambda p=soul_path: p.read_text(encoding="utf-8", errors="replace")
                    )
                    soul_summary = text[:200].replace("\n", " ").strip()
                except Exception as exc:
                    logger.warning("Failed to read SOUL.md for %s: %s", name, exc)

            config_path = entry / "config.yaml"
            if config_path.is_file():
                try:
                    config_data = await _read_yaml_sync(config_path)
                except Exception as exc:
                    logger.warning("Failed to read config.yaml for %s: %s", name, exc)

            info.soul_summary = soul_summary
            info.config = config_data
            results.append(info)

        return results

    # ── Get detail ────────────────────────────────────────────────────

    @staticmethod
    async def get_profile(name: str) -> ProfileDetail:
        """Return detailed information about a single profile.

        Parameters
        ----------
        name : str
            Profile directory name.

        Returns
        -------
        ProfileDetail
            Full detail including complete ``SOUL.md`` content.

        Raises
        ------
        FileNotFoundError
            If the profile directory does not exist.
        """
        profile_dir = _profiles_dir() / name
        if not profile_dir.is_dir():
            raise FileNotFoundError(f"Profile '{name}' not found at {profile_dir}")

        status = await ProfileManager.get_profile_status(name)
        detail = ProfileDetail(
            name=name,
            running=status.running,
            pid=status.pid,
            port=status.port,
            profile_dir=str(profile_dir),
            config_path=str(profile_dir / "config.yaml"),
            soul_path=str(profile_dir / "SOUL.md"),
        )

        soul_path = profile_dir / "SOUL.md"
        if soul_path.is_file():
            try:
                detail.soul_full = await _read_text_sync(soul_path)
                detail.soul_summary = detail.soul_full[:200].replace("\n", " ").strip()
            except Exception as exc:
                logger.warning("Failed to read SOUL.md for %s: %s", name, exc)

        config_path = profile_dir / "config.yaml"
        if config_path.is_file():
            try:
                detail.config = await _read_yaml_sync(config_path)
            except Exception as exc:
                logger.warning("Failed to read config.yaml for %s: %s", name, exc)

        return detail

    # ── Create ────────────────────────────────────────────────────────

    @staticmethod
    async def create_profile(name: str, clone_from: str | None = None) -> str:
        """Create a new Hermes profile via the ``hermes profile create`` CLI.

        Parameters
        ----------
        name : str
            Name of the new profile (lowercase, alphanumeric).
        clone_from : str or None
            Source profile to clone configuration from.  If ``None``, the
            profile is created fresh.

        Returns
        -------
        str
            Stdout output from the CLI command.

        Raises
        ------
        RuntimeError
            If the CLI invocation fails.
        """
        args = ["profile", "create", name]
        if clone_from:
            args.extend(["--clone-from", clone_from])
        else:
            args.append("--no-alias")
        return await _run_hermes_cli(*args)

    # ── Delete ────────────────────────────────────────────────────────

    @staticmethod
    async def delete_profile(name: str) -> str:
        """Delete a Hermes profile via ``hermes profile delete``.

        Parameters
        ----------
        name : str
            Profile to delete.

        Returns
        -------
        str
            Stdout output from the CLI command.

        Raises
        ------
        RuntimeError
            If the CLI invocation fails.
        """
        # Stop if running
        if name in _running_processes:
            await ProfileManager.stop_profile(name)

        return await _run_hermes_cli("profile", "delete", name, "-y")

    # ── Start ─────────────────────────────────────────────────────────

    @staticmethod
    async def start_profile(name: str) -> int:
        """Start a profile as a background subprocess.

        The process is launched via ``hermes`` CLI with the profile name.
        The calling code is responsible for tracking the returned PID.

        Parameters
        ----------
        name : str
            Profile to start.

        Returns
        -------
        int
            Process ID (PID) of the started subprocess.

        Raises
        ------
        FileNotFoundError
            If the profile does not exist.
        RuntimeError
            If the profile is already running.
        """
        # Guard: profile must exist
        profile_dir = _profiles_dir() / name
        if not profile_dir.is_dir():
            raise FileNotFoundError(f"Profile '{name}' not found at {profile_dir}")

        # Guard: not already running
        if name in _running_processes:
            proc = _running_processes[name]
            if proc.poll() is None:
                raise RuntimeError(f"Profile '{name}' is already running (PID {proc.pid})")
            # Stale entry — clean up
            del _running_processes[name]

        hermes_bin = _find_hermes_cli()
        proc = subprocess.Popen(
            [hermes_bin, "agent", "--profile", name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(profile_dir),
        )
        _running_processes[name] = proc
        logger.info("Started profile '%s' with PID %d", name, proc.pid)

        # Give the process a moment to crash on obvious errors
        await asyncio.sleep(0.5)
        if proc.poll() is not None:
            del _running_processes[name]
            stderr_output = (
                proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            )
            raise RuntimeError(
                f"Profile '{name}' exited immediately (PID {proc.pid}):\n{stderr_output}"
            )

        return proc.pid

    # ── Stop ──────────────────────────────────────────────────────────

    @staticmethod
    async def stop_profile(name: str) -> None:
        """Stop a running profile by writing ``/exit`` to its stdin.

        If the process does not terminate gracefully within 5 seconds,
        it is killed with ``SIGTERM`` (and ``SIGKILL`` after another 3 s).

        Parameters
        ----------
        name : str
            Profile to stop.

        Raises
        ------
        RuntimeError
            If the profile is not currently tracked as running.
        """
        proc = _running_processes.get(name)
        if proc is None:
            raise RuntimeError(f"Profile '{name}' is not currently running")

        if proc.poll() is not None:
            # Already dead — clean up
            del _running_processes[name]
            return

        # Graceful shutdown: send /exit
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.write(b"/exit\n")
                proc.stdin.flush()
        except OSError:
            pass  # pipe may already be broken

        # Wait up to 5 seconds
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Profile '%s' did not exit gracefully, sending SIGTERM", name)
            if os.name == "nt":
                proc.terminate()
            else:
                os.kill(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logger.warning("Profile '%s' still alive, sending SIGKILL", name)
                proc.kill()
                proc.wait()

        del _running_processes[name]
        logger.info("Stopped profile '%s'", name)

    # ── Status ────────────────────────────────────────────────────────

    @staticmethod
    async def get_profile_status(name: str) -> ProfileInfo:
        """Check whether a profile is currently running.

        Detection uses two signals:

        1. **PID check** — looks up *name* in the in-memory process registry.
        2. **Port scan** — attempts to connect to known Hermes gateway ports
           within the profile's configured port range.

        Parameters
        ----------
        name : str
            Profile name.

        Returns
        -------
        ProfileInfo
            Status object with ``running``, ``pid``, and ``port`` fields.
        """
        info = ProfileInfo(name=name)

        # PID check
        proc = _running_processes.get(name)
        if proc is not None and proc.poll() is None:
            info.pid = proc.pid
        elif proc is not None:
            # Stale entry
            del _running_processes[name]

        # Port scan
        profile_dir = _profiles_dir() / name
        if profile_dir.is_dir():
            info.port = await _detect_port(profile_dir)

        info.running = info.pid is not None or info.port is not None

        # If we have a port but no PID, try to find the PID via port
        if info.port is not None and info.pid is None:
            try:
                if os.name == "nt":
                    result = await _run_subprocess_sync(["netstat", "-ano"], timeout=5)
                    for line in result.stdout.splitlines():
                        if f":{info.port}" in line and "LISTENING" in line:
                            parts = line.strip().split()
                            if parts:
                                info.pid = int(parts[-1])
                            break
                else:
                    result = await _run_subprocess_sync(
                        ["lsof", "-ti", f":{info.port}"], timeout=5
                    )
                    if result.stdout.strip():
                        info.pid = int(result.stdout.strip().splitlines()[0])
            except Exception:
                pass  # best-effort

        return info
