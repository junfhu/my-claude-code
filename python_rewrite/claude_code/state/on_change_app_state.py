"""
Side-effect handlers triggered on every state change.

This module implements the ``on_change`` callback wired into the store via
``create_store(initial_state, on_change_app_state)`` at bootstrap.  It is
called synchronously by ``Store.set_state`` *before* subscriber
notifications, which means:

    1. External systems (persistence, CCR sync, SDK status) are updated
       before any consumer re-reads the state.
    2. The function must be fast -- it runs on every single ``set_state``
       call.

The handler compares ``old_state`` vs ``new_state`` for specific fields
and triggers side-effects only when those fields actually changed.  This
is a centralised "diff & react" approach that replaces scattered manual
notification calls throughout the codebase.

Side-effects handled here:
    - Permission mode -> session metadata notification + SDK status stream
    - main_loop_model -> settings file + bootstrap override
    - expanded_view -> global config persistence (show_expanded_todos)
    - verbose -> global config persistence
    - settings -> clear auth caches + re-apply environment variables
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from .app_state import (
    AppState,
    PermissionMode,
    to_external_permission_mode,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Notification sinks -- pluggable callbacks for external system integration.
#
# These are set at bootstrap time (or left as no-ops for testing).
# The on_change handler calls them; it doesn't import their implementations
# directly, keeping this module a leaf in the import DAG.
# ---------------------------------------------------------------------------

_permission_mode_changed_callback: Callable[[PermissionMode], None] | None = None
_session_metadata_changed_callback: Callable[[dict[str, Any]], None] | None = None
_save_global_config_callback: Callable[[Callable[[dict[str, Any]], dict[str, Any]]], None] | None = None
_get_global_config_callback: Callable[[], dict[str, Any]] | None = None
_update_settings_for_source_callback: Callable[[str, dict[str, Any]], None] | None = None
_set_main_loop_model_override_callback: Callable[[str | None], None] | None = None
_clear_auth_caches_callback: Callable[[], None] | None = None
_apply_config_env_vars_callback: Callable[[], None] | None = None


def register_on_change_callbacks(
    *,
    permission_mode_changed: Callable[[PermissionMode], None] | None = None,
    session_metadata_changed: Callable[[dict[str, Any]], None] | None = None,
    save_global_config: Callable[[Callable[[dict[str, Any]], dict[str, Any]]], None] | None = None,
    get_global_config: Callable[[], dict[str, Any]] | None = None,
    update_settings_for_source: Callable[[str, dict[str, Any]], None] | None = None,
    set_main_loop_model_override: Callable[[str | None], None] | None = None,
    clear_auth_caches: Callable[[], None] | None = None,
    apply_config_env_vars: Callable[[], None] | None = None,
) -> None:
    """Register callback functions for side-effect handling.

    Call this during application bootstrap to wire up the concrete
    implementations of external-system interactions.  In tests, leave
    them unregistered -- the on_change handler will simply skip those
    side-effects.
    """
    global \
        _permission_mode_changed_callback, \
        _session_metadata_changed_callback, \
        _save_global_config_callback, \
        _get_global_config_callback, \
        _update_settings_for_source_callback, \
        _set_main_loop_model_override_callback, \
        _clear_auth_caches_callback, \
        _apply_config_env_vars_callback
    _permission_mode_changed_callback = permission_mode_changed
    _session_metadata_changed_callback = session_metadata_changed
    _save_global_config_callback = save_global_config
    _get_global_config_callback = get_global_config
    _update_settings_for_source_callback = update_settings_for_source
    _set_main_loop_model_override_callback = set_main_loop_model_override
    _clear_auth_caches_callback = clear_auth_caches
    _apply_config_env_vars_callback = apply_config_env_vars


# ---------------------------------------------------------------------------
# external_metadata_to_app_state -- Converts CCR external metadata back
# into an AppState updater function.
# ---------------------------------------------------------------------------

def external_metadata_to_app_state(
    metadata: dict[str, Any],
) -> Callable[[AppState], AppState]:
    """Convert CCR external metadata back into an AppState updater.

    This is the inverse of the metadata push in ``on_change_app_state``:
    when a worker process restarts, it reads the latest external_metadata
    from CCR and uses this function to restore the AppState fields
    (permission_mode, is_ultraplan_mode) that were previously pushed out.

    Returns a state updater function compatible with ``store.set_state()``.
    """
    from dataclasses import replace

    def updater(prev: AppState) -> AppState:
        updates: dict[str, Any] = {}

        permission_mode_str = metadata.get("permission_mode")
        if isinstance(permission_mode_str, str):
            try:
                new_mode = PermissionMode(permission_mode_str)
                updates["tool_permission_context"] = replace(
                    prev.tool_permission_context, mode=new_mode
                )
            except ValueError:
                pass  # Unknown mode string -- ignore

        is_ultraplan = metadata.get("is_ultraplan_mode")
        if isinstance(is_ultraplan, bool):
            updates["is_ultraplan_mode"] = is_ultraplan

        if not updates:
            return prev
        return replace(prev, **updates)

    return updater


# ---------------------------------------------------------------------------
# on_change_app_state -- The main side-effect handler.
# ---------------------------------------------------------------------------

def on_change_app_state(new_state: AppState, old_state: AppState) -> None:
    """Side-effect handler called on every actual state change.

    Wired as the ``on_change`` callback to ``create_store()`` at bootstrap.
    Called synchronously on every ``set_state`` that produces a new state
    reference.  Runs BEFORE subscriber notifications.

    Each block below handles one state field diff.  The pattern is::

        if new_state.X != old_state.X:
            # side-effect

    This ensures side-effects only fire when the relevant field actually
    changed, keeping the function efficient even though it runs on every
    state update.
    """

    # =====================================================================
    # 1. Permission mode sync -> CCR + SDK
    # =====================================================================
    prev_mode = old_state.tool_permission_context.mode
    new_mode = new_state.tool_permission_context.mode

    if prev_mode != new_mode:
        # External mode mapping -- internal modes like BUBBLE and
        # UNGATED_AUTO map to their external equivalents.
        prev_external = to_external_permission_mode(prev_mode)
        new_external = to_external_permission_mode(new_mode)

        if prev_external != new_external:
            # Ultraplan = first plan cycle only.
            is_ultraplan: bool | None = None
            if (
                new_external == "plan"
                and getattr(new_state, "is_ultraplan_mode", False)
                and not getattr(old_state, "is_ultraplan_mode", False)
            ):
                is_ultraplan = True

            if _session_metadata_changed_callback is not None:
                try:
                    _session_metadata_changed_callback({
                        "permission_mode": new_external,
                        "is_ultraplan_mode": is_ultraplan,
                    })
                except Exception:
                    logger.exception("Failed to notify session metadata change")

        if _permission_mode_changed_callback is not None:
            try:
                _permission_mode_changed_callback(new_mode)
            except Exception:
                logger.exception("Failed to notify permission mode change")

    # =====================================================================
    # 2. Model override -> settings file + bootstrap state
    # =====================================================================
    if new_state.main_loop_model != old_state.main_loop_model:
        if new_state.main_loop_model is None:
            # User cleared the model override -- remove from settings
            if _update_settings_for_source_callback is not None:
                try:
                    _update_settings_for_source_callback(
                        "userSettings", {"model": None}
                    )
                except Exception:
                    logger.exception("Failed to update settings (model cleared)")

            if _set_main_loop_model_override_callback is not None:
                try:
                    _set_main_loop_model_override_callback(None)
                except Exception:
                    logger.exception("Failed to clear model override")
        else:
            # User set a model override -- persist it
            if _update_settings_for_source_callback is not None:
                try:
                    _update_settings_for_source_callback(
                        "userSettings", {"model": new_state.main_loop_model}
                    )
                except Exception:
                    logger.exception("Failed to update settings (model set)")

            if _set_main_loop_model_override_callback is not None:
                try:
                    _set_main_loop_model_override_callback(
                        new_state.main_loop_model
                    )
                except Exception:
                    logger.exception("Failed to set model override")

    # =====================================================================
    # 3. Expanded view -> global config persistence
    # =====================================================================
    if new_state.expanded_view != old_state.expanded_view:
        show_expanded_todos = new_state.expanded_view == "tasks"
        show_spinner_tree = new_state.expanded_view == "teammates"

        if _get_global_config_callback is not None and _save_global_config_callback is not None:
            try:
                config = _get_global_config_callback()
                if (
                    config.get("show_expanded_todos") != show_expanded_todos
                    or config.get("show_spinner_tree") != show_spinner_tree
                ):
                    _save_global_config_callback(
                        lambda current: {
                            **current,
                            "show_expanded_todos": show_expanded_todos,
                            "show_spinner_tree": show_spinner_tree,
                        }
                    )
            except Exception:
                logger.exception("Failed to persist expanded view config")

    # =====================================================================
    # 4. Verbose mode -> global config persistence
    # =====================================================================
    if new_state.verbose != old_state.verbose:
        if _get_global_config_callback is not None and _save_global_config_callback is not None:
            try:
                config = _get_global_config_callback()
                if config.get("verbose") != new_state.verbose:
                    verbose_val = new_state.verbose
                    _save_global_config_callback(
                        lambda current: {**current, "verbose": verbose_val}
                    )
            except Exception:
                logger.exception("Failed to persist verbose config")

    # =====================================================================
    # 5. Tungsten panel visibility -> global config persistence
    # =====================================================================
    if (
        new_state.tungsten_panel_visible != old_state.tungsten_panel_visible
        and new_state.tungsten_panel_visible is not None
    ):
        if _get_global_config_callback is not None and _save_global_config_callback is not None:
            try:
                config = _get_global_config_callback()
                if config.get("tungsten_panel_visible") != new_state.tungsten_panel_visible:
                    tpv = new_state.tungsten_panel_visible
                    _save_global_config_callback(
                        lambda current: {
                            **current,
                            "tungsten_panel_visible": tpv,
                        }
                    )
            except Exception:
                logger.exception("Failed to persist tungsten panel config")

    # =====================================================================
    # 6. Settings change -> clear auth caches + re-apply env vars
    # =====================================================================
    if new_state.settings is not old_state.settings:
        try:
            if _clear_auth_caches_callback is not None:
                _clear_auth_caches_callback()

            # Re-apply environment variables when settings.env changes
            if (
                new_state.settings.get("env")
                != old_state.settings.get("env")
                and _apply_config_env_vars_callback is not None
            ):
                _apply_config_env_vars_callback()
        except Exception:
            logger.exception("Failed to handle settings change")

    # =====================================================================
    # 7. Theme change -> log for debugging
    # =====================================================================
    if new_state.theme != old_state.theme:
        logger.debug(
            "Theme changed: %s -> %s", old_state.theme, new_state.theme
        )


__all__ = [
    "external_metadata_to_app_state",
    "on_change_app_state",
    "register_on_change_callbacks",
]
