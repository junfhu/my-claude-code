"""Services / API package — Anthropic API client, error handling, retry logic."""

from .client import ClientConfig, get_anthropic_client
from .errors import (
    APIErrorType,
    ClassifiedError,
    classify_api_error,
    get_assistant_message_from_error,
    is_prompt_too_long_message,
    is_retryable_error,
)
from .retry import RetryConfig, with_retry, with_retry_simple

__all__ = [
    "ClientConfig",
    "get_anthropic_client",
    "APIErrorType",
    "ClassifiedError",
    "classify_api_error",
    "get_assistant_message_from_error",
    "is_prompt_too_long_message",
    "is_retryable_error",
    "RetryConfig",
    "with_retry",
    "with_retry_simple",
]
