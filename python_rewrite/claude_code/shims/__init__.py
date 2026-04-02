"""Shims: feature flags and build-time replacement stubs."""

from .feature_flags import feature, is_enabled

__all__ = ["feature", "is_enabled"]
