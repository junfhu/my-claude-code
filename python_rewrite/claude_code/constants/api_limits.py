"""
Anthropic API limits.

Server-side limits enforced by the Anthropic API.  Keep this file dependency-free
to prevent circular imports.

Last verified: 2025-12-22
Source: api/api/schemas/messages/blocks/ and api/api/config.py
"""

from __future__ import annotations

__all__ = [
    # Image limits
    "API_IMAGE_MAX_BASE64_SIZE",
    "IMAGE_TARGET_RAW_SIZE",
    "IMAGE_MAX_WIDTH",
    "IMAGE_MAX_HEIGHT",
    # PDF limits
    "PDF_TARGET_RAW_SIZE",
    "API_PDF_MAX_PAGES",
    "PDF_EXTRACT_SIZE_THRESHOLD",
    "PDF_MAX_EXTRACT_SIZE",
    "PDF_MAX_PAGES_PER_READ",
    "PDF_AT_MENTION_INLINE_THRESHOLD",
    # Media limits
    "API_MAX_MEDIA_PER_REQUEST",
]

# =============================================================================
# IMAGE LIMITS
# =============================================================================

API_IMAGE_MAX_BASE64_SIZE: int = 5 * 1024 * 1024
"""Maximum base64-encoded image size (5 MB).

The API rejects images where the base64 string length exceeds this value.
Note: This is the base64 length, NOT raw bytes.  Base64 increases size by ~33%.
"""

IMAGE_TARGET_RAW_SIZE: int = (API_IMAGE_MAX_BASE64_SIZE * 3) // 4
"""Target raw image size to stay under base64 limit after encoding (3.75 MB).

Base64 encoding increases size by 4/3, so:
``raw_size * 4/3 = base64_size`` → ``raw_size = base64_size * 3/4``.
"""

IMAGE_MAX_WIDTH: int = 2000
"""Client-side maximum width for image resizing.

The API internally resizes images larger than 1568 px, but this is handled
server-side and doesn't cause errors.
"""

IMAGE_MAX_HEIGHT: int = 2000
"""Client-side maximum height for image resizing."""

# =============================================================================
# PDF LIMITS
# =============================================================================

PDF_TARGET_RAW_SIZE: int = 20 * 1024 * 1024
"""Maximum raw PDF file size (20 MB).

The API has a 32 MB total request size limit.  Base64 encoding increases size
by ~33% (4/3), so 20 MB raw → ~27 MB base64, leaving room for context.
"""

API_PDF_MAX_PAGES: int = 100
"""Maximum number of pages in a PDF accepted by the API."""

PDF_EXTRACT_SIZE_THRESHOLD: int = 3 * 1024 * 1024
"""Size threshold (3 MB) above which PDFs are extracted into page images.

Applies to first-party API only; non-first-party always uses extraction.
"""

PDF_MAX_EXTRACT_SIZE: int = 100 * 1024 * 1024
"""Maximum PDF file size (100 MB) for the page extraction path.

PDFs larger than this are rejected to avoid processing extremely large files.
"""

PDF_MAX_PAGES_PER_READ: int = 20
"""Max pages the Read tool will extract in a single call with the pages parameter."""

PDF_AT_MENTION_INLINE_THRESHOLD: int = 10
"""PDFs with more pages than this get reference treatment on @ mention."""

# =============================================================================
# MEDIA LIMITS
# =============================================================================

API_MAX_MEDIA_PER_REQUEST: int = 100
"""Maximum number of media items (images + PDFs) per API request.

The API rejects requests exceeding this limit.  We validate client-side
to provide a clear error message.
"""
