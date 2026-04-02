"""Theme definitions and management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ThemeName(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    LIGHT_DALTONIZED = "light-daltonized"
    DARK_DALTONIZED = "dark-daltonized"


@dataclass
class ThemeColors:
    """Color palette for a theme."""
    primary: str
    secondary: str
    accent: str
    background: str
    surface: str
    text: str
    text_muted: str
    success: str
    warning: str
    error: str
    info: str
    border: str
    diff_added: str
    diff_removed: str


THEMES: dict[ThemeName, ThemeColors] = {
    ThemeName.DARK: ThemeColors(
        primary="#c084fc", secondary="#818cf8", accent="#f472b6",
        background="#0f172a", surface="#1e293b", text="#e2e8f0",
        text_muted="#64748b", success="#4ade80", warning="#fbbf24",
        error="#f87171", info="#38bdf8", border="#334155",
        diff_added="#166534", diff_removed="#991b1b",
    ),
    ThemeName.LIGHT: ThemeColors(
        primary="#7c3aed", secondary="#4f46e5", accent="#db2777",
        background="#ffffff", surface="#f8fafc", text="#1e293b",
        text_muted="#94a3b8", success="#16a34a", warning="#d97706",
        error="#dc2626", info="#0284c7", border="#e2e8f0",
        diff_added="#dcfce7", diff_removed="#fee2e2",
    ),
    ThemeName.LIGHT_DALTONIZED: ThemeColors(
        primary="#0077bb", secondary="#33bbee", accent="#ee7733",
        background="#ffffff", surface="#f8fafc", text="#1e293b",
        text_muted="#94a3b8", success="#009988", warning="#ee7733",
        error="#cc3311", info="#0077bb", border="#e2e8f0",
        diff_added="#d4edda", diff_removed="#f8d7da",
    ),
    ThemeName.DARK_DALTONIZED: ThemeColors(
        primary="#33bbee", secondary="#0077bb", accent="#ee7733",
        background="#0f172a", surface="#1e293b", text="#e2e8f0",
        text_muted="#64748b", success="#009988", warning="#ee7733",
        error="#cc3311", info="#33bbee", border="#334155",
        diff_added="#166534", diff_removed="#991b1b",
    ),
}


_current_theme: ThemeName = ThemeName.DARK


def get_theme() -> ThemeColors:
    return THEMES[_current_theme]


def set_theme(name: ThemeName | str) -> None:
    global _current_theme
    if isinstance(name, str):
        name = ThemeName(name)
    _current_theme = name


def get_theme_name() -> ThemeName:
    return _current_theme
