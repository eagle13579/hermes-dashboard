"""
Command Router — Hermes dashboard command routing service.

Routes terminal commands to the correct Hermes profile session,
with support for command registration, whitelist/blacklist filtering,
and profile-specific dispatch.

Architecture
------------
*L2 — Command Router*: 终端命令注入
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .session_manager import SessionManager

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Types
# ──────────────────────────────────────────────────────────────────────

CommandHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
"""
Signature for a registered command handler::

    def handler(command: str, context: dict[str, Any]) -> dict[str, Any]:
        ...

Parameters
----------
command : str
    The raw command string to execute.
context : dict[str, Any]
    Execution context (e.g. ``{"profile": "my-profile", "session_id": "..."}``).

Returns
-------
dict[str, Any]
    Result dictionary with at least a ``"output"`` key.
"""


# ──────────────────────────────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────────────────────────────


@dataclass
class CommandRule:
    """A single command routing rule.

    Attributes
    ----------
    pattern : str
        Regex pattern the command must match.
    handler : CommandHandler
        Callable invoked when the pattern matches.
    description : str
        Human-readable description of this rule.
    priority : int
        Priority for ordering (higher = checked first).
    allowed_profiles : list[str] | None
        If set, only route commands for these profile names.
    """

    pattern: str
    handler: CommandHandler
    description: str = ""
    priority: int = 0
    allowed_profiles: list[str] | None = None


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


class CommandRouter:
    """Routes terminal commands to the appropriate handler or profile.

    Features
    --------
    * Register named command patterns with associated handlers.
    * Whitelist / blacklist filtering by command or profile.
    * Fallback execution against the active session's profile.
    * Route caching for performance.

    Usage
    -----
    .. code-block:: python

        router = CommandRouter()

        def echo_handler(cmd, ctx):
            return {"output": cmd}

        router.register(r"^echo\\s+(.+)", echo_handler, "Echo command")
        router.set_whitelist(["echo", "help"])

        result = router.route("echo hello world", {"profile": "test"})
    """

    def __init__(self) -> None:
        self._rules: list[CommandRule] = []
        self._whitelist: set[str] | None = None
        """If not None, only commands whose first word is in this set pass."""
        self._blacklist: set[str] = set()
        """Commands whose first word matches are rejected immediately."""
        self._profile_blacklist: dict[str, set[str]] = {}
        """Per-profile command blacklist: ``{profile_name: {command_word, ...}}``."""

    # ── Whitelist / Blacklist ────────────────────────────────────────

    def set_whitelist(self, commands: list[str] | None) -> None:
        """Set the global command whitelist.

        When set, only commands whose first word appears in *commands*
        will be routed.  ``None`` or an empty list disables the whitelist.

        Parameters
        ----------
        commands : list[str] or None
            Allowed command first-words.
        """
        if commands:
            self._whitelist = set(cmd.strip().lower() for cmd in commands if cmd.strip())
        else:
            self._whitelist = None
        logger.debug(
            "CommandRouter whitelist %s",
            f"set to {sorted(self._whitelist)}" if self._whitelist else "disabled",
        )

    def add_to_blacklist(self, *commands: str) -> None:
        """Add one or more commands to the global blacklist.

        Parameters
        ----------
        *commands : str
            Command first-words to blacklist.
        """
        for cmd in commands:
            self._blacklist.add(cmd.strip().lower())
        logger.debug("CommandRouter blacklist: %s", sorted(self._blacklist))

    def remove_from_blacklist(self, *commands: str) -> None:
        """Remove one or more commands from the global blacklist.

        Parameters
        ----------
        *commands : str
            Command first-words to remove.
        """
        for cmd in commands:
            self._blacklist.discard(cmd.strip().lower())
        logger.debug("CommandRouter blacklist after removal: %s", sorted(self._blacklist))

    def add_profile_blacklist(self, profile: str, *commands: str) -> None:
        """Add command blacklist entries for a specific profile.

        Parameters
        ----------
        profile : str
            Profile name.
        *commands : str
            Command first-words to blacklist for this profile.
        """
        if profile not in self._profile_blacklist:
            self._profile_blacklist[profile] = set()
        for cmd in commands:
            self._profile_blacklist[profile].add(cmd.strip().lower())

    # ── Rule registration ────────────────────────────────────────────

    def register(
        self,
        pattern: str,
        handler: CommandHandler,
        description: str = "",
        priority: int = 0,
        allowed_profiles: list[str] | None = None,
    ) -> None:
        """Register a command pattern and its handler.

        Parameters
        ----------
        pattern : str
            Regex pattern the command must match (case-insensitive).
        handler : CommandHandler
            Callable receiving ``(command, context)``.
        description : str
            Human-readable description of this rule.
        priority : int
            Higher priority rules are checked first (default: 0).
        allowed_profiles : list[str] or None
            If set, this rule only fires for listed profile names.
        """
        rule = CommandRule(
            pattern=pattern,
            handler=handler,
            description=description,
            priority=priority,
            allowed_profiles=allowed_profiles,
        )
        self._rules.append(rule)
        # Sort by priority descending so higher-priority rules come first
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        logger.debug(
            "Registered command pattern '%s' (priority=%d) for profiles=%s",
            pattern,
            priority,
            allowed_profiles or "all",
        )

    def unregister(self, pattern: str) -> bool:
        """Remove a registered command pattern.

        Parameters
        ----------
        pattern : str
            The exact pattern to remove.

        Returns
        -------
        bool
            ``True`` if a rule was removed, ``False`` if not found.
        """
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.pattern != pattern]
        return len(self._rules) < before

    def get_rules(self) -> list[dict[str, Any]]:
        """Return all registered rules as dictionaries (for introspection).

        Returns
        -------
        list[dict[str, Any]]
            List of rule metadata.
        """
        return [
            {
                "pattern": r.pattern,
                "description": r.description,
                "priority": r.priority,
                "allowed_profiles": r.allowed_profiles,
            }
            for r in self._rules
        ]

    # ── Routing ──────────────────────────────────────────────────────

    def route(self, command: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route a command to the appropriate handler or profile.

        The routing order is:

        1. Global blacklist check (rejected immediately).
        2. Profile-specific blacklist check.
        3. Global whitelist check (if enabled).
        4. Registered rules (highest priority first).
        5. Fallback: if a ``profile`` is set in context, execute via
           the active session; otherwise return an error.

        Parameters
        ----------
        command : str
            The raw command string.
        context : dict[str, Any] or None
            Optional execution context (profile name, session ID, etc.).

        Returns
        -------
        dict[str, Any]
            Result with at least ``"output"`` and ``"success"`` keys.

        Examples
        --------
        >>> router = CommandRouter()
        >>> router.route("unknown-cmd", {"profile": "test"})
        {"output": "No handler matched. Executing as shell command...", "success": True}
        """
        ctx: dict[str, Any] = dict(context or {})
        command = command.strip()
        if not command:
            return {"output": "Empty command.", "success": False}

        first_word = command.split(maxsplit=1)[0].lower() if command else ""

        # 1. Global blacklist
        if first_word in self._blacklist:
            logger.warning("Command '%s' rejected by global blacklist", first_word)
            return {
                "output": f"Command '{first_word}' is blacklisted.",
                "success": False,
                "rejected": True,
            }

        # 2. Profile-specific blacklist
        profile = ctx.get("profile", "")
        if profile and profile in self._profile_blacklist:
            if first_word in self._profile_blacklist[profile]:
                logger.warning(
                    "Command '%s' rejected by profile blacklist for '%s'",
                    first_word,
                    profile,
                )
                return {
                    "output": f"Command '{first_word}' is blacklisted for profile '{profile}'.",
                    "success": False,
                    "rejected": True,
                }

        # 3. Global whitelist
        if self._whitelist is not None and first_word not in self._whitelist:
            return {
                "output": (
                    f"Command '{first_word}' is not in the whitelist. "
                    f"Allowed: {sorted(self._whitelist)}"
                ),
                "success": False,
                "rejected": True,
            }

        # 4. Registered rules (highest priority first)
        for rule in self._rules:
            # Profile restriction check
            if rule.allowed_profiles and profile not in rule.allowed_profiles:
                continue
            if re.search(rule.pattern, command, re.IGNORECASE):
                try:
                    return rule.handler(command, ctx)
                except Exception as exc:
                    logger.exception(
                        "Handler for pattern '%s' raised an exception", rule.pattern
                    )
                    return {
                        "output": f"Handler error: {exc}",
                        "success": False,
                    }

        # 5. Fallback: execute via session if a profile is known
        if profile:
            return self._fallback_exec(command, ctx)

        return {
            "output": (
                "No handler matched and no profile context provided. "
                "Set a 'profile' in the context to execute commands."
            ),
            "success": False,
        }

    # ── Fallback logic ───────────────────────────────────────────────

    @staticmethod
    def _fallback_exec(command: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a command against the active session as a fallback.

        Locates the most recent session for the profile, appends the
        command to its history, and returns a confirmation.

        Parameters
        ----------
        command : str
            Command to execute.
        context : dict[str, Any]
            Execution context with at least ``"profile"``.

        Returns
        -------
        dict[str, Any]
            Result dictionary.
        """
        profile = context.get("profile", "")
        session_id = context.get("session_id", "")

        # If a specific session is provided, use it; otherwise find the latest
        if session_id:
            try:
                session = SessionManager.touch_session(session_id)
            except KeyError:
                return {
                    "output": f"Session '{session_id}' not found.",
                    "success": False,
                }
        else:
            sessions = SessionManager.get_sessions_for_profile(profile)
            if not sessions:
                # Auto-create a session for this profile
                session = SessionManager.create_session(profile_name=profile)
            else:
                session = sessions[0]

        SessionManager.append_command(session.session_id, command)
        logger.info(
            "Fallback-executed command on session %s (profile=%s): %.80s",
            session.session_id,
            profile,
            command,
        )
        return {
            "output": f"Command routed to profile '{profile}' (session {session.session_id}).",
            "success": True,
            "session_id": session.session_id,
        }


# ──────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────

command_router: CommandRouter = CommandRouter()
"""Pre-initialised command router singleton.  Import this everywhere."""
