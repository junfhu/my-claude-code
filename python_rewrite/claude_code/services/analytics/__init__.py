"""Services / Analytics package — event logging and metadata enrichment."""

from .analytics import (
    AnalyticsEvent,
    AnalyticsManager,
    AnalyticsSink,
    CallbackSink,
    FileSink,
    HttpSink,
    attach_analytics_sink,
    flush_analytics,
    log_event,
    log_event_async,
    setup_default_analytics,
    shutdown_analytics,
)
from .metadata import (
    build_api_call_metadata,
    build_session_event_metadata,
    build_tool_use_metadata,
    enrich_event,
    get_environment_metadata,
)

__all__ = [
    "AnalyticsEvent",
    "AnalyticsManager",
    "AnalyticsSink",
    "CallbackSink",
    "FileSink",
    "HttpSink",
    "attach_analytics_sink",
    "flush_analytics",
    "log_event",
    "log_event_async",
    "setup_default_analytics",
    "shutdown_analytics",
    "build_api_call_metadata",
    "build_session_event_metadata",
    "build_tool_use_metadata",
    "enrich_event",
    "get_environment_metadata",
]
