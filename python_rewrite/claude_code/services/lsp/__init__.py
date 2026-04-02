"""Services / LSP package — Language Server Protocol client."""

from .lsp_client import (
    LSPClient,
    LSPCompletionItem,
    LSPDiagnostic,
    LSPHoverResult,
    LSPLocation,
    LSPPosition,
    LSPRange,
    LSPServerConfig,
    discover_language_servers,
)

__all__ = [
    "LSPClient",
    "LSPCompletionItem",
    "LSPDiagnostic",
    "LSPHoverResult",
    "LSPLocation",
    "LSPPosition",
    "LSPRange",
    "LSPServerConfig",
    "discover_language_servers",
]
