"""
Configuration editor screen.

Provides a full-screen, interactive editor for Claude Code settings.
Reads from and writes to ``~/.claude/config.json`` and project-level
``.claude/config.json``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
    Switch,
)


# ---------------------------------------------------------------------------
# Config schema definition
# ---------------------------------------------------------------------------

_CONFIG_SECTIONS: List[Dict[str, Any]] = [
    {
        "name": "General",
        "icon": "⚙️",
        "settings": [
            {
                "key": "model",
                "label": "Default model",
                "type": "choice",
                "choices": [
                    "claude-sonnet-4-20250514",
                    "claude-opus-4-20250514",
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                ],
                "default": "claude-sonnet-4-20250514",
                "description": "The default model to use for conversations.",
            },
            {
                "key": "permission_mode",
                "label": "Permission mode",
                "type": "choice",
                "choices": ["default", "plan", "auto-edit", "full-auto"],
                "default": "default",
                "description": "Controls when Claude asks for permission before executing tools.",
            },
            {
                "key": "max_turns",
                "label": "Max turns (headless)",
                "type": "number",
                "default": 100,
                "description": "Maximum number of agentic turns in headless mode.",
            },
            {
                "key": "vim_mode",
                "label": "Vim mode",
                "type": "bool",
                "default": False,
                "description": "Enable vim keybindings in the input widget.",
            },
        ],
    },
    {
        "name": "Appearance",
        "icon": "🎨",
        "settings": [
            {
                "key": "theme",
                "label": "Color theme",
                "type": "choice",
                "choices": ["dark", "light", "monokai", "solarized", "dracula"],
                "default": "dark",
                "description": "Terminal color theme.",
            },
            {
                "key": "show_token_count",
                "label": "Show token count",
                "type": "bool",
                "default": True,
                "description": "Display token count in the status bar.",
            },
            {
                "key": "show_cost",
                "label": "Show cost",
                "type": "bool",
                "default": True,
                "description": "Display accumulated cost in the status bar.",
            },
            {
                "key": "compact_messages",
                "label": "Compact messages",
                "type": "bool",
                "default": False,
                "description": "Use a more compact message display format.",
            },
        ],
    },
    {
        "name": "Privacy",
        "icon": "🔒",
        "settings": [
            {
                "key": "telemetry",
                "label": "Telemetry",
                "type": "bool",
                "default": True,
                "description": "Send anonymous usage telemetry to Anthropic.",
            },
            {
                "key": "save_history",
                "label": "Save history",
                "type": "bool",
                "default": True,
                "description": "Persist conversation history to disk.",
            },
        ],
    },
    {
        "name": "Advanced",
        "icon": "🔧",
        "settings": [
            {
                "key": "api_base_url",
                "label": "API base URL",
                "type": "string",
                "default": "https://api.anthropic.com",
                "description": "Base URL for the Anthropic API.",
            },
            {
                "key": "max_context_tokens",
                "label": "Max context tokens",
                "type": "number",
                "default": 200000,
                "description": "Maximum context window size.",
            },
            {
                "key": "auto_compact_threshold",
                "label": "Auto-compact threshold",
                "type": "number",
                "default": 0,
                "description": "Auto-compact when context exceeds this token count (0 = disabled).",
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Config screen
# ---------------------------------------------------------------------------


class ConfigScreen(Screen):
    """
    Full-screen configuration editor.

    Layout:
      - Left: section list (General, Appearance, Privacy, Advanced)
      - Right: settings for the selected section
    """

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("q", "pop_screen", "Back", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
    ]

    CSS = """
    ConfigScreen {
        background: $surface;
    }

    #config-container {
        height: 1fr;
        layout: horizontal;
    }

    #section-list {
        width: 24;
        height: 1fr;
        border-right: solid $accent;
        padding: 1;
    }

    #section-list ListView {
        height: 1fr;
    }

    #settings-panel {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }

    .setting-row {
        height: auto;
        padding: 1 0;
        border-bottom: dashed $surface-darken-1;
    }

    .setting-label {
        height: 1;
        padding: 0;
    }

    .setting-description {
        height: auto;
        padding: 0;
        color: $text-muted;
    }

    .setting-input {
        height: auto;
        margin-top: 1;
    }

    #save-status {
        height: 1;
        padding: 0 2;
        dock: bottom;
    }

    #config-scope-bar {
        height: 1;
        padding: 0 2;
        background: $accent-darken-3;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config: Dict[str, Any] = {}
        self._modified: Dict[str, Any] = {}
        self._current_section: int = 0
        self._config_path = Path.home() / ".claude" / "config.json"
        self._scope = "user"  # "user" or "project"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            Text.from_markup(
                "  [bold]Configuration[/bold]  "
                "[dim]|[/dim]  Scope: [cyan]User (~/.claude/config.json)[/cyan]  "
                "[dim]|[/dim]  [bold]Ctrl+S[/bold] to save"
            ),
            id="config-scope-bar",
        )
        with Horizontal(id="config-container"):
            with Vertical(id="section-list"):
                yield ListView(
                    *[
                        ListItem(
                            Label(f"{sec['icon']}  {sec['name']}"),
                            id=f"section-{i}",
                        )
                        for i, sec in enumerate(_CONFIG_SECTIONS)
                    ],
                    id="section-listview",
                )
            yield VerticalScroll(id="settings-panel")
        yield Static("", id="save-status")
        yield Footer()

    async def on_mount(self) -> None:
        """Load config and render initial section."""
        self._load_config()
        await self._render_section(0)

    def _load_config(self) -> None:
        """Load the config file."""
        if self._config_path.is_file():
            try:
                self._config = json.loads(self._config_path.read_text())
            except Exception:
                self._config = {}
        else:
            self._config = {}

    def _get_value(self, key: str, default: Any = None) -> Any:
        """Get a config value (modified takes precedence)."""
        if key in self._modified:
            return self._modified[key]
        return self._config.get(key, default)

    @on(ListView.Selected, "#section-listview")
    async def on_section_selected(self, event: ListView.Selected) -> None:
        """Handle section selection."""
        idx = event.list_view.index
        if idx is not None:
            await self._render_section(idx)

    async def _render_section(self, index: int) -> None:
        """Render the settings for a section."""
        self._current_section = index
        section = _CONFIG_SECTIONS[index]

        try:
            panel = self.query_one("#settings-panel", VerticalScroll)
        except NoMatches:
            return

        await panel.remove_children()

        # Section header
        await panel.mount(
            Static(Text.from_markup(
                f"[bold]{section['icon']}  {section['name']}[/bold]"
            ))
        )

        for setting in section["settings"]:
            widget = self._create_setting_widget(setting)
            await panel.mount(widget)

    def _create_setting_widget(self, setting: Dict[str, Any]) -> Widget:
        """Create the appropriate widget for a setting."""
        key = setting["key"]
        label = setting["label"]
        desc = setting["description"]
        stype = setting["type"]
        default = setting.get("default")
        current = self._get_value(key, default)

        container = Vertical(classes="setting-row")

        # We build the contents imperatively since Vertical.compose is already done
        # Return a Static that renders the full setting
        return _SettingWidget(
            key=key,
            label=label,
            description=desc,
            setting_type=stype,
            value=current,
            choices=setting.get("choices"),
            on_change=self._on_setting_change,
        )

    def _on_setting_change(self, key: str, value: Any) -> None:
        """Called when a setting value changes."""
        self._modified[key] = value
        try:
            status = self.query_one("#save-status", Static)
            status.update(Text.from_markup(
                f"[yellow]⚠ Unsaved changes ({len(self._modified)} modified)[/yellow]"
            ))
        except NoMatches:
            pass

    def action_save(self) -> None:
        """Save the configuration."""
        if not self._modified:
            return

        # Merge modifications
        self._config.update(self._modified)

        # Write to disk
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(self._config, indent=2, sort_keys=True)
            )
            self._modified.clear()

            try:
                status = self.query_one("#save-status", Static)
                status.update(Text.from_markup(
                    f"[green]✔ Configuration saved to {self._config_path}[/green]"
                ))
            except NoMatches:
                pass
        except Exception as exc:
            try:
                status = self.query_one("#save-status", Static)
                status.update(Text.from_markup(f"[red]✖ Save failed: {exc}[/red]"))
            except NoMatches:
                pass

    def action_pop_screen(self) -> None:
        """Return to the REPL, warning if unsaved changes."""
        if self._modified:
            # In a full implementation we'd show a confirmation dialog
            pass
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Setting widget (inline rendered)
# ---------------------------------------------------------------------------

from textual.widget import Widget  # noqa: E402 (needed for class below)


class _SettingWidget(Widget):
    """Renders a single configuration setting with label, description, and input."""

    DEFAULT_CSS = """
    _SettingWidget {
        height: auto;
        padding: 1 0;
        border-bottom: dashed $surface-darken-1;
    }
    """

    def __init__(
        self,
        key: str,
        label: str,
        description: str,
        setting_type: str,
        value: Any,
        choices: Optional[List[str]] = None,
        on_change: Any = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._key = key
        self._label = label
        self._description = description
        self._type = setting_type
        self._value = value
        self._choices = choices
        self._on_change = on_change

    def compose(self) -> ComposeResult:
        yield Static(Text.from_markup(
            f"[bold]{self._label}[/bold]  [dim]{self._description}[/dim]"
        ))

        if self._type == "bool":
            yield Switch(value=bool(self._value), id=f"switch-{self._key}")
        elif self._type == "choice" and self._choices:
            yield Select(
                [(c, c) for c in self._choices],
                value=self._value,
                id=f"select-{self._key}",
            )
        elif self._type == "number":
            yield Input(
                value=str(self._value or ""),
                type="number",
                id=f"input-{self._key}",
            )
        else:
            yield Input(
                value=str(self._value or ""),
                id=f"input-{self._key}",
            )

    @on(Switch.Changed)
    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._on_change:
            self._on_change(self._key, event.value)

    @on(Select.Changed)
    def on_select_changed(self, event: Select.Changed) -> None:
        if self._on_change:
            self._on_change(self._key, event.value)

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        if self._on_change:
            val = event.value
            if self._type == "number":
                try:
                    val = int(val) if val else 0
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        return
            self._on_change(self._key, val)
