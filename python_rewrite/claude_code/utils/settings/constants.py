"""Settings constants — setting sources and feature flags."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class SettingSource(str, Enum):
    POLICY_SETTINGS = "policySettings"
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"


# Whether each setting source is enabled
_enabled_sources: dict[SettingSource, bool] = {
    SettingSource.POLICY_SETTINGS: True,
    SettingSource.USER_SETTINGS: True,
    SettingSource.PROJECT_SETTINGS: True,
}


def is_setting_source_enabled(source: SettingSource | str) -> bool:
    if isinstance(source, str):
        try:
            source = SettingSource(source)
        except ValueError:
            return True
    return _enabled_sources.get(source, True)


def set_setting_source_enabled(source: SettingSource, enabled: bool) -> None:
    _enabled_sources[source] = enabled
