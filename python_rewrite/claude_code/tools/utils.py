"""
Shared utility functions used across all tool implementations.

Provides:
  - File helpers: reading with line numbers, staleness checks, image detection
  - Process helpers: run subprocess, timeout management
  - String helpers: truncation, quote normalisation
  - Path helpers: resolve, sandbox checks
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_OUTPUT_CHARS = 100_000
MAX_TOOL_RESPONSE_SIZE = 800_000
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}
BINARY_EXTENSIONS = {
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flv",
    ".o", ".a", ".pyc", ".pyo", ".class",
}
DEVICE_PATH_PREFIXES = ("/dev/", "/proc/", "/sys/")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
def resolve_path(path: str, cwd: str = ".") -> Path:
    """Resolve *path* relative to *cwd*, expanding ``~``."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path(cwd) / p
    return p.resolve()


def is_device_path(path: str) -> bool:
    """Return ``True`` if *path* points to a system device / virtual FS."""
    return any(path.startswith(prefix) for prefix in DEVICE_PATH_PREFIXES)


def is_image_file(path: str) -> bool:
    """Return ``True`` if the file extension indicates an image."""
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def is_binary_file(path: str) -> bool:
    """Return ``True`` if the file extension indicates a binary format."""
    return Path(path).suffix.lower() in BINARY_EXTENSIONS


def path_is_within(child: Path, parent: Path) -> bool:
    """Return ``True`` if *child* is inside *parent* (or is *parent*)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------
def read_file_with_line_numbers(
    path: Path,
    offset: int = 0,
    limit: Optional[int] = None,
    max_line_len: int = 2000,
) -> tuple[str, int]:
    """Read a text file and return ``(text_with_line_numbers, total_lines)``.

    *offset* is 1-based.  Lines longer than *max_line_len* are truncated.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    total = len(lines)
    start = max(0, offset - 1) if offset > 0 else 0
    end = (start + limit) if limit else total
    selected = lines[start:end]

    numbered: list[str] = []
    for idx, line in enumerate(selected, start=start + 1):
        stripped = line.rstrip("\n\r")
        if len(stripped) > max_line_len:
            stripped = stripped[:max_line_len] + "... (truncated)"
        numbered.append(f"{idx:>6}\t{stripped}")

    return "\n".join(numbered), total


def read_image_as_base64(path: Path) -> tuple[str, str]:
    """Return ``(base64_data, media_type)`` for an image file."""
    data = path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return b64, mime


def file_mtime(path: Path) -> float:
    """Return modification time as a float, or 0.0 on error."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def check_file_staleness(
    path: Path,
    recorded_mtime: Optional[float],
) -> bool:
    """Return ``True`` if the file has been modified since *recorded_mtime*."""
    if recorded_mtime is None:
        return False
    return file_mtime(path) > recorded_mtime


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------
def truncate_output(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate *text* to *max_chars*, appending an indicator if cut."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return (
        text[:half]
        + f"\n\n... [{len(text) - max_chars} characters truncated] ...\n\n"
        + text[-half:]
    )


def normalize_quotes(text: str) -> str:
    r"""Normalise fancy Unicode quotes to plain ASCII equivalents."""
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def escape_for_json(text: str) -> str:
    """Minimally escape *text* for safe inclusion in a JSON string."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def pluralize(n: int, singular: str, plural: Optional[str] = None) -> str:
    """Return *singular* or *plural* depending on *n*."""
    if n == 1:
        return singular
    return plural or (singular + "s")


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------
async def run_subprocess(
    cmd: list[str] | str,
    *,
    cwd: Optional[str] = None,
    timeout: float = 120.0,
    env: Optional[dict[str, str]] = None,
    shell: bool = False,
    stdin_data: Optional[str] = None,
) -> dict[str, Any]:
    """Run a subprocess asynchronously and capture output.

    Returns a dict with keys: ``stdout``, ``stderr``, ``returncode``,
    ``duration``, ``timed_out``.
    """
    merged_env: Optional[dict[str, str]] = None
    if env is not None:
        merged_env = {**os.environ, **env}

    start = time.monotonic()
    timed_out = False
    try:
        if shell or isinstance(cmd, str):
            proc = await asyncio.create_subprocess_shell(
                cmd if isinstance(cmd, str) else " ".join(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                cwd=cwd,
                env=merged_env,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                cwd=cwd,
                env=merged_env,
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(
                    input=stdin_data.encode() if stdin_data else None
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {cmd}",
            "returncode": 127,
            "duration": time.monotonic() - start,
            "timed_out": False,
        }

    duration = time.monotonic() - start
    return {
        "stdout": stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else "",
        "stderr": stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else "",
        "returncode": proc.returncode or 0,
        "duration": duration,
        "timed_out": timed_out,
    }


def run_subprocess_sync(
    cmd: list[str] | str,
    *,
    cwd: Optional[str] = None,
    timeout: float = 120.0,
    env: Optional[dict[str, str]] = None,
    shell: bool = False,
) -> dict[str, Any]:
    """Synchronous wrapper around :func:`subprocess.run`."""
    merged_env: Optional[dict[str, str]] = None
    if env is not None:
        merged_env = {**os.environ, **env}

    start = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=merged_env,
            shell=shell if isinstance(cmd, str) else False,
        )
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
            "duration": time.monotonic() - start,
            "timed_out": True,
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": f"Command not found: {cmd}",
            "returncode": 127,
            "duration": time.monotonic() - start,
            "timed_out": False,
        }

    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "duration": time.monotonic() - start,
        "timed_out": False,
    }


# ---------------------------------------------------------------------------
# Notebook helpers
# ---------------------------------------------------------------------------
def read_notebook(path: Path) -> list[dict[str, Any]]:
    """Read a Jupyter ``.ipynb`` file and return its cells."""
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("cells", [])


def write_notebook_cell(
    path: Path,
    cell_number: int,
    new_source: str,
    cell_type: Optional[str] = None,
    edit_mode: str = "replace",
) -> dict[str, Any]:
    """Modify a Jupyter notebook cell and persist the result.

    *edit_mode* is one of ``replace``, ``insert``, ``delete``.
    Returns the updated cell list.
    """
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    cells = data.get("cells", [])

    if edit_mode == "delete":
        if 0 <= cell_number < len(cells):
            cells.pop(cell_number)
    elif edit_mode == "insert":
        new_cell = {
            "cell_type": cell_type or "code",
            "metadata": {},
            "source": new_source.splitlines(True),
            "outputs": [] if (cell_type or "code") == "code" else [],
        }
        if (cell_type or "code") == "code":
            new_cell["execution_count"] = None
        cells.insert(cell_number, new_cell)
    else:  # replace
        if 0 <= cell_number < len(cells):
            cells[cell_number]["source"] = new_source.splitlines(True)
            if cell_type:
                cells[cell_number]["cell_type"] = cell_type

    data["cells"] = cells
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"cells": cells, "total": len(cells)}


# ---------------------------------------------------------------------------
# Content extraction helpers
# ---------------------------------------------------------------------------
def extract_text_from_html(html: str) -> str:
    """Best-effort extraction of readable text from HTML."""
    try:
        from html.parser import HTMLParser

        class _Extractor(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self._parts: list[str] = []
                self._skip = False

            def handle_starttag(self, tag: str, attrs: Any) -> None:
                if tag in ("script", "style", "noscript"):
                    self._skip = True

            def handle_endtag(self, tag: str) -> None:
                if tag in ("script", "style", "noscript"):
                    self._skip = False

            def handle_data(self, data: str) -> None:
                if not self._skip:
                    self._parts.append(data)

        ex = _Extractor()
        ex.feed(html)
        return " ".join(ex._parts)
    except Exception:
        return html


def format_tool_error(message: str) -> str:
    """Wrap *message* in a standard error format."""
    return f"[ERROR] {message}"


def format_tool_warning(message: str) -> str:
    """Wrap *message* in a standard warning format."""
    return f"[WARNING] {message}"
