"""
Animated spinner widget for loading/thinking states.

Provides both a Textual widget (for the TUI) and a Rich-based
console spinner (for headless progress indication).
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional, Sequence

from rich.text import Text
from textual.reactive import reactive
from textual.timer import Timer
from textual.widget import Widget


# ---------------------------------------------------------------------------
# Spinner frame sets
# ---------------------------------------------------------------------------

SPINNER_FRAMES: dict[str, Sequence[str]] = {
    "dots": ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"),
    "line": ("-", "\\", "|", "/"),
    "arc": ("◜", "◠", "◝", "◞", "◡", "◟"),
    "bouncing_bar": (
        "[    ]", "[=   ]", "[==  ]", "[=== ]",
        "[ ===]", "[  ==]", "[   =]", "[    ]",
        "[   =]", "[  ==]", "[ ===]", "[====]",
        "[=== ]", "[==  ]", "[=   ]",
    ),
    "moon": ("🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"),
    "braille": ("⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"),
    "pulse": ("█", "▓", "▒", "░", "▒", "▓"),
    "thinking": ("🤔", "💭", "⚡", "✨", "💡"),
}


# ---------------------------------------------------------------------------
# Thinking messages (rotated during long operations)
# ---------------------------------------------------------------------------

_THINKING_MESSAGES = [
    "Thinking",
    "Analyzing",
    "Processing",
    "Reasoning",
    "Considering",
    "Evaluating",
    "Working",
]


# ---------------------------------------------------------------------------
# Textual widget
# ---------------------------------------------------------------------------


class ThinkingSpinner(Widget):
    """
    Animated spinner widget that shows a thinking/loading indicator.

    Renders as: ``⠋ Thinking...`` with the spinner character cycling
    through the selected frame set.
    """

    DEFAULT_CSS = """
    ThinkingSpinner {
        height: 1;
        padding: 0 1;
        color: $accent;
    }
    """

    # Reactive state
    is_active: reactive[bool] = reactive(False)
    label: reactive[str] = reactive("Thinking")
    style_name: reactive[str] = reactive("dots")
    elapsed_seconds: reactive[float] = reactive(0.0)

    def __init__(
        self,
        label: str = "Thinking",
        style_name: str = "dots",
        interval: float = 0.08,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.style_name = style_name
        self._interval = interval
        self._frame_index: int = 0
        self._timer: Optional[Timer] = None
        self._start_time: float = 0.0
        self._message_index: int = 0

    @property
    def frames(self) -> Sequence[str]:
        """Return the current frame set."""
        return SPINNER_FRAMES.get(self.style_name, SPINNER_FRAMES["dots"])

    def on_mount(self) -> None:
        """Start the animation timer."""
        self._timer = self.set_interval(self._interval, self._advance_frame)

    def _advance_frame(self) -> None:
        """Advance to the next frame."""
        if not self.is_active:
            return
        self._frame_index = (self._frame_index + 1) % len(self.frames)
        self.elapsed_seconds = time.monotonic() - self._start_time

        # Rotate the thinking message every ~5 seconds
        if self.elapsed_seconds > 0 and int(self.elapsed_seconds) % 5 == 0:
            new_idx = int(self.elapsed_seconds / 5) % len(_THINKING_MESSAGES)
            if new_idx != self._message_index:
                self._message_index = new_idx
                self.label = _THINKING_MESSAGES[self._message_index]

        self.refresh()

    def start(self, label: Optional[str] = None) -> None:
        """Start the spinner."""
        if label:
            self.label = label
        self._start_time = time.monotonic()
        self._frame_index = 0
        self._message_index = 0
        self.is_active = True

    def stop(self) -> None:
        """Stop the spinner."""
        self.is_active = False
        self.elapsed_seconds = 0.0

    def render(self) -> Text:
        """Render the spinner."""
        if not self.is_active:
            return Text("")

        frame = self.frames[self._frame_index]

        # Build the display text
        result = Text()
        result.append(f" {frame} ", style="bold cyan")
        result.append(self.label, style="bold")

        # Animated dots
        dot_count = (self._frame_index % 4)
        result.append("." * dot_count, style="dim")
        result.append(" " * (3 - dot_count))

        # Elapsed time (after 2 seconds)
        if self.elapsed_seconds > 2.0:
            elapsed_str = self._format_elapsed(self.elapsed_seconds)
            result.append(f" ({elapsed_str})", style="dim")

        return result

    def watch_is_active(self, active: bool) -> None:
        """React to activation state changes."""
        if active:
            self._start_time = time.monotonic()
        self.refresh()

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        """Format elapsed time for display."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m{secs:02d}s"


# ---------------------------------------------------------------------------
# Inline progress spinner (non-widget, for Rich Console usage)
# ---------------------------------------------------------------------------


class InlineSpinner:
    """
    A non-widget spinner for use with ``rich.console.Console.status()``
    or manual rendering. Provides the frame cycling logic without
    requiring a Textual event loop.
    """

    def __init__(self, style_name: str = "dots") -> None:
        self.style_name = style_name
        self._frame_index = 0
        self._start_time = time.monotonic()

    @property
    def frames(self) -> Sequence[str]:
        return SPINNER_FRAMES.get(self.style_name, SPINNER_FRAMES["dots"])

    def next_frame(self) -> str:
        """Return the next spinner frame."""
        frame = self.frames[self._frame_index]
        self._frame_index = (self._frame_index + 1) % len(self.frames)
        return frame

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def render_text(self, label: str = "Thinking") -> Text:
        """Render the spinner as a Rich Text object."""
        frame = self.next_frame()
        text = Text()
        text.append(f"{frame} ", style="bold cyan")
        text.append(label, style="bold")
        if self.elapsed > 2.0:
            text.append(f" ({self.elapsed:.0f}s)", style="dim")
        return text
