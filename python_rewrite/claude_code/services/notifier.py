"""
OS notification service.

Sends desktop notifications for long-running operations, task completions,
errors, and other events.  Uses platform-native notification mechanisms.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Notification:
    """A notification to be displayed to the user."""

    title: str
    body: str
    urgency: str = "normal"  # "low" | "normal" | "critical"
    icon: Optional[str] = None
    sound: bool = False
    timeout_ms: int = 5000
    category: str = "general"  # "general" | "task_complete" | "error" | "cost"
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------


class Notifier:
    """Cross-platform desktop notification service.

    Supports macOS (osascript/terminal-notifier), Linux (notify-send),
    and provides a no-op fallback for unsupported platforms or
    when no notification tool is available.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        app_name: str = "Claude Code",
        sound: bool = True,
    ) -> None:
        self._enabled = enabled
        self._app_name = app_name
        self._sound = sound
        self._platform = platform.system().lower()
        self._available: Optional[bool] = None
        self._history: List[Notification] = []
        self._max_history = 100

    @property
    def is_available(self) -> bool:
        """Check whether notifications can be sent."""
        if self._available is not None:
            return self._available

        self._available = self._check_availability()
        return self._available

    def notify(self, notification: Notification) -> bool:
        """Send a notification synchronously.

        Returns True if the notification was sent (or queued) successfully.
        """
        if not self._enabled or not self.is_available:
            return False

        self._history.append(notification)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        try:
            if self._platform == "darwin":
                return self._notify_macos(notification)
            elif self._platform == "linux":
                return self._notify_linux(notification)
            elif self._platform == "windows":
                return self._notify_windows(notification)
            else:
                return False
        except Exception as exc:
            logger.debug("Notification failed: %s", exc)
            return False

    async def notify_async(self, notification: Notification) -> bool:
        """Send a notification asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.notify, notification)

    # ---- Convenience methods ----

    def task_complete(self, task: str, details: str = "") -> bool:
        """Notify that a task completed."""
        return self.notify(
            Notification(
                title=f"{self._app_name} — Task Complete",
                body=f"{task}\n{details}" if details else task,
                category="task_complete",
                sound=self._sound,
            )
        )

    def error(self, message: str) -> bool:
        """Notify about an error."""
        return self.notify(
            Notification(
                title=f"{self._app_name} — Error",
                body=message,
                urgency="critical",
                category="error",
                sound=True,
            )
        )

    def cost_warning(self, cost_usd: float, budget_usd: float) -> bool:
        """Notify about cost approaching budget."""
        pct = (cost_usd / budget_usd * 100) if budget_usd > 0 else 0
        return self.notify(
            Notification(
                title=f"{self._app_name} — Cost Warning",
                body=f"Session cost: ${cost_usd:.2f} ({pct:.0f}% of ${budget_usd:.2f} budget)",
                urgency="normal",
                category="cost",
            )
        )

    def waiting_for_input(self) -> bool:
        """Notify that the assistant is waiting for user input."""
        return self.notify(
            Notification(
                title=self._app_name,
                body="Waiting for your input...",
                urgency="low",
                category="general",
                timeout_ms=3000,
            )
        )

    @property
    def history(self) -> List[Notification]:
        return list(self._history)

    # ---- Platform implementations ----

    def _notify_macos(self, notification: Notification) -> bool:
        """Send notification on macOS using osascript."""
        # Try terminal-notifier first (better UX)
        if shutil.which("terminal-notifier"):
            cmd = [
                "terminal-notifier",
                "-title",
                notification.title,
                "-message",
                notification.body,
                "-group",
                self._app_name,
            ]
            if notification.sound and self._sound:
                cmd.extend(["-sound", "default"])
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
                return True
            except (subprocess.TimeoutExpired, OSError):
                pass

        # Fallback to osascript
        script = (
            f'display notification "{_escape_applescript(notification.body)}" '
            f'with title "{_escape_applescript(notification.title)}"'
        )
        if notification.sound and self._sound:
            script += ' sound name "default"'

        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _notify_linux(self, notification: Notification) -> bool:
        """Send notification on Linux using notify-send."""
        if not shutil.which("notify-send"):
            return False

        urgency_map = {
            "low": "low",
            "normal": "normal",
            "critical": "critical",
        }

        cmd = [
            "notify-send",
            "--app-name", self._app_name,
            "--urgency", urgency_map.get(notification.urgency, "normal"),
            "--expire-time", str(notification.timeout_ms),
            notification.title,
            notification.body,
        ]

        if notification.icon:
            cmd.extend(["--icon", notification.icon])

        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _notify_windows(self, notification: Notification) -> bool:
        """Send notification on Windows using PowerShell toast."""
        script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

        $template = @"
        <toast>
            <visual>
                <binding template="ToastText02">
                    <text id="1">{notification.title}</text>
                    <text id="2">{notification.body}</text>
                </binding>
            </visual>
        </toast>
"@

        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{self._app_name}").Show($toast)
        """

        try:
            subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                timeout=10,
            )
            return True
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return False

    def _check_availability(self) -> bool:
        """Check if notification tools are available."""
        if self._platform == "darwin":
            return shutil.which("osascript") is not None
        elif self._platform == "linux":
            return shutil.which("notify-send") is not None
        elif self._platform == "windows":
            return shutil.which("powershell") is not None
        return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_global_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    """Get (or create) the global notifier."""
    global _global_notifier
    if _global_notifier is None:
        _global_notifier = Notifier()
    return _global_notifier


def set_notifier(notifier: Notifier) -> None:
    """Replace the global notifier."""
    global _global_notifier
    _global_notifier = notifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape_applescript(text: str) -> str:
    """Escape a string for use in AppleScript."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
