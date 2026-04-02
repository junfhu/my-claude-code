"""
Permission request dialog widget.

Displays a tool invocation that requires user approval, shows the tool
name, input parameters, and risk level, and collects the user's decision:
Allow, Deny, or Always Allow.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Static


# ---------------------------------------------------------------------------
# Risk level styling
# ---------------------------------------------------------------------------

_RISK_STYLES = {
    "low": ("green", "✔", "Low risk — read-only operation"),
    "medium": ("yellow", "⚠", "Medium risk — may modify files"),
    "high": ("red", "⛔", "High risk — potentially destructive"),
}


# ---------------------------------------------------------------------------
# Permission prompt widget
# ---------------------------------------------------------------------------


class PermissionPromptWidget(Widget):
    """
    A compact permission dialog that appears inline in the chat area.

    Displays:
      - Tool name and risk indicator
      - Formatted tool input (command, file path, etc.)
      - Three action buttons: Allow (y), Deny (n), Always Allow (a)

    Emits a :class:`PermissionDecision` message with the user's choice.
    """

    DEFAULT_CSS = """
    PermissionPromptWidget {
        height: auto;
        max-height: 20;
        margin: 0 1;
        padding: 0;
    }

    PermissionPromptWidget .perm-header {
        height: 1;
        padding: 0 1;
        background: $warning-darken-2;
        color: $text;
    }

    PermissionPromptWidget .perm-body {
        height: auto;
        max-height: 12;
        padding: 0 1;
        border: solid $warning;
        overflow-y: auto;
    }

    PermissionPromptWidget .perm-actions {
        height: 3;
        padding: 1 1;
        align: center middle;
    }

    PermissionPromptWidget Button {
        margin: 0 1;
        min-width: 16;
    }

    PermissionPromptWidget Button.allow-btn {
        background: $success;
    }

    PermissionPromptWidget Button.deny-btn {
        background: $error;
    }

    PermissionPromptWidget Button.always-btn {
        background: $primary;
    }
    """

    BINDINGS = [
        Binding("y", "allow", "Allow", show=True, priority=True),
        Binding("n", "deny", "Deny", show=True, priority=True),
        Binding("a", "always_allow", "Always Allow", show=True, priority=True),
        Binding("escape", "deny", "Deny", show=False),
    ]

    # Message emitted on decision
    class Decision(Message):
        """Emitted when the user makes a permission decision."""

        def __init__(self, tool_id: str, decision: str) -> None:
            super().__init__()
            self.tool_id = tool_id
            self.decision = decision  # "allow" | "deny" | "always_allow"

    def __init__(
        self,
        tool_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        risk_level: str = "medium",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tool_id = tool_id
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.risk_level = risk_level

    def compose(self):
        """Build the permission prompt layout."""
        color, icon, description = _RISK_STYLES.get(
            self.risk_level, _RISK_STYLES["medium"]
        )

        # Header
        yield Static(
            Text.from_markup(
                f"[bold {color}]{icon} Permission Required — {self.tool_name}[/bold {color}]"
                f"  [dim]({description})[/dim]"
            ),
            classes="perm-header",
        )

        # Body: tool input
        with Vertical(classes="perm-body"):
            yield Static(self._format_tool_input())

        # Action buttons
        with Horizontal(classes="perm-actions"):
            yield Button(
                "✔ Allow (y)",
                id="allow-btn",
                variant="success",
                classes="allow-btn",
            )
            yield Button(
                "✖ Deny (n)",
                id="deny-btn",
                variant="error",
                classes="deny-btn",
            )
            yield Button(
                "✔ Always Allow (a)",
                id="always-btn",
                variant="primary",
                classes="always-btn",
            )

    def _format_tool_input(self) -> Text:
        """Format the tool input for display in the permission dialog."""
        text = Text()

        if self.tool_name == "bash":
            cmd = self.tool_input.get("command", "")
            text.append("Command: ", style="bold")
            text.append(cmd, style="bold white")
        elif self.tool_name in ("file_write", "file_edit"):
            path = self.tool_input.get("file_path", self.tool_input.get("path", ""))
            text.append("File: ", style="bold")
            text.append(path, style="bold cyan")
            if self.tool_name == "file_edit":
                old_str = self.tool_input.get("old_string", "")
                new_str = self.tool_input.get("new_string", "")
                if old_str:
                    text.append("\nReplace: ", style="bold")
                    text.append(old_str[:100], style="red")
                    if len(old_str) > 100:
                        text.append("...", style="dim")
                if new_str:
                    text.append("\nWith: ", style="bold")
                    text.append(new_str[:100], style="green")
                    if len(new_str) > 100:
                        text.append("...", style="dim")
            elif self.tool_name == "file_write":
                content = self.tool_input.get("content", "")
                text.append(f"\nContent: ", style="bold")
                text.append(f"{len(content)} characters", style="dim")
        elif self.tool_name == "notebook_edit":
            path = self.tool_input.get("notebook_path", "")
            text.append("Notebook: ", style="bold")
            text.append(path, style="bold cyan")
        else:
            # Generic JSON display
            try:
                formatted = json.dumps(self.tool_input, indent=2, default=str)
                if len(formatted) > 500:
                    formatted = formatted[:500] + "\n..."
                text.append(formatted)
            except Exception:
                text.append(str(self.tool_input)[:500])

        return text

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#allow-btn")
    def on_allow(self, event: Button.Pressed) -> None:
        event.stop()
        self._emit_decision("allow")

    @on(Button.Pressed, "#deny-btn")
    def on_deny(self, event: Button.Pressed) -> None:
        event.stop()
        self._emit_decision("deny")

    @on(Button.Pressed, "#always-btn")
    def on_always_allow(self, event: Button.Pressed) -> None:
        event.stop()
        self._emit_decision("always_allow")

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def action_allow(self) -> None:
        self._emit_decision("allow")

    def action_deny(self) -> None:
        self._emit_decision("deny")

    def action_always_allow(self) -> None:
        self._emit_decision("always_allow")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_decision(self, decision: str) -> None:
        """Post the decision message and signal the parent REPL."""
        self.post_message(self.Decision(tool_id=self.tool_id, decision=decision))
        # Also post the PermissionDecision message expected by the REPL
        from claude_code.screens.repl import PermissionDecision

        self.post_message(PermissionDecision(tool_id=self.tool_id, decision=decision))
