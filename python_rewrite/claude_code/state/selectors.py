"""
Pure derived-state selectors for AppState.

Selectors are pure functions that compute derived values from the AppState
atom.  They encapsulate common lookup + validation patterns so that multiple
consumers (TUI components, REPL logic, input routing) share one canonical
implementation rather than duplicating task-lookup boilerplate.

Design principles:
    1. Pure -- no side effects, no mutations, no I/O.
    2. Minimal -- accept only the AppState slices they need (via Protocol /
       TypedDict), so callers can pass partial mocks in tests.
    3. Type-safe -- return discriminated unions so callers can narrow with
       pattern matching and get exhaustive checking.

These selectors are NOT framework hooks.  They can be used in any context:
    - Inside reactive subscriptions for rendering
    - In imperative code with ``store.get_state()``
    - In tests with plain objects
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from .app_state import AppState, PermissionMode, ToolPermissionContext


# ---------------------------------------------------------------------------
# Task type guards
# ---------------------------------------------------------------------------

def is_in_process_teammate_task(task: dict[str, Any]) -> bool:
    """Check whether a task dict represents an in-process teammate task."""
    return task.get("type") == "in_process_teammate"


def is_local_agent_task(task: dict[str, Any]) -> bool:
    """Check whether a task dict represents a local agent task."""
    return task.get("type") == "local_agent"


# ---------------------------------------------------------------------------
# ActiveAgentForInput -- Discriminated union describing where user input
# should be directed.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActiveAgentLeader:
    """Input goes to the main leader agent (default)."""
    type: Literal["leader"] = "leader"


@dataclass(frozen=True)
class ActiveAgentViewed:
    """Input goes to the in-process teammate being viewed."""
    type: Literal["viewed"] = "viewed"
    task: dict[str, Any] = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ActiveAgentNamed:
    """Input goes to a local agent task (non-teammate subagent)."""
    type: Literal["named_agent"] = "named_agent"
    task: dict[str, Any] = None  # type: ignore[assignment]


ActiveAgentForInput = ActiveAgentLeader | ActiveAgentViewed | ActiveAgentNamed


# ---------------------------------------------------------------------------
# get_viewed_teammate_task
# ---------------------------------------------------------------------------

def get_viewed_teammate_task(
    app_state: AppState,
) -> dict[str, Any] | None:
    """Get the currently viewed teammate task, if any.

    Returns ``None`` if:
        - No teammate is being viewed (``viewing_agent_task_id`` is None)
        - The task ID doesn't exist in tasks
        - The task is not an in-process teammate task

    This is a 3-step validation pipeline:
        1. Is viewing_agent_task_id set? (are we viewing anyone?)
        2. Does the ID map to an existing task? (guard against stale IDs)
        3. Is that task an in-process teammate? (not a local-agent or other type)
    """
    viewing_id = app_state.viewing_agent_task_id

    # Not viewing any teammate
    if viewing_id is None:
        return None

    # Look up the task
    task = app_state.tasks.get(viewing_id)
    if task is None:
        return None

    # Verify it's an in-process teammate task
    if not is_in_process_teammate_task(task):
        return None

    return task


# ---------------------------------------------------------------------------
# get_active_agent_for_input
# ---------------------------------------------------------------------------

def get_active_agent_for_input(
    app_state: AppState,
) -> ActiveAgentForInput:
    """Determine where user input should be routed.

    Resolution order:
        1. If viewing an in-process teammate -> route to that teammate
        2. If viewing a local agent task -> route to that named agent
        3. Otherwise -> route to the leader (default behaviour)

    This selector drives the input routing in the REPL: when a user types a
    message, the system needs to know whether to send it to the leader, a
    viewed teammate, or a named subagent.

    Returns:
        - ``ActiveAgentLeader()`` when not viewing a teammate
        - ``ActiveAgentViewed(task=...)`` when viewing an in-process teammate
        - ``ActiveAgentNamed(task=...)`` when viewing a local agent task
    """
    # First: check if we're viewing an in-process teammate
    viewed_task = get_viewed_teammate_task(app_state)
    if viewed_task is not None:
        return ActiveAgentViewed(task=viewed_task)

    # Second: check if we're viewing a local agent task (non-teammate subagent)
    viewing_id = app_state.viewing_agent_task_id
    if viewing_id is not None:
        task = app_state.tasks.get(viewing_id)
        if task is not None and is_local_agent_task(task):
            return ActiveAgentNamed(task=task)

    # Default: input goes to the leader
    return ActiveAgentLeader()


# ---------------------------------------------------------------------------
# get_effective_permission_mode
# ---------------------------------------------------------------------------

def get_effective_permission_mode(
    app_state: AppState,
) -> PermissionMode:
    """Get the effective permission mode, accounting for overrides.

    The effective mode resolves the current ``ToolPermissionContext.mode``
    after considering:
        - The base mode set by the user (default, plan, auto, bypass)
        - Session-level overrides (e.g. bypass permissions mode flag)

    This is the canonical way to determine the current permission mode
    for tool execution decisions.
    """
    return app_state.tool_permission_context.mode


# ---------------------------------------------------------------------------
# Convenience selectors
# ---------------------------------------------------------------------------

def get_current_model(app_state: AppState) -> str | None:
    """Get the currently configured model (alias or full name), or None."""
    return app_state.main_loop_model


def is_plan_mode(app_state: AppState) -> bool:
    """Check if the session is currently in plan mode."""
    return app_state.tool_permission_context.mode == PermissionMode.PLAN


def is_auto_mode(app_state: AppState) -> bool:
    """Check if the session is currently in auto/ungated-auto mode."""
    mode = app_state.tool_permission_context.mode
    return mode in (PermissionMode.AUTO, PermissionMode.UNGATED_AUTO)


def get_active_task_count(app_state: AppState) -> int:
    """Count tasks that are currently running (not completed/failed)."""
    return sum(
        1
        for task in app_state.tasks.values()
        if isinstance(task, dict)
        and task.get("status") in ("running", "pending")
    )


def has_active_speculation(app_state: AppState) -> bool:
    """Check if there is an active speculative execution in flight."""
    return getattr(app_state.speculation, "status", "idle") == "active"


__all__ = [
    "ActiveAgentForInput",
    "ActiveAgentLeader",
    "ActiveAgentNamed",
    "ActiveAgentViewed",
    "get_active_agent_for_input",
    "get_active_task_count",
    "get_current_model",
    "get_effective_permission_mode",
    "get_viewed_teammate_task",
    "has_active_speculation",
    "is_auto_mode",
    "is_in_process_teammate_task",
    "is_local_agent_task",
    "is_plan_mode",
]
