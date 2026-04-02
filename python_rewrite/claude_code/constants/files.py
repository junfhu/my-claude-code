"""
File-related constants: binary extensions, binary detection, and path helpers.
"""

from __future__ import annotations

__all__ = [
    "BINARY_EXTENSIONS",
    "has_binary_extension",
    "is_binary_content",
    "BINARY_CHECK_SIZE",
]

# ============================================================================
# Binary file extensions
# ============================================================================

BINARY_EXTENSIONS: frozenset[str] = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
    # Videos
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v", ".mpeg", ".mpg",
    # Audio
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".aiff", ".opus",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".z", ".tgz", ".iso",
    # Executables/binaries
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj", ".lib",
    ".app", ".msi", ".deb", ".rpm",
    # Documents (PDF is here; FileReadTool excludes it at the call site)
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Bytecode / VM artifacts
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear", ".node", ".wasm", ".rlib",
    # Database files
    ".sqlite", ".sqlite3", ".db", ".mdb", ".idx",
    # Design / 3D
    ".psd", ".ai", ".eps", ".sketch", ".fig", ".xd", ".blend", ".3ds", ".max",
    # Flash
    ".swf", ".fla",
    # Lock/profiling data
    ".lockb", ".dat", ".data",
})
"""Binary file extensions to skip for text-based operations.

These files can't be meaningfully compared as text and are often large.
"""


def has_binary_extension(file_path: str) -> bool:
    """Check if *file_path* has a known binary extension."""
    dot_idx = file_path.rfind(".")
    if dot_idx == -1:
        return False
    ext = file_path[dot_idx:].lower()
    return ext in BINARY_EXTENSIONS


# ============================================================================
# Binary content detection
# ============================================================================

BINARY_CHECK_SIZE: int = 8192
"""Number of bytes to read for binary content detection."""


def is_binary_content(data: bytes) -> bool:
    """Check if *data* contains binary content.

    Looks for null bytes or a high proportion of non-printable characters
    in the first :data:`BINARY_CHECK_SIZE` bytes.
    """
    check_size = min(len(data), BINARY_CHECK_SIZE)
    if check_size == 0:
        return False

    non_printable = 0
    for i in range(check_size):
        byte = data[i]
        # Null byte is a strong indicator of binary
        if byte == 0:
            return True
        # Count non-printable, non-whitespace bytes
        # Printable ASCII is 32-126, plus common whitespace (9=tab, 10=LF, 13=CR)
        if byte < 32 and byte not in (9, 10, 13):
            non_printable += 1

    # If more than 10% non-printable, likely binary
    return non_printable / check_size > 0.1
