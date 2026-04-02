"""Query package — core conversation loop and supporting modules."""

from .config import QueryConfig
from .query import QueryParams, query
from .stop_hooks import (
    BudgetStopHook,
    MaxTurnsStopHook,
    StopHook,
    StopHookResult,
    TimeoutStopHook,
)
from .token_budget import TokenBudget
from .transitions import LoopAction, LoopState, StopReason

__all__ = [
    "QueryConfig",
    "QueryParams",
    "query",
    "BudgetStopHook",
    "MaxTurnsStopHook",
    "StopHook",
    "StopHookResult",
    "TimeoutStopHook",
    "TokenBudget",
    "LoopAction",
    "LoopState",
    "StopReason",
]
