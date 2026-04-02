"""Context collection: git status, system/user context, notifications, mailbox."""

from .context import (
    clear_context_cache,
    get_git_status,
    get_system_context,
    get_user_context,
)
from .mailbox import Mailbox, Message
from .notifications import Notification, NotificationManager

__all__ = [
    "Mailbox",
    "Message",
    "Notification",
    "NotificationManager",
    "clear_context_cache",
    "get_git_status",
    "get_system_context",
    "get_user_context",
]
