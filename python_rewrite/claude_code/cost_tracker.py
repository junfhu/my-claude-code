"""
CostTracker - Token cost tracking and reporting.

Tracks per-model usage, estimates costs based on published pricing,
persists session costs to disk, and provides formatted cost summaries.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing tables  (USD per 1M tokens)
# ---------------------------------------------------------------------------

# Maps model-family prefixes to pricing.
# Prices: (input, output, cache_creation, cache_read) per 1M tokens.
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "claude-opus-4": {
        "input": 15.0,
        "output": 75.0,
        "cache_creation": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4": {
        "input": 3.0,
        "output": 15.0,
        "cache_creation": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-7-sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_creation": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-sonnet": {
        "input": 3.0,
        "output": 15.0,
        "cache_creation": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-haiku": {
        "input": 0.80,
        "output": 4.0,
        "cache_creation": 1.0,
        "cache_read": 0.08,
    },
    "claude-3-haiku": {
        "input": 0.25,
        "output": 1.25,
        "cache_creation": 0.30,
        "cache_read": 0.03,
    },
    "claude-3-opus": {
        "input": 15.0,
        "output": 75.0,
        "cache_creation": 18.75,
        "cache_read": 1.50,
    },
}

# Default fallback pricing
DEFAULT_PRICING: Dict[str, float] = {
    "input": 3.0,
    "output": 15.0,
    "cache_creation": 3.75,
    "cache_read": 0.30,
}


def _get_pricing(model: str) -> Dict[str, float]:
    """Look up pricing for a model string, falling back to default."""
    model_lower = model.lower()
    # Try exact prefix match first
    for prefix, pricing in MODEL_PRICING.items():
        if model_lower.startswith(prefix):
            return pricing
    # Fuzzy match on keywords
    for keyword in ("opus", "sonnet", "haiku"):
        if keyword in model_lower:
            for prefix, pricing in MODEL_PRICING.items():
                if keyword in prefix:
                    return pricing
    return DEFAULT_PRICING


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModelUsage:
    """Token usage for a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class ModelCostRecord:
    """Accumulated cost record for a single model."""

    model: str
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    api_call_count: int = 0
    first_used: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


@dataclass
class SessionCostSnapshot:
    """Snapshot of session costs for persistence."""

    session_id: str
    models: Dict[str, ModelCostRecord]
    total_cost_usd: float
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Estimation helpers
# ---------------------------------------------------------------------------


def estimate_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimate USD cost for a given token usage."""
    pricing = _get_pricing(model)
    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (cache_creation_tokens / 1_000_000) * pricing["cache_creation"]
        + (cache_read_tokens / 1_000_000) * pricing["cache_read"]
    )
    return cost


def add_usage(a: ModelUsage, b: ModelUsage) -> ModelUsage:
    """Merge two ModelUsage records."""
    return ModelUsage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_creation_tokens=a.cache_creation_tokens + b.cache_creation_tokens,
        cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens,
        cost_usd=a.cost_usd + b.cost_usd,
    )


# ---------------------------------------------------------------------------
# CostTracker
# ---------------------------------------------------------------------------


class CostTracker:
    """Per-model cost accumulator with persistence support."""

    def __init__(self, session_id: Optional[str] = None) -> None:
        self._session_id = session_id or ""
        self._models: Dict[str, ModelCostRecord] = {}
        self._total_cost_usd: float = 0.0

    # ---- mutation ----

    def add(self, model: str, usage: ModelUsage) -> None:
        """Record a single API call's usage."""
        record = self._models.get(model)
        if record is None:
            record = ModelCostRecord(model=model)
            self._models[model] = record

        record.total_input_tokens += usage.input_tokens
        record.total_output_tokens += usage.output_tokens
        record.total_cache_creation_tokens += usage.cache_creation_tokens
        record.total_cache_read_tokens += usage.cache_read_tokens
        record.total_cost_usd += usage.cost_usd
        record.api_call_count += 1
        record.last_used = time.time()

        self._total_cost_usd += usage.cost_usd

    def reset(self) -> None:
        """Clear all tracked costs."""
        self._models.clear()
        self._total_cost_usd = 0.0

    # ---- queries ----

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def models(self) -> Dict[str, ModelCostRecord]:
        return dict(self._models)

    def get_model_cost(self, model: str) -> Optional[ModelCostRecord]:
        return self._models.get(model)

    def total_tokens(self) -> int:
        """Return total tokens across all models."""
        total = 0
        for record in self._models.values():
            total += record.total_input_tokens + record.total_output_tokens
        return total

    # ---- formatting ----

    def format_total_cost(self) -> str:
        """Return a human-readable cost summary string."""
        lines: List[str] = []
        lines.append(f"Total session cost: ${self._total_cost_usd:.4f}")
        lines.append("")

        for model, record in sorted(self._models.items()):
            lines.append(f"  {model}:")
            lines.append(f"    API calls:       {record.api_call_count}")
            lines.append(f"    Input tokens:    {record.total_input_tokens:,}")
            lines.append(f"    Output tokens:   {record.total_output_tokens:,}")
            if record.total_cache_creation_tokens > 0:
                lines.append(
                    f"    Cache creation:  {record.total_cache_creation_tokens:,}"
                )
            if record.total_cache_read_tokens > 0:
                lines.append(
                    f"    Cache read:      {record.total_cache_read_tokens:,}"
                )
            lines.append(f"    Cost:            ${record.total_cost_usd:.4f}")
            lines.append("")

        return "\n".join(lines)

    def format_short(self) -> str:
        """One-line cost summary."""
        total_in = sum(r.total_input_tokens for r in self._models.values())
        total_out = sum(r.total_output_tokens for r in self._models.values())
        return (
            f"${self._total_cost_usd:.4f} "
            f"({total_in:,} in / {total_out:,} out)"
        )

    # ---- persistence ----

    def save_current_session_costs(self, directory: Optional[str] = None) -> str:
        """Persist session costs to a JSON file.  Returns the path written."""
        from datetime import datetime, timezone

        dir_path = Path(directory) if directory else _default_cost_dir()
        dir_path.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        snapshot = SessionCostSnapshot(
            session_id=self._session_id,
            models={k: asdict(v) for k, v in self._models.items()},  # type: ignore[arg-type]
            total_cost_usd=self._total_cost_usd,
            created_at=now,
            updated_at=now,
        )

        file_path = dir_path / f"session_{self._session_id}.json"
        with open(file_path, "w") as f:
            json.dump(asdict(snapshot), f, indent=2, default=str)

        logger.debug("Saved session costs to %s", file_path)
        return str(file_path)

    @classmethod
    def restore_cost_state_for_session(
        cls, session_id: str, directory: Optional[str] = None
    ) -> "CostTracker":
        """Load a previous session's cost state."""
        dir_path = Path(directory) if directory else _default_cost_dir()
        file_path = dir_path / f"session_{session_id}.json"

        tracker = cls(session_id=session_id)

        if not file_path.exists():
            logger.debug("No saved costs found for session %s", session_id)
            return tracker

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            for model_name, record_data in data.get("models", {}).items():
                record = ModelCostRecord(
                    model=record_data.get("model", model_name),
                    total_input_tokens=record_data.get("total_input_tokens", 0),
                    total_output_tokens=record_data.get("total_output_tokens", 0),
                    total_cache_creation_tokens=record_data.get(
                        "total_cache_creation_tokens", 0
                    ),
                    total_cache_read_tokens=record_data.get(
                        "total_cache_read_tokens", 0
                    ),
                    total_cost_usd=record_data.get("total_cost_usd", 0.0),
                    api_call_count=record_data.get("api_call_count", 0),
                    first_used=record_data.get("first_used", 0.0),
                    last_used=record_data.get("last_used", 0.0),
                )
                tracker._models[model_name] = record

            tracker._total_cost_usd = data.get("total_cost_usd", 0.0)
            logger.debug("Restored costs for session %s", session_id)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to restore session costs: %s", exc)

        return tracker


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

# Global singleton for the current process
_global_tracker: Optional[CostTracker] = None


def get_global_tracker() -> CostTracker:
    """Return (or create) the global cost tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = CostTracker()
    return _global_tracker


def set_global_tracker(tracker: CostTracker) -> None:
    """Replace the global cost tracker."""
    global _global_tracker
    _global_tracker = tracker


def add_to_total_session_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Add usage to the global tracker and return the incremental cost."""
    cost = estimate_cost_usd(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
    )
    usage = ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
        cost_usd=cost,
    )
    get_global_tracker().add(model, usage)
    return cost


def format_total_cost() -> str:
    """Format the global tracker's cost summary."""
    return get_global_tracker().format_total_cost()


def save_current_session_costs(directory: Optional[str] = None) -> str:
    """Save the global tracker's session costs."""
    return get_global_tracker().save_current_session_costs(directory)


def restore_cost_state_for_session(
    session_id: str, directory: Optional[str] = None
) -> CostTracker:
    """Restore a previous session and install as global tracker."""
    tracker = CostTracker.restore_cost_state_for_session(session_id, directory)
    set_global_tracker(tracker)
    return tracker


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _default_cost_dir() -> Path:
    """Default directory for cost data: ~/.claude/costs/"""
    home = Path.home()
    return home / ".claude" / "costs"
