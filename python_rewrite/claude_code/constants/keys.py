"""
Key constants for keyboard handling and GrowthBook client configuration.
"""

from __future__ import annotations

import os

__all__ = [
    "get_growthbook_client_key",
]


def _is_env_truthy(value: str | None) -> bool:
    """Check if an env var value is truthy (``"1"``, ``"true"``, ``"yes"``)."""
    if value is None:
        return False
    return value.lower() in ("1", "true", "yes")


def get_growthbook_client_key() -> str:
    """Return the GrowthBook SDK client key based on user type and environment.

    Lazy-reads environment variables so that ``ENABLE_GROWTHBOOK_DEV`` from
    ``globalSettings.env`` (applied after module load) is picked up.
    """
    user_type = os.environ.get("USER_TYPE")
    if user_type == "ant":
        if _is_env_truthy(os.environ.get("ENABLE_GROWTHBOOK_DEV")):
            return "sdk-yZQvlplybuXjYh6L"
        return "sdk-xRVcrliHIlrg4og4"
    return "sdk-zAZezfDKGoZuXXKe"
