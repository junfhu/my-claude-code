"""
Initial setup / trust dialog screen.

Shown on first launch or when entering an untrusted directory. Asks the
user to trust the current workspace, authenticate, or configure settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from rich.panel import Panel
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


# ---------------------------------------------------------------------------
# ASCII art logo
# ---------------------------------------------------------------------------

_LOGO = r"""
   _____ _                 _         ____          _
  / ____| |               | |       / ___|___   __| | ___
 | |    | | __ _ _   _  __| | ___  | |   / _ \ / _` |/ _ \
 | |    | |/ _` | | | |/ _` |/ _ \ | |__| (_) | (_| |  __/
  \_____|_|\__,_|\__,_|\__,_|\___/  \____\___/ \__,_|\___|
"""


# ---------------------------------------------------------------------------
# Setup screen (standalone App for use from main.py)
# ---------------------------------------------------------------------------


class SetupScreen(App):
    """
    First-run / trust setup screen.

    Shown when:
      1. The user launches Claude Code for the first time, OR
      2. The current working directory is not in the trusted-directories list.

    The user can:
      - Trust this directory (saves to ``~/.claude/trust.json``)
      - Launch the login/auth flow
      - Quit
    """

    TITLE = "Claude Code — Setup"

    CSS = """
    Screen {
        align: center middle;
    }

    #setup-container {
        width: 70;
        height: auto;
        padding: 1 2;
    }

    #logo {
        height: auto;
        text-align: center;
        color: $accent;
        margin-bottom: 1;
    }

    #welcome-text {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
    }

    #trust-panel {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: solid $warning;
    }

    #dir-display {
        height: auto;
        padding: 0 1;
        margin-bottom: 1;
    }

    #button-row {
        height: 3;
        align: center middle;
        margin-top: 1;
    }

    Button {
        margin: 0 1;
        min-width: 18;
    }

    .auth-notice {
        height: auto;
        padding: 0 2;
        margin-top: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("y", "trust", "Trust & Continue", show=True),
        Binding("n", "quit", "Quit", show=True),
        Binding("q", "quit", "Quit", show=False),
        Binding("escape", "quit", "Quit", show=False),
    ]

    def __init__(self, cwd: Optional[str] = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cwd = cwd or os.getcwd()
        self.trusted = False
        self._has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        self._has_credentials = Path(
            os.path.expanduser("~/.claude/credentials.json")
        ).is_file()

    def compose(self) -> ComposeResult:
        yield Header()
        with Center():
            with Vertical(id="setup-container"):
                yield Static(_LOGO, id="logo")
                yield Static(
                    Text.from_markup(
                        "[bold]Welcome to Claude Code![/bold]\n\n"
                        "Claude Code is an AI coding assistant that runs in your terminal.\n"
                        "It can read and write files, execute commands, and help you build software."
                    ),
                    id="welcome-text",
                )
                yield Static(
                    self._build_trust_panel(),
                    id="trust-panel",
                )
                yield Static(
                    Text.from_markup(
                        f"  📂 [bold]{self.cwd}[/bold]"
                    ),
                    id="dir-display",
                )
                with Center(id="button-row"):
                    yield Button(
                        "✔ Trust & Continue (y)",
                        id="trust-btn",
                        variant="success",
                    )
                    yield Button(
                        "✖ Quit (n)",
                        id="quit-btn",
                        variant="error",
                    )
                yield Static(
                    self._build_auth_notice(),
                    classes="auth-notice",
                )
        yield Footer()

    def _build_trust_panel(self) -> Text:
        """Build the trust warning text."""
        text = Text()
        text.append("⚠️  Trust Required\n\n", style="bold yellow")
        text.append(
            "Claude Code needs your permission to work in this directory.\n"
            "Trusting a directory allows Claude to read files, execute commands,\n"
            "and make changes within it.\n\n"
            "You can manage trusted directories in "
        )
        text.append("~/.claude/trust.json", style="cyan")
        text.append(".")
        return text

    def _build_auth_notice(self) -> Text:
        """Build the authentication status notice."""
        text = Text()
        if self._has_api_key:
            text.append("✔ ", style="green")
            text.append("API key found in environment.", style="dim")
        elif self._has_credentials:
            text.append("✔ ", style="green")
            text.append("Credentials found in ~/.claude/credentials.json", style="dim")
        else:
            text.append("⚠ ", style="yellow")
            text.append(
                "No API key found. Set ANTHROPIC_API_KEY or run ",
                style="dim",
            )
            text.append("claude login", style="bold cyan")
            text.append(" after setup.", style="dim")
        return text

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#trust-btn")
    def on_trust_button(self, event: Button.Pressed) -> None:
        """User chose to trust the directory."""
        self.trusted = True
        self.exit()

    @on(Button.Pressed, "#quit-btn")
    def on_quit_button(self, event: Button.Pressed) -> None:
        """User chose to quit."""
        self.trusted = False
        self.exit()

    # ------------------------------------------------------------------
    # Keyboard actions
    # ------------------------------------------------------------------

    def action_trust(self) -> None:
        """Shortcut: trust and continue."""
        self.trusted = True
        self.exit()


# ---------------------------------------------------------------------------
# Inline trust prompt (for embedding in the REPL screen)
# ---------------------------------------------------------------------------


class InlineTrustPrompt(Static):
    """
    A compact inline trust prompt widget that can be embedded in the REPL
    screen instead of showing a full-screen setup dialog.
    """

    DEFAULT_CSS = """
    InlineTrustPrompt {
        height: auto;
        padding: 1 2;
        margin: 1 2;
        border: solid $warning;
    }
    """

    class TrustDecision(Static.Changed):
        """Message emitted when the user decides."""

        def __init__(self, trusted: bool) -> None:
            super().__init__()
            self.trusted = trusted

    def __init__(self, cwd: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cwd = cwd

    def render(self) -> Text:
        text = Text()
        text.append("⚠️  Untrusted directory: ", style="bold yellow")
        text.append(self.cwd, style="bold")
        text.append("\n\nPress ", style="dim")
        text.append("y", style="bold green")
        text.append(" to trust, ", style="dim")
        text.append("n", style="bold red")
        text.append(" to quit.", style="dim")
        return text
