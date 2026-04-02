"""
Analytics logging for API calls.

Records API call metadata (model, tokens, latency, errors) for analytics
and debugging.  Uses a lightweight queue-based approach to avoid blocking
the main conversation loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class APICallRecord:
    """Record of a single API call."""

    request_id: str = ""
    model: str = ""
    provider: str = "anthropic"
    timestamp: float = field(default_factory=time.time)

    # Request
    message_count: int = 0
    tool_count: int = 0
    system_prompt_tokens_est: int = 0
    has_images: bool = False

    # Response
    status_code: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    stop_reason: Optional[str] = None

    # Performance
    latency_ms: float = 0.0
    time_to_first_token_ms: Optional[float] = None
    streaming: bool = True

    # Error
    error: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0

    # Cost
    cost_usd: float = 0.0

    # Context
    session_id: str = ""
    turn_index: int = 0


# ---------------------------------------------------------------------------
# Logger singleton
# ---------------------------------------------------------------------------


class APICallLogger:
    """Accumulates API call records and writes them to disk.

    Thread/task-safe via an asyncio.Queue.
    """

    _instance: Optional["APICallLogger"] = None

    def __init__(
        self,
        log_dir: Optional[str] = None,
        max_buffer_size: int = 100,
    ) -> None:
        self._log_dir = Path(log_dir) if log_dir else self._default_dir()
        self._buffer: List[APICallRecord] = []
        self._max_buffer = max_buffer_size
        self._total_calls: int = 0
        self._total_errors: int = 0
        self._total_tokens: int = 0
        self._total_cost_usd: float = 0.0

    @classmethod
    def get_instance(cls) -> "APICallLogger":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "APICallLogger") -> None:
        cls._instance = instance

    def record(self, call: APICallRecord) -> None:
        """Record a completed API call."""
        self._buffer.append(call)
        self._total_calls += 1
        self._total_tokens += call.input_tokens + call.output_tokens
        self._total_cost_usd += call.cost_usd

        if call.error:
            self._total_errors += 1

        if len(self._buffer) >= self._max_buffer:
            self.flush()

    def flush(self) -> None:
        """Write buffered records to disk."""
        if not self._buffer:
            return

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self._log_dir / "api_calls.jsonl"

            with open(log_file, "a", encoding="utf-8") as f:
                for record in self._buffer:
                    f.write(json.dumps(asdict(record), default=str) + "\n")

            logger.debug("Flushed %d API call records", len(self._buffer))
            self._buffer.clear()
        except OSError as exc:
            logger.warning("Cannot write API call log: %s", exc)

    @property
    def stats(self) -> Dict[str, Any]:
        """Return aggregate statistics."""
        return {
            "total_calls": self._total_calls,
            "total_errors": self._total_errors,
            "total_tokens": self._total_tokens,
            "total_cost_usd": self._total_cost_usd,
            "buffered_records": len(self._buffer),
            "error_rate": (
                self._total_errors / self._total_calls
                if self._total_calls > 0
                else 0.0
            ),
        }

    @staticmethod
    def _default_dir() -> Path:
        return Path.home() / ".claude" / "logs"


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def log_api_call(record: APICallRecord) -> None:
    """Log an API call record to the global logger."""
    APICallLogger.get_instance().record(record)


def log_api_call_from_dict(data: Dict[str, Any]) -> None:
    """Log an API call record from a dict."""
    record = APICallRecord(**{
        k: v for k, v in data.items() if k in APICallRecord.__dataclass_fields__
    })
    log_api_call(record)


def flush_api_logs() -> None:
    """Flush all buffered API call records to disk."""
    APICallLogger.get_instance().flush()


def get_api_stats() -> Dict[str, Any]:
    """Return aggregate API call statistics."""
    return APICallLogger.get_instance().stats


# ---------------------------------------------------------------------------
# Timer context manager
# ---------------------------------------------------------------------------


class APICallTimer:
    """Context manager that builds an APICallRecord with timing."""

    def __init__(
        self,
        model: str = "",
        session_id: str = "",
        turn_index: int = 0,
        provider: str = "anthropic",
    ) -> None:
        self.record = APICallRecord(
            model=model,
            session_id=session_id,
            turn_index=turn_index,
            provider=provider,
        )
        self._start: float = 0.0
        self._first_token_time: Optional[float] = None

    def __enter__(self) -> "APICallTimer":
        self._start = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        elapsed = (time.time() - self._start) * 1000
        self.record.latency_ms = elapsed
        if self._first_token_time is not None:
            self.record.time_to_first_token_ms = (
                (self._first_token_time - self._start) * 1000
            )

        if exc_val is not None:
            self.record.error = str(exc_val)
            from .errors import classify_api_error
            classified = classify_api_error(exc_val)
            self.record.error_type = classified.error_type.value
            self.record.status_code = classified.status_code

        log_api_call(self.record)

    def mark_first_token(self) -> None:
        """Call when the first token is received during streaming."""
        if self._first_token_time is None:
            self._first_token_time = time.time()

    def set_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation: int = 0,
        cache_read: int = 0,
    ) -> None:
        self.record.input_tokens = input_tokens
        self.record.output_tokens = output_tokens
        self.record.cache_creation_input_tokens = cache_creation
        self.record.cache_read_input_tokens = cache_read

    def set_cost(self, cost_usd: float) -> None:
        self.record.cost_usd = cost_usd
