"""
Session state management.

This module holds the global bootstrap state for a Claude Code session.
It is intentionally a leaf in the import dependency graph -- no other
modules from the application should be imported here (except pure utility
types) to avoid circular imports.

The ``_State`` dataclass holds all session-level counters, IDs, and
configuration that persists for the lifetime of a single CLI invocation.
Access is provided via module-level getter/setter functions rather than
direct attribute access, so that:

    1. The state object is private and cannot be accidentally replaced.
    2. Callers get a clean, discoverable API (``get_session_id()`` vs
       ``STATE.session_id``).
    3. Thread safety can be added transparently if needed.

DO NOT ADD MORE STATE HERE -- BE JUDICIOUS WITH GLOBAL STATE.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Signal -- lightweight pub/sub for internal events
# ---------------------------------------------------------------------------

class Signal:
    """A simple synchronous signal (event emitter).

    Usage::

        sig = Signal()
        unsub = sig.subscribe(lambda *args: print(args))
        sig.emit("hello")
        unsub()
    """

    def __init__(self) -> None:
        self._listeners: list[Callable[..., None]] = []

    def subscribe(self, listener: Callable[..., None]) -> Callable[[], None]:
        """Register a listener.  Returns an unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def emit(self, *args: Any) -> None:
        """Fire the signal, calling all registered listeners."""
        for listener in list(self._listeners):
            listener(*args)

    def clear(self) -> None:
        """Remove all listeners."""
        self._listeners.clear()


# ---------------------------------------------------------------------------
# ModelUsage -- per-model token and cost counters
# ---------------------------------------------------------------------------

@dataclass
class ModelUsage:
    """Token and cost usage for a single model."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    web_search_requests: int = 0


# ---------------------------------------------------------------------------
# SettingSource
# ---------------------------------------------------------------------------

SettingSource = str  # "userSettings" | "projectSettings" | "localSettings" | "flagSettings" | "policySettings"

DEFAULT_ALLOWED_SETTING_SOURCES: list[SettingSource] = [
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
]


# ---------------------------------------------------------------------------
# _State dataclass
# ---------------------------------------------------------------------------

def _resolve_cwd() -> str:
    """Resolve the current working directory, following symlinks."""
    try:
        return str(Path(os.getcwd()).resolve())
    except OSError:
        return os.getcwd()


@dataclass
class _State:
    """Internal session state.

    This is the single mutable state object for the bootstrap layer.
    It is created once at module import time and reset only in tests.
    """
    # ---- Paths ----
    original_cwd: str = field(default_factory=_resolve_cwd)
    project_root: str = field(default_factory=_resolve_cwd)
    cwd: str = field(default_factory=_resolve_cwd)

    # ---- Cost & duration counters ----
    total_cost_usd: float = 0.0
    total_api_duration: float = 0.0
    total_api_duration_without_retries: float = 0.0
    total_tool_duration: float = 0.0
    turn_hook_duration_ms: float = 0.0
    turn_tool_duration_ms: float = 0.0
    turn_classifier_duration_ms: float = 0.0
    turn_tool_count: int = 0
    turn_hook_count: int = 0
    turn_classifier_count: int = 0

    # ---- Time tracking ----
    start_time: float = field(default_factory=time.time)
    last_interaction_time: float = field(default_factory=time.time)

    # ---- Lines changed ----
    total_lines_added: int = 0
    total_lines_removed: int = 0

    # ---- Model ----
    has_unknown_model_cost: bool = False
    model_usage: dict[str, ModelUsage] = field(default_factory=dict)
    main_loop_model_override: str | None = None
    initial_main_loop_model: str | None = None
    model_strings: dict[str, str] | None = None

    # ---- Session identity ----
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_session_id: str | None = None

    # ---- Flags ----
    is_interactive: bool = False
    kairos_active: bool = False
    strict_tool_result_pairing: bool = False
    sdk_agent_progress_summaries_enabled: bool = False
    user_msg_opt_in: bool = False
    client_type: str = "cli"
    session_source: str | None = None
    question_preview_format: str | None = None  # "markdown" | "html" | None
    flag_settings_path: str | None = None
    flag_settings_inline: dict[str, Any] | None = None
    allowed_setting_sources: list[str] = field(
        default_factory=lambda: list(DEFAULT_ALLOWED_SETTING_SOURCES)
    )

    # ---- Auth tokens ----
    session_ingress_token: str | None = None
    oauth_token_from_fd: str | None = None
    api_key_from_fd: str | None = None

    # ---- Agent state ----
    agent_color_map: dict[str, str] = field(default_factory=dict)
    agent_color_index: int = 0

    # ---- Debug / diagnostics ----
    last_api_request: dict[str, Any] | None = None
    last_api_request_messages: list[Any] | None = None
    last_classifier_requests: list[Any] | None = None
    cached_claude_md_content: str | None = None
    in_memory_error_log: list[dict[str, str]] = field(default_factory=list)

    # ---- Session-only flags ----
    inline_plugins: list[str] = field(default_factory=list)
    chrome_flag_override: bool | None = None
    use_cowork_plugins: bool = False
    session_bypass_permissions_mode: bool = False
    scheduled_tasks_enabled: bool = False
    session_cron_tasks: list[Any] = field(default_factory=list)
    session_created_teams: set[str] = field(default_factory=set)
    session_trust_accepted: bool = False
    session_persistence_disabled: bool = False
    has_exited_plan_mode: bool = False
    needs_plan_mode_exit_attachment: bool = False
    needs_auto_mode_exit_attachment: bool = False
    lsp_recommendation_shown_this_session: bool = False

    # ---- SDK state ----
    init_json_schema: dict[str, Any] | None = None
    registered_hooks: dict[str, list[Any]] | None = None
    sdk_betas: list[str] | None = None

    # ---- Caches ----
    plan_slug_cache: dict[str, str] = field(default_factory=dict)
    system_prompt_section_cache: dict[str, str | None] = field(
        default_factory=dict
    )
    invoked_skills: dict[str, dict[str, Any]] = field(default_factory=dict)

    # ---- Teleport / remote ----
    teleported_session_info: dict[str, Any] | None = None
    is_remote_mode: bool = False
    direct_connect_server_url: str | None = None

    # ---- Misc ----
    slow_operations: list[dict[str, Any]] = field(default_factory=list)
    main_thread_agent_type: str | None = None
    last_emitted_date: str | None = None
    additional_directories_for_claude_md: list[str] = field(
        default_factory=list
    )
    allowed_channels: list[dict[str, Any]] = field(default_factory=list)
    has_dev_channels: bool = False
    session_project_dir: str | None = None

    # ---- Prompt cache ----
    prompt_cache_1h_allowlist: list[str] | None = None
    prompt_cache_1h_eligible: bool | None = None
    afk_mode_header_latched: bool | None = None
    fast_mode_header_latched: bool | None = None
    cache_editing_header_latched: bool | None = None
    thinking_clear_latched: bool | None = None

    # ---- Request tracking ----
    prompt_id: str | None = None
    last_main_request_id: str | None = None
    last_api_completion_timestamp: float | None = None
    pending_post_compaction: bool = False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_STATE = _State()
_session_switched = Signal()

# Turn-level token tracking
_output_tokens_at_turn_start: int = 0
_current_turn_token_budget: int | None = None
_budget_continuation_count: int = 0


# ---------------------------------------------------------------------------
# Session identity
# ---------------------------------------------------------------------------

def get_session_id() -> str:
    """Return the current session ID (UUID string)."""
    return _STATE.session_id


def set_session_id(session_id: str) -> None:
    """Set the session ID directly.

    Prefer ``regenerate_session_id()`` or ``switch_session()`` in normal
    code paths; this is for bootstrap / restore scenarios.
    """
    _STATE.session_id = session_id


def regenerate_session_id(
    *, set_current_as_parent: bool = False,
) -> str:
    """Generate a new session ID, optionally recording the old one as parent.

    Returns the new session ID.
    """
    global _STATE
    if set_current_as_parent:
        _STATE.parent_session_id = _STATE.session_id
    _STATE.plan_slug_cache.pop(_STATE.session_id, None)
    _STATE.session_id = str(uuid.uuid4())
    _STATE.session_project_dir = None
    return _STATE.session_id


def get_parent_session_id() -> str | None:
    """Return the parent session ID, if any."""
    return _STATE.parent_session_id


def switch_session(
    session_id: str,
    project_dir: str | None = None,
) -> None:
    """Atomically switch the active session.

    ``session_id`` and ``session_project_dir`` always change together so
    they cannot drift out of sync.

    Args:
        session_id: The new session ID.
        project_dir: Directory containing the session's ``.jsonl``.
            Pass ``None`` for sessions in the current project.
    """
    _STATE.plan_slug_cache.pop(_STATE.session_id, None)
    _STATE.session_id = session_id
    _STATE.session_project_dir = project_dir
    _session_switched.emit(session_id)


def on_session_switch(
    callback: Callable[[str], None],
) -> Callable[[], None]:
    """Register a callback for session switches.  Returns unsubscribe."""
    return _session_switched.subscribe(callback)


def get_session_project_dir() -> str | None:
    """Session transcript directory, or ``None`` for current project."""
    return _STATE.session_project_dir


# ---------------------------------------------------------------------------
# Working directory
# ---------------------------------------------------------------------------

def get_original_cwd() -> str:
    """Return the original working directory at session start."""
    return _STATE.original_cwd


def set_original_cwd(cwd: str) -> None:
    """Update the original CWD (normalised)."""
    _STATE.original_cwd = str(Path(cwd).resolve())


def get_project_root() -> str:
    """Return the stable project root (set once at startup).

    Unlike ``get_original_cwd()``, this is never updated by mid-session
    worktree changes.  Use for project identity (history, skills, sessions),
    not file operations.
    """
    return _STATE.project_root


def set_project_root(cwd: str) -> None:
    """Set the project root (only for ``--worktree`` startup flag)."""
    _STATE.project_root = str(Path(cwd).resolve())


def get_cwd() -> str:
    """Return the current working directory."""
    return _STATE.cwd


def set_cwd(cwd: str) -> None:
    """Update the current working directory (normalised)."""
    _STATE.cwd = str(Path(cwd).resolve())


# ---------------------------------------------------------------------------
# Cost & duration
# ---------------------------------------------------------------------------

def add_to_total_duration(
    duration: float,
    duration_without_retries: float,
) -> None:
    """Add to the cumulative API duration counters."""
    _STATE.total_api_duration += duration
    _STATE.total_api_duration_without_retries += duration_without_retries


def add_to_total_cost(
    cost: float,
    model_usage: ModelUsage,
    model: str,
) -> None:
    """Add to the cumulative cost and per-model usage."""
    _STATE.model_usage[model] = model_usage
    _STATE.total_cost_usd += cost


def get_total_cost_usd() -> float:
    return _STATE.total_cost_usd


def get_total_api_duration() -> float:
    return _STATE.total_api_duration


def get_total_duration() -> float:
    """Wall-clock duration since session start (seconds)."""
    return time.time() - _STATE.start_time


def get_total_api_duration_without_retries() -> float:
    return _STATE.total_api_duration_without_retries


def get_total_tool_duration() -> float:
    return _STATE.total_tool_duration


def add_to_tool_duration(duration: float) -> None:
    _STATE.total_tool_duration += duration
    _STATE.turn_tool_duration_ms += duration
    _STATE.turn_tool_count += 1


# ---------------------------------------------------------------------------
# Turn-level counters
# ---------------------------------------------------------------------------

def get_turn_hook_duration_ms() -> float:
    return _STATE.turn_hook_duration_ms


def add_to_turn_hook_duration(duration: float) -> None:
    _STATE.turn_hook_duration_ms += duration
    _STATE.turn_hook_count += 1


def reset_turn_hook_duration() -> None:
    _STATE.turn_hook_duration_ms = 0.0
    _STATE.turn_hook_count = 0


def get_turn_hook_count() -> int:
    return _STATE.turn_hook_count


def get_turn_tool_duration_ms() -> float:
    return _STATE.turn_tool_duration_ms


def reset_turn_tool_duration() -> None:
    _STATE.turn_tool_duration_ms = 0.0
    _STATE.turn_tool_count = 0


def get_turn_tool_count() -> int:
    return _STATE.turn_tool_count


def get_turn_classifier_duration_ms() -> float:
    return _STATE.turn_classifier_duration_ms


def add_to_turn_classifier_duration(duration: float) -> None:
    _STATE.turn_classifier_duration_ms += duration
    _STATE.turn_classifier_count += 1


def reset_turn_classifier_duration() -> None:
    _STATE.turn_classifier_duration_ms = 0.0
    _STATE.turn_classifier_count = 0


def get_turn_classifier_count() -> int:
    return _STATE.turn_classifier_count


# ---------------------------------------------------------------------------
# Lines changed
# ---------------------------------------------------------------------------

def add_to_total_lines_changed(added: int, removed: int) -> None:
    _STATE.total_lines_added += added
    _STATE.total_lines_removed += removed


def get_total_lines_added() -> int:
    return _STATE.total_lines_added


def get_total_lines_removed() -> int:
    return _STATE.total_lines_removed


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

def get_total_input_tokens() -> int:
    return sum(u.input_tokens for u in _STATE.model_usage.values())


def get_total_output_tokens() -> int:
    return sum(u.output_tokens for u in _STATE.model_usage.values())


def get_total_cache_read_input_tokens() -> int:
    return sum(u.cache_read_input_tokens for u in _STATE.model_usage.values())


def get_total_cache_creation_input_tokens() -> int:
    return sum(
        u.cache_creation_input_tokens for u in _STATE.model_usage.values()
    )


def get_total_web_search_requests() -> int:
    return sum(u.web_search_requests for u in _STATE.model_usage.values())


# ---------------------------------------------------------------------------
# Turn token budget
# ---------------------------------------------------------------------------

def get_turn_output_tokens() -> int:
    return get_total_output_tokens() - _output_tokens_at_turn_start


def get_current_turn_token_budget() -> int | None:
    return _current_turn_token_budget


def snapshot_output_tokens_for_turn(budget: int | None) -> None:
    global _output_tokens_at_turn_start, _current_turn_token_budget, _budget_continuation_count
    _output_tokens_at_turn_start = get_total_output_tokens()
    _current_turn_token_budget = budget
    _budget_continuation_count = 0


def get_budget_continuation_count() -> int:
    return _budget_continuation_count


def increment_budget_continuation_count() -> None:
    global _budget_continuation_count
    _budget_continuation_count += 1


# ---------------------------------------------------------------------------
# Model override
# ---------------------------------------------------------------------------

def get_main_loop_model_override() -> str | None:
    return _STATE.main_loop_model_override


def set_main_loop_model_override(model: str | None) -> None:
    _STATE.main_loop_model_override = model


def get_initial_main_loop_model() -> str | None:
    return _STATE.initial_main_loop_model


def set_initial_main_loop_model(model: str | None) -> None:
    _STATE.initial_main_loop_model = model


# ---------------------------------------------------------------------------
# Model strings
# ---------------------------------------------------------------------------

def get_model_strings() -> dict[str, str] | None:
    return _STATE.model_strings


def set_model_strings(model_strings: dict[str, str]) -> None:
    _STATE.model_strings = model_strings


# ---------------------------------------------------------------------------
# Interaction time
# ---------------------------------------------------------------------------

_interaction_time_dirty = False


def update_last_interaction_time(immediate: bool = False) -> None:
    """Mark that a user interaction occurred.

    By default the actual ``time.time()`` call is deferred until
    ``flush_interaction_time()`` is called, so we avoid calling it on
    every single keypress.  Pass ``immediate=True`` for code that runs
    after a render cycle.
    """
    global _interaction_time_dirty
    if immediate:
        _flush_interaction_time_inner()
    else:
        _interaction_time_dirty = True


def flush_interaction_time() -> None:
    """If an interaction was recorded since the last flush, update now."""
    if _interaction_time_dirty:
        _flush_interaction_time_inner()


def _flush_interaction_time_inner() -> None:
    global _interaction_time_dirty
    _STATE.last_interaction_time = time.time()
    _interaction_time_dirty = False


def get_last_interaction_time() -> float:
    return _STATE.last_interaction_time


# ---------------------------------------------------------------------------
# Unknown model cost
# ---------------------------------------------------------------------------

def set_has_unknown_model_cost() -> None:
    _STATE.has_unknown_model_cost = True


def has_unknown_model_cost() -> bool:
    return _STATE.has_unknown_model_cost


# ---------------------------------------------------------------------------
# Request tracking
# ---------------------------------------------------------------------------

def get_last_main_request_id() -> str | None:
    return _STATE.last_main_request_id


def set_last_main_request_id(request_id: str) -> None:
    _STATE.last_main_request_id = request_id


def get_last_api_completion_timestamp() -> float | None:
    return _STATE.last_api_completion_timestamp


def set_last_api_completion_timestamp(timestamp: float) -> None:
    _STATE.last_api_completion_timestamp = timestamp


def mark_post_compaction() -> None:
    """Mark that a compaction just occurred."""
    _STATE.pending_post_compaction = True


def consume_post_compaction() -> bool:
    """Consume the post-compaction flag (returns True once after compaction)."""
    was = _STATE.pending_post_compaction
    _STATE.pending_post_compaction = False
    return was


# ---------------------------------------------------------------------------
# Direct connect
# ---------------------------------------------------------------------------

def get_direct_connect_server_url() -> str | None:
    return _STATE.direct_connect_server_url


def set_direct_connect_server_url(url: str) -> None:
    _STATE.direct_connect_server_url = url


# ---------------------------------------------------------------------------
# Additional directories
# ---------------------------------------------------------------------------

def get_additional_directories_for_claude_md() -> list[str]:
    return _STATE.additional_directories_for_claude_md


def set_additional_directories_for_claude_md(dirs: list[str]) -> None:
    _STATE.additional_directories_for_claude_md = dirs


# ---------------------------------------------------------------------------
# Cached CLAUDE.md content
# ---------------------------------------------------------------------------

def get_cached_claude_md_content() -> str | None:
    return _STATE.cached_claude_md_content


def set_cached_claude_md_content(content: str | None) -> None:
    _STATE.cached_claude_md_content = content


# ---------------------------------------------------------------------------
# Model usage
# ---------------------------------------------------------------------------

def get_model_usage() -> dict[str, ModelUsage]:
    return _STATE.model_usage


def get_usage_for_model(model: str) -> ModelUsage | None:
    return _STATE.model_usage.get(model)


# ---------------------------------------------------------------------------
# SDK betas
# ---------------------------------------------------------------------------

def get_sdk_betas() -> list[str] | None:
    return _STATE.sdk_betas


def set_sdk_betas(betas: list[str] | None) -> None:
    _STATE.sdk_betas = betas


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def reset_cost_state() -> None:
    """Reset all cost and duration counters (e.g. on /clear)."""
    _STATE.total_cost_usd = 0.0
    _STATE.total_api_duration = 0.0
    _STATE.total_api_duration_without_retries = 0.0
    _STATE.total_tool_duration = 0.0
    _STATE.start_time = time.time()
    _STATE.total_lines_added = 0
    _STATE.total_lines_removed = 0
    _STATE.has_unknown_model_cost = False
    _STATE.model_usage = {}
    _STATE.prompt_id = None


def set_cost_state_for_restore(
    *,
    total_cost_usd: float,
    total_api_duration: float,
    total_api_duration_without_retries: float,
    total_tool_duration: float,
    total_lines_added: int,
    total_lines_removed: int,
    last_duration: float | None = None,
    model_usage: dict[str, ModelUsage] | None = None,
) -> None:
    """Restore cost state from a persisted session."""
    _STATE.total_cost_usd = total_cost_usd
    _STATE.total_api_duration = total_api_duration
    _STATE.total_api_duration_without_retries = total_api_duration_without_retries
    _STATE.total_tool_duration = total_tool_duration
    _STATE.total_lines_added = total_lines_added
    _STATE.total_lines_removed = total_lines_removed
    if model_usage is not None:
        _STATE.model_usage = model_usage
    if last_duration is not None:
        _STATE.start_time = time.time() - last_duration


def reset_state_for_tests() -> None:
    """Reset all state to defaults (ONLY for use in tests)."""
    global _STATE, _output_tokens_at_turn_start, _current_turn_token_budget, _budget_continuation_count
    if os.environ.get("NODE_ENV") != "test" and not os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("reset_state_for_tests can only be called in tests")
    _STATE = _State()
    _output_tokens_at_turn_start = 0
    _current_turn_token_budget = None
    _budget_continuation_count = 0
    _session_switched.clear()


__all__ = [
    "ModelUsage",
    "Signal",
    "add_to_tool_duration",
    "add_to_total_cost",
    "add_to_total_duration",
    "add_to_total_lines_changed",
    "add_to_turn_classifier_duration",
    "add_to_turn_hook_duration",
    "consume_post_compaction",
    "flush_interaction_time",
    "get_additional_directories_for_claude_md",
    "get_budget_continuation_count",
    "get_cached_claude_md_content",
    "get_current_turn_token_budget",
    "get_cwd",
    "get_direct_connect_server_url",
    "get_initial_main_loop_model",
    "get_last_api_completion_timestamp",
    "get_last_interaction_time",
    "get_last_main_request_id",
    "get_main_loop_model_override",
    "get_model_strings",
    "get_model_usage",
    "get_original_cwd",
    "get_parent_session_id",
    "get_project_root",
    "get_sdk_betas",
    "get_session_id",
    "get_session_project_dir",
    "get_total_api_duration",
    "get_total_api_duration_without_retries",
    "get_total_cache_creation_input_tokens",
    "get_total_cache_read_input_tokens",
    "get_total_cost_usd",
    "get_total_duration",
    "get_total_input_tokens",
    "get_total_lines_added",
    "get_total_lines_removed",
    "get_total_output_tokens",
    "get_total_tool_duration",
    "get_total_web_search_requests",
    "get_turn_classifier_count",
    "get_turn_classifier_duration_ms",
    "get_turn_hook_count",
    "get_turn_hook_duration_ms",
    "get_turn_output_tokens",
    "get_turn_tool_count",
    "get_turn_tool_duration_ms",
    "get_usage_for_model",
    "has_unknown_model_cost",
    "increment_budget_continuation_count",
    "mark_post_compaction",
    "on_session_switch",
    "regenerate_session_id",
    "reset_cost_state",
    "reset_state_for_tests",
    "reset_turn_classifier_duration",
    "reset_turn_hook_duration",
    "reset_turn_tool_duration",
    "set_additional_directories_for_claude_md",
    "set_cached_claude_md_content",
    "set_cost_state_for_restore",
    "set_cwd",
    "set_direct_connect_server_url",
    "set_has_unknown_model_cost",
    "set_initial_main_loop_model",
    "set_last_api_completion_timestamp",
    "set_last_main_request_id",
    "set_main_loop_model_override",
    "set_model_strings",
    "set_original_cwd",
    "set_project_root",
    "set_sdk_betas",
    "set_session_id",
    "set_cwd",
    "snapshot_output_tokens_for_turn",
    "switch_session",
    "update_last_interaction_time",
]
