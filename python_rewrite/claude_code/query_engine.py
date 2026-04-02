"""
QueryEngine - Standalone engine class managing the full lifecycle of a conversation.

Manages mutable message history, tracks file state cache for diff detection,
accumulates token usage, coordinates with query() function for the main loop.
This is the primary public interface for programmatic use of Claude Code.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
)

from .cost_tracker import (
    CostTracker,
    ModelUsage,
    add_usage,
    estimate_cost_usd,
)
from .query.config import QueryConfig
from .query.query import QueryParams, query
from .query.stop_hooks import (
    MaxTurnsStopHook,
    BudgetStopHook,
    StopHookResult,
)
from .query.token_budget import TokenBudget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class QueryEngineConfig:
    """Configuration for QueryEngine initialization."""

    model: str = "claude-sonnet-4-20250514"
    max_turns: int = 100
    max_tokens: int = 16384
    system_prompt: Optional[str] = None
    custom_system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    tools: List[Any] = field(default_factory=list)
    permission_mode: str = "default"
    api_key: Optional[str] = None
    max_budget_usd: Optional[float] = None
    cwd: str = "."
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    provider: str = "anthropic"  # anthropic | bedrock | vertex | azure
    base_url: Optional[str] = None
    timeout_ms: int = 120_000
    retry_enabled: bool = True
    max_retries: int = 3
    enable_analytics: bool = True
    enable_compact: bool = True
    compact_threshold_tokens: int = 100_000
    session_id: Optional[str] = None


@dataclass
class StreamEvent:
    """A single event emitted by the query engine during streaming."""

    type: str  # text_delta | tool_use | tool_result | message_start | message_stop | error | usage | cost
    data: Any = None
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:  # pragma: no cover
        preview = str(self.data)[:80] if self.data else ""
        return f"StreamEvent(type={self.type!r}, data={preview!r})"


@dataclass
class FileSnapshot:
    """A snapshot of a file's content hash for diff detection."""

    path: str
    content_hash: str
    modified_at: float
    size: int


@dataclass
class ConversationSummary:
    """Summary statistics for the current conversation."""

    session_id: str
    turn_count: int
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    duration_seconds: float
    model: str


# ---------------------------------------------------------------------------
# QueryEngine
# ---------------------------------------------------------------------------


class QueryEngine:
    """Standalone query engine for Claude Code conversations.

    Usage::

        config = QueryEngineConfig(model="claude-sonnet-4-20250514", api_key="sk-...")
        engine = QueryEngine(config)

        async for event in engine.submit_message("Explain this codebase"):
            if event.type == "text_delta":
                print(event.data, end="", flush=True)
    """

    # ---- construction ----

    def __init__(self, config: QueryEngineConfig) -> None:
        self.config = config

        # Conversation state
        self._messages: List[Dict[str, Any]] = []
        self._total_usage: Dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        self._permission_denials: List[Dict[str, Any]] = []
        self._file_state_cache: Dict[str, FileSnapshot] = {}
        self._session_id = config.session_id or str(uuid.uuid4())
        self._turn_count = 0
        self._total_cost_usd: float = 0.0
        self._started_at: float = time.time()
        self._aborted = False
        self._lock = asyncio.Lock()

        # Cost tracker (per-model)
        self._cost_tracker = CostTracker()

        # Token budget helper
        self._token_budget = TokenBudget(
            max_context_tokens=self._model_context_window(),
            max_output_tokens=config.max_tokens,
        )

        # Build stop hooks
        self._stop_hooks = self._build_stop_hooks()

        # External callbacks
        self._on_event: Optional[Callable[[StreamEvent], None]] = None
        self._on_turn_complete: Optional[Callable[[int], None]] = None

        logger.info(
            "QueryEngine initialised session=%s model=%s",
            self._session_id,
            config.model,
        )

    # ---- public API ----

    async def submit_message(
        self,
        prompt: str,
        *,
        images: Optional[List[Dict[str, Any]]] = None,
        extra_system: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Submit a user message and yield response events.

        This is the main entry point.  It appends the user message to
        history, invokes the query loop, streams back events, and updates
        internal bookkeeping when the turn completes.

        Args:
            prompt: The user's text message.
            images: Optional list of image content blocks.
            extra_system: An additional system prompt fragment for this turn only.
            metadata: Opaque metadata dict forwarded to analytics.

        Yields:
            StreamEvent instances (text_delta, tool_use, tool_result, etc.).
        """
        async with self._lock:
            if self._aborted:
                yield StreamEvent(type="error", data="Engine has been aborted.")
                return

            # ---- 1. Build the user message ----
            user_content: List[Any] = []
            if images:
                for img in images:
                    user_content.append(img)
            user_content.append({"type": "text", "text": prompt})

            user_message: Dict[str, Any] = {
                "role": "user",
                "content": user_content if len(user_content) > 1 else prompt,
            }
            self._add_message(user_message)

            # ---- 2. Build system prompt ----
            system_prompt = self._build_system_prompt(extra_system=extra_system)

            # ---- 3. Snapshot files for diff detection ----
            self._refresh_file_state_cache()

            # ---- 4. Prepare query params ----
            params = QueryParams(
                model=self.config.model,
                messages=list(self._messages),
                system_prompt=system_prompt,
                tools=list(self.config.tools),
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                stop_sequences=self.config.stop_sequences,
                api_key=self.config.api_key,
                provider=self.config.provider,
                base_url=self.config.base_url,
                timeout_ms=self.config.timeout_ms,
                retry_enabled=self.config.retry_enabled,
                max_retries=self.config.max_retries,
                stop_hooks=list(self._stop_hooks),
                permission_mode=self.config.permission_mode,
                cwd=self.config.cwd,
                session_id=self._session_id,
                metadata=metadata or {},
            )

            # ---- 5. Run the query loop ----
            turn_start = time.time()
            try:
                async for event in query(params):
                    # Book-keep usage
                    if event.get("type") == "usage":
                        self._accumulate_usage(event.get("data", {}))
                    elif event.get("type") == "message":
                        msg = event.get("data", {})
                        if msg.get("role") == "assistant":
                            self._add_message(msg)
                    elif event.get("type") == "tool_result":
                        self._add_message(event.get("data", {}))

                    # Wrap and yield as StreamEvent
                    se = StreamEvent(
                        type=event.get("type", "unknown"),
                        data=event.get("data"),
                    )

                    if self._on_event:
                        try:
                            self._on_event(se)
                        except Exception:
                            logger.exception("on_event callback error")

                    yield se

            except asyncio.CancelledError:
                logger.info("Query cancelled for session %s", self._session_id)
                self._aborted = True
                yield StreamEvent(type="error", data="Query was cancelled.")
                return
            except Exception as exc:
                logger.exception("Query loop error session=%s", self._session_id)
                yield StreamEvent(type="error", data=str(exc))
                return
            finally:
                self._turn_count += 1
                turn_elapsed = time.time() - turn_start
                logger.debug(
                    "Turn %d completed in %.2fs",
                    self._turn_count,
                    turn_elapsed,
                )
                if self._on_turn_complete:
                    try:
                        self._on_turn_complete(self._turn_count)
                    except Exception:
                        logger.exception("on_turn_complete callback error")

            # Yield a final cost event
            yield StreamEvent(type="cost", data={"total_cost_usd": self._total_cost_usd})

    async def submit_tool_result(
        self,
        tool_use_id: str,
        result: Any,
        *,
        is_error: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Manually feed a tool result back and continue the conversation."""
        tool_result_msg = {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": str(result) if not isinstance(result, str) else result,
                    "is_error": is_error,
                }
            ],
        }
        self._add_message(tool_result_msg)

        # Re-enter the query loop with existing messages
        async for event in self.submit_message("", metadata={"continuation": True}):
            yield event

    def abort(self) -> None:
        """Abort the running conversation."""
        self._aborted = True
        logger.info("Engine aborted session=%s", self._session_id)

    def reset(self) -> None:
        """Reset engine state for a fresh conversation, keeping config."""
        self._messages.clear()
        self._total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        self._permission_denials.clear()
        self._file_state_cache.clear()
        self._turn_count = 0
        self._total_cost_usd = 0.0
        self._started_at = time.time()
        self._aborted = False
        self._session_id = str(uuid.uuid4())
        self._cost_tracker.reset()
        logger.info("Engine reset, new session=%s", self._session_id)

    def get_summary(self) -> ConversationSummary:
        """Return a summary of the current conversation."""
        return ConversationSummary(
            session_id=self._session_id,
            turn_count=self._turn_count,
            message_count=len(self._messages),
            total_input_tokens=self._total_usage["input_tokens"],
            total_output_tokens=self._total_usage["output_tokens"],
            total_cost_usd=self._total_cost_usd,
            duration_seconds=time.time() - self._started_at,
            model=self.config.model,
        )

    def add_permission_denial(self, tool_name: str, reason: str) -> None:
        """Record a permission denial."""
        self._permission_denials.append(
            {
                "tool": tool_name,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_file_diff(self, path: str) -> Optional[Dict[str, Any]]:
        """Check if a file changed since last snapshot.

        Returns a dict with old_hash, new_hash, changed flag, or None if
        the file was never tracked.
        """
        snapshot = self._file_state_cache.get(path)
        if snapshot is None:
            return None

        new_hash = self._hash_file(path)
        changed = new_hash != snapshot.content_hash
        return {
            "path": path,
            "old_hash": snapshot.content_hash,
            "new_hash": new_hash,
            "changed": changed,
        }

    # ---- callbacks ----

    def on_event(self, callback: Callable[[StreamEvent], None]) -> None:
        """Register a synchronous callback for every stream event."""
        self._on_event = callback

    def on_turn_complete(self, callback: Callable[[int], None]) -> None:
        """Register callback fired after each turn completes."""
        self._on_turn_complete = callback

    # ---- properties ----

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Return a defensive copy of the message history."""
        return list(self._messages)

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def total_usage(self) -> Dict[str, int]:
        return dict(self._total_usage)

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    @property
    def permission_denials(self) -> List[Dict[str, Any]]:
        return list(self._permission_denials)

    # ---- internal helpers ----

    def _add_message(self, message: Dict[str, Any]) -> None:
        """Append a message to history with timestamp metadata."""
        message.setdefault("_meta", {})
        message["_meta"]["timestamp"] = time.time()
        message["_meta"]["turn"] = self._turn_count
        self._messages.append(message)

    def _build_system_prompt(
        self,
        *,
        extra_system: Optional[str] = None,
    ) -> str:
        """Construct the full system prompt from config parts.

        Priority (concatenated in order):
        1. custom_system_prompt (replaces default) OR default system_prompt
        2. append_system_prompt
        3. extra_system (per-turn)
        4. Permission denial context (if any)
        """
        parts: List[str] = []

        if self.config.custom_system_prompt is not None:
            parts.append(self.config.custom_system_prompt)
        elif self.config.system_prompt is not None:
            parts.append(self.config.system_prompt)
        else:
            parts.append(self._default_system_prompt())

        if self.config.append_system_prompt:
            parts.append(self.config.append_system_prompt)

        if extra_system:
            parts.append(extra_system)

        # Inject permission denial context so the model knows what was refused
        if self._permission_denials:
            denial_lines = []
            for d in self._permission_denials[-5:]:  # last 5
                denial_lines.append(
                    f"- Tool '{d['tool']}' was denied: {d['reason']}"
                )
            parts.append(
                "\n\n<permission_denials>\n"
                "The following tool uses were denied by the user:\n"
                + "\n".join(denial_lines)
                + "\nDo not retry these exact tool calls."
                + "\n</permission_denials>"
            )

        return "\n\n".join(parts)

    @staticmethod
    def _default_system_prompt() -> str:
        """Fallback system prompt when none is provided."""
        return (
            "You are Claude, an AI assistant made by Anthropic. You are helpful, "
            "harmless, and honest. You have access to tools that let you interact "
            "with the user's computer - reading and writing files, running commands, "
            "and searching codebases. Use these tools to help the user with their "
            "software engineering tasks. Always explain what you're doing before "
            "taking action."
        )

    def _accumulate_usage(self, usage: Dict[str, int]) -> None:
        """Add usage from a single API call to running totals."""
        for key in self._total_usage:
            self._total_usage[key] += usage.get(key, 0)

        # Update cost
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)

        cost = estimate_cost_usd(
            model=self.config.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_tokens=cache_creation,
            cache_read_tokens=cache_read,
        )
        self._total_cost_usd += cost

        # Per-model tracking
        self._cost_tracker.add(
            model=self.config.model,
            usage=ModelUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation,
                cache_read_tokens=cache_read,
                cost_usd=cost,
            ),
        )

    def _model_context_window(self) -> int:
        """Return the context window size for the configured model."""
        model = self.config.model.lower()
        if "opus" in model:
            return 200_000
        if "sonnet" in model:
            return 200_000
        if "haiku" in model:
            return 200_000
        # Default for unknown models
        return 200_000

    def _build_stop_hooks(self) -> List[Any]:
        """Create the default set of stop hooks."""
        hooks: List[Any] = []
        hooks.append(MaxTurnsStopHook(max_turns=self.config.max_turns))
        if self.config.max_budget_usd is not None:
            hooks.append(BudgetStopHook(max_budget_usd=self.config.max_budget_usd))
        return hooks

    def _refresh_file_state_cache(self) -> None:
        """Snapshot all tracked files (from tool results) for diff detection."""
        cwd = Path(self.config.cwd).resolve()
        # Find file paths referenced in recent tool results
        paths_seen: set[str] = set()
        for msg in self._messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        # Look for file paths in tool use blocks
                        inp = block.get("input", {})
                        if isinstance(inp, dict):
                            for key in ("file_path", "path", "file_name"):
                                fp = inp.get(key)
                                if fp and isinstance(fp, str):
                                    paths_seen.add(fp)

        for path_str in paths_seen:
            try:
                p = Path(path_str)
                if not p.is_absolute():
                    p = cwd / p
                if p.exists() and p.is_file():
                    content_hash = self._hash_file(str(p))
                    stat = p.stat()
                    self._file_state_cache[str(p)] = FileSnapshot(
                        path=str(p),
                        content_hash=content_hash,
                        modified_at=stat.st_mtime,
                        size=stat.st_size,
                    )
            except OSError:
                pass

    @staticmethod
    def _hash_file(path: str) -> str:
        """Return SHA-256 hex digest of a file's content."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
        except OSError:
            return ""
        return h.hexdigest()
