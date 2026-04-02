"""
Model pricing data.

Per-token costs for all Claude models used in cost tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ModelCost:
    """Per-token pricing for a model."""
    input_per_million: float   # USD per 1M input tokens
    output_per_million: float  # USD per 1M output tokens
    cache_read_per_million: float = 0.0
    cache_write_per_million: float = 0.0


# Pricing as of 2025
MODEL_COSTS: dict[str, ModelCost] = {
    # Claude 4 family
    "claude-opus-4-20250514": ModelCost(15.0, 75.0, 1.5, 18.75),
    "claude-sonnet-4-20250514": ModelCost(3.0, 15.0, 0.3, 3.75),
    # Claude 3.7
    "claude-3-7-sonnet-20250219": ModelCost(3.0, 15.0, 0.3, 3.75),
    # Claude 3.5 family
    "claude-3-5-sonnet-20241022": ModelCost(3.0, 15.0, 0.3, 3.75),
    "claude-3-5-sonnet-20240620": ModelCost(3.0, 15.0, 0.3, 3.75),
    "claude-3-5-haiku-20241022": ModelCost(0.8, 4.0, 0.08, 1.0),
    # Claude 3 family
    "claude-3-opus-20240229": ModelCost(15.0, 75.0, 1.5, 18.75),
    "claude-3-sonnet-20240229": ModelCost(3.0, 15.0, 0.3, 3.75),
    "claude-3-haiku-20240307": ModelCost(0.25, 1.25, 0.03, 0.3),
}

# Short aliases
MODEL_ALIASES: dict[str, str] = {
    "claude-opus-4": "claude-opus-4-20250514",
    "claude-sonnet-4": "claude-sonnet-4-20250514",
    "claude-3.7-sonnet": "claude-3-7-sonnet-20250219",
    "claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-3.5-haiku": "claude-3-5-haiku-20241022",
    "claude-3-opus": "claude-3-opus-20240229",
    "claude-3-sonnet": "claude-3-sonnet-20240229",
    "claude-3-haiku": "claude-3-haiku-20240307",
    "opus": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "haiku": "claude-3-5-haiku-20241022",
}


def resolve_model_id(model: str) -> str:
    """Resolve a model name/alias to a canonical model ID."""
    return MODEL_ALIASES.get(model, model)


def get_model_cost(model: str) -> Optional[ModelCost]:
    """Get pricing for a model by name or alias."""
    resolved = resolve_model_id(model)
    cost = MODEL_COSTS.get(resolved)
    if cost:
        return cost
    # Fuzzy match
    for key, val in MODEL_COSTS.items():
        if model in key or key in model:
            return val
    return None


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Optional[float]:
    """Calculate the cost in USD for a request."""
    cost = get_model_cost(model)
    if cost is None:
        return None

    total = (
        (input_tokens / 1_000_000) * cost.input_per_million
        + (output_tokens / 1_000_000) * cost.output_per_million
        + (cache_read_tokens / 1_000_000) * cost.cache_read_per_million
        + (cache_write_tokens / 1_000_000) * cost.cache_write_per_million
    )
    return round(total, 6)


def format_cost(usd: float) -> str:
    """Format a USD cost for display."""
    if usd < 0.01:
        return f"${usd:.4f}"
    if usd < 1.0:
        return f"${usd:.2f}"
    return f"${usd:.2f}"
