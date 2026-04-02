"""
Error handling and classification for Anthropic API responses.

Provides utilities to:
- Convert API errors into assistant-friendly messages
- Classify errors by type (auth, rate-limit, quota, timeout, SSL, etc.)
- Detect prompt-too-long conditions
- Build synthetic assistant messages from errors for display
"""
from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class APIErrorType(enum.Enum):
    """Classification of API errors."""

    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    QUOTA_EXCEEDED = "quota_exceeded"
    PROMPT_TOO_LONG = "prompt_too_long"
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    SSL = "ssl"
    SERVER_ERROR = "server_error"
    CONTENT_FILTER = "content_filter"
    MODEL_NOT_AVAILABLE = "model_not_available"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """A classified API error with metadata."""

    error_type: APIErrorType
    message: str
    status_code: Optional[int] = None
    retryable: bool = False
    retry_after_ms: Optional[int] = None
    original_error: Optional[Exception] = None
    suggestion: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def classify_api_error(error: Exception) -> ClassifiedError:
    """Classify an API error into a structured type.

    Works with anthropic SDK exceptions and generic exceptions.
    """
    msg = str(error).lower()
    status_code = getattr(error, "status_code", None)

    # ---- Status code based ----
    if status_code == 401:
        return ClassifiedError(
            error_type=APIErrorType.AUTHENTICATION,
            message="Invalid API key or authentication failed.",
            status_code=status_code,
            retryable=False,
            original_error=error,
            suggestion="Check your ANTHROPIC_API_KEY environment variable.",
        )

    if status_code == 403:
        return ClassifiedError(
            error_type=APIErrorType.PERMISSION,
            message="Permission denied. Your API key may not have access to this resource.",
            status_code=status_code,
            retryable=False,
            original_error=error,
            suggestion="Verify your API key has the necessary permissions.",
        )

    if status_code == 404:
        if "model" in msg:
            return ClassifiedError(
                error_type=APIErrorType.MODEL_NOT_AVAILABLE,
                message="The requested model is not available.",
                status_code=status_code,
                retryable=False,
                original_error=error,
                suggestion="Check the model name and your account's model access.",
            )
        return ClassifiedError(
            error_type=APIErrorType.NOT_FOUND,
            message="Resource not found.",
            status_code=status_code,
            retryable=False,
            original_error=error,
        )

    if status_code == 413:
        return ClassifiedError(
            error_type=APIErrorType.PROMPT_TOO_LONG,
            message="Request payload too large. The prompt is too long.",
            status_code=status_code,
            retryable=False,
            original_error=error,
            suggestion="Reduce the conversation size or enable auto-compact.",
        )

    if status_code == 429:
        retry_after = _extract_retry_after(error)
        return ClassifiedError(
            error_type=APIErrorType.RATE_LIMIT,
            message="Rate limit exceeded.",
            status_code=status_code,
            retryable=True,
            retry_after_ms=retry_after,
            original_error=error,
            suggestion="Wait a moment before retrying. Consider reducing request frequency.",
        )

    if status_code == 529:
        return ClassifiedError(
            error_type=APIErrorType.OVERLOADED,
            message="API is temporarily overloaded.",
            status_code=status_code,
            retryable=True,
            retry_after_ms=5000,
            original_error=error,
            suggestion="The API is experiencing high load. Retrying with backoff.",
        )

    if status_code is not None and 500 <= status_code < 600:
        return ClassifiedError(
            error_type=APIErrorType.SERVER_ERROR,
            message=f"Server error (HTTP {status_code}).",
            status_code=status_code,
            retryable=True,
            retry_after_ms=2000,
            original_error=error,
            suggestion="This is a server-side issue. Retrying may help.",
        )

    # ---- Message-pattern based ----
    if _match_any(msg, ("timeout", "timed out", "deadline exceeded")):
        return ClassifiedError(
            error_type=APIErrorType.TIMEOUT,
            message="Request timed out.",
            retryable=True,
            retry_after_ms=1000,
            original_error=error,
            suggestion="The request took too long. It will be retried.",
        )

    if _match_any(msg, ("ssl", "certificate", "tls")):
        return ClassifiedError(
            error_type=APIErrorType.SSL,
            message="SSL/TLS connection error.",
            retryable=False,
            original_error=error,
            suggestion="Check your network configuration and SSL certificates.",
        )

    if _match_any(msg, ("connection", "connect", "dns", "resolve", "network")):
        return ClassifiedError(
            error_type=APIErrorType.CONNECTION,
            message="Network connection error.",
            retryable=True,
            retry_after_ms=2000,
            original_error=error,
            suggestion="Check your internet connection and proxy settings.",
        )

    if _match_any(msg, ("quota", "insufficient_quota", "billing")):
        return ClassifiedError(
            error_type=APIErrorType.QUOTA_EXCEEDED,
            message="API quota exceeded.",
            retryable=False,
            original_error=error,
            suggestion="Your account has reached its usage limit. Check your billing settings.",
        )

    if _match_any(msg, ("prompt is too long", "too many tokens", "context length")):
        return ClassifiedError(
            error_type=APIErrorType.PROMPT_TOO_LONG,
            message="Prompt is too long for the model's context window.",
            retryable=False,
            original_error=error,
            suggestion="Enable auto-compact or reduce the conversation length.",
        )

    if _match_any(msg, ("content filter", "content_filter", "safety")):
        return ClassifiedError(
            error_type=APIErrorType.CONTENT_FILTER,
            message="Request was blocked by content filters.",
            retryable=False,
            original_error=error,
            suggestion="Modify your request to comply with content policies.",
        )

    if _match_any(msg, ("invalid", "bad request", "malformed")):
        return ClassifiedError(
            error_type=APIErrorType.INVALID_REQUEST,
            message=f"Invalid request: {error}",
            status_code=status_code or 400,
            retryable=False,
            original_error=error,
        )

    # ---- Fallback ----
    return ClassifiedError(
        error_type=APIErrorType.UNKNOWN,
        message=str(error),
        status_code=status_code,
        retryable=False,
        original_error=error,
    )


# ---------------------------------------------------------------------------
# Assistant message generation
# ---------------------------------------------------------------------------


def get_assistant_message_from_error(
    error: Exception,
    *,
    model: str = "",
    turn_index: int = 0,
) -> Dict[str, Any]:
    """Convert an API error into a synthetic assistant message.

    This is used to show error information to the user in the
    conversation UI when the API call fails.
    """
    classified = classify_api_error(error)

    error_text = _format_error_for_display(classified)

    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": error_text,
            }
        ],
        "_meta": {
            "is_error": True,
            "error_type": classified.error_type.value,
            "status_code": classified.status_code,
            "retryable": classified.retryable,
            "model": model,
            "turn_index": turn_index,
        },
    }
    return assistant_msg


def _format_error_for_display(classified: ClassifiedError) -> str:
    """Format a classified error as a user-friendly string."""
    parts = [f"⚠️ **API Error**: {classified.message}"]

    if classified.suggestion:
        parts.append(f"\n💡 **Suggestion**: {classified.suggestion}")

    if classified.retryable:
        if classified.retry_after_ms:
            parts.append(
                f"\n🔄 Will retry in {classified.retry_after_ms / 1000:.1f}s..."
            )
        else:
            parts.append("\n🔄 This error is retryable.")

    if classified.status_code:
        parts.append(f"\n📡 HTTP Status: {classified.status_code}")

    return "".join(parts)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def is_prompt_too_long_message(error: Exception) -> bool:
    """Check if an error indicates the prompt is too long."""
    classified = classify_api_error(error)
    return classified.error_type == APIErrorType.PROMPT_TOO_LONG


def is_retryable_error(error: Exception) -> bool:
    """Check if an error should be retried."""
    classified = classify_api_error(error)
    return classified.retryable


def is_auth_error(error: Exception) -> bool:
    """Check if an error is authentication-related."""
    classified = classify_api_error(error)
    return classified.error_type in (
        APIErrorType.AUTHENTICATION,
        APIErrorType.PERMISSION,
    )


def is_rate_limit_error(error: Exception) -> bool:
    """Check if an error is a rate limit."""
    classified = classify_api_error(error)
    return classified.error_type in (
        APIErrorType.RATE_LIMIT,
        APIErrorType.OVERLOADED,
    )


def is_server_error(error: Exception) -> bool:
    """Check if an error is a server-side error."""
    classified = classify_api_error(error)
    return classified.error_type == APIErrorType.SERVER_ERROR


def get_retry_after_ms(error: Exception) -> Optional[int]:
    """Extract the retry-after delay in milliseconds from an error."""
    classified = classify_api_error(error)
    return classified.retry_after_ms


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Check if any pattern appears in text."""
    return any(p in text for p in patterns)


def _extract_retry_after(error: Exception) -> Optional[int]:
    """Try to extract retry-after header value from an error."""
    # anthropic SDK may expose headers
    headers = getattr(error, "response", None)
    if headers is not None:
        headers = getattr(headers, "headers", {})
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return int(float(retry_after) * 1000)
            except (ValueError, TypeError):
                pass

    # Try to parse from error message
    msg = str(error)
    match = re.search(r"retry.after[:\s]+(\d+(?:\.\d+)?)\s*s", msg, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 1000)

    # Default for 429
    return 2000
