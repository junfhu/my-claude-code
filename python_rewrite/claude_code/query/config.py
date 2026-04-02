"""
QueryConfig — Immutable snapshot of query configuration.

Captures all parameters needed for a single query loop invocation.
Created once at query start and threaded through every phase.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class QueryConfig:
    """Immutable configuration snapshot for one query loop run.

    This is created from QueryParams at the start of query() and should
    not be mutated during the loop.
    """

    # Model
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 16384
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stop_sequences: Optional[tuple[str, ...]] = None  # frozen → tuple

    # System prompt (already assembled)
    system_prompt: str = ""

    # Tools
    tools: tuple[Any, ...] = ()  # frozen → tuple

    # API
    api_key: Optional[str] = None
    provider: str = "anthropic"
    base_url: Optional[str] = None
    timeout_ms: int = 120_000

    # Retry
    retry_enabled: bool = True
    max_retries: int = 3

    # Permission
    permission_mode: str = "default"

    # Context
    cwd: str = "."
    session_id: str = ""

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Budget / limits
    max_turns: int = 100
    max_budget_usd: Optional[float] = None
    max_context_tokens: int = 200_000

    # Feature flags
    enable_compact: bool = True
    compact_threshold_tokens: int = 100_000
    enable_streaming: bool = True
    enable_cache: bool = True

    # ---- derived helpers ----

    @property
    def is_bedrock(self) -> bool:
        return self.provider == "bedrock"

    @property
    def is_vertex(self) -> bool:
        return self.provider == "vertex"

    @property
    def is_azure(self) -> bool:
        return self.provider == "azure"

    @property
    def is_direct(self) -> bool:
        return self.provider == "anthropic"

    @property
    def effective_model(self) -> str:
        """Return the model string as the API expects it."""
        # Bedrock uses a different model ID format
        if self.is_bedrock:
            return self._bedrock_model_id()
        return self.model

    def _bedrock_model_id(self) -> str:
        """Convert a model name to its Bedrock model ID."""
        # e.g. "claude-sonnet-4-20250514" → "anthropic.claude-sonnet-4-20250514-v1:0"
        model = self.model
        if not model.startswith("anthropic."):
            model = f"anthropic.{model}"
        if not any(model.endswith(s) for s in (":0", ":1", ":2")):
            model = f"{model}-v1:0"
        return model

    @classmethod
    def from_env(cls, **overrides: Any) -> "QueryConfig":
        """Create a QueryConfig populated from environment variables."""
        env_map = {
            "model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "provider": os.environ.get("CLAUDE_PROVIDER", "anthropic"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
            "max_tokens": int(os.environ.get("CLAUDE_MAX_TOKENS", "16384")),
            "timeout_ms": int(os.environ.get("CLAUDE_TIMEOUT_MS", "120000")),
            "max_retries": int(os.environ.get("CLAUDE_MAX_RETRIES", "3")),
            "cwd": os.environ.get("CLAUDE_CWD", os.getcwd()),
            "permission_mode": os.environ.get("CLAUDE_PERMISSION_MODE", "default"),
        }
        env_map.update(overrides)

        # Convert mutable defaults → frozen types
        if "tools" in env_map and isinstance(env_map["tools"], list):
            env_map["tools"] = tuple(env_map["tools"])
        if "stop_sequences" in env_map and isinstance(env_map["stop_sequences"], list):
            env_map["stop_sequences"] = tuple(env_map["stop_sequences"])

        return cls(**env_map)

    def replace(self, **changes: Any) -> "QueryConfig":
        """Return a new QueryConfig with the given fields replaced.

        Convenience wrapper around dataclasses.replace for frozen dataclasses.
        """
        import dataclasses
        return dataclasses.replace(self, **changes)
