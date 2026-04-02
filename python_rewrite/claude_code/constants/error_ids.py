"""
Error ID constants for tracking error sources in production.

These IDs are obfuscated identifiers that help trace which ``log_error()``
call generated an error.

Adding a new error type:
    1. Add a constant based on the next ID.
    2. Increment NEXT_ERROR_ID.
"""

from __future__ import annotations

__all__ = [
    "E_TOOL_USE_SUMMARY_GENERATION_FAILED",
    "NEXT_ERROR_ID",
]

# Next ID: 346
NEXT_ERROR_ID: int = 346

E_TOOL_USE_SUMMARY_GENERATION_FAILED: int = 344
