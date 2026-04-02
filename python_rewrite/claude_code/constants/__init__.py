"""
Claude Code constants.

Re-exports from all submodules for convenient access::

    from claude_code.constants import PRODUCT_URL, get_local_iso_date
"""

from __future__ import annotations

# common
from .common import get_local_iso_date, get_local_month_year, get_session_start_date

# product
from .product import (
    CLAUDE_AI_BASE_URL,
    CLAUDE_AI_LOCAL_BASE_URL,
    CLAUDE_AI_STAGING_BASE_URL,
    PRODUCT_URL,
    get_claude_ai_base_url,
    get_remote_session_url,
    is_remote_session_local,
    is_remote_session_staging,
)

# api_limits
from .api_limits import (
    API_IMAGE_MAX_BASE64_SIZE,
    API_MAX_MEDIA_PER_REQUEST,
    API_PDF_MAX_PAGES,
    IMAGE_MAX_HEIGHT,
    IMAGE_MAX_WIDTH,
    IMAGE_TARGET_RAW_SIZE,
    PDF_AT_MENTION_INLINE_THRESHOLD,
    PDF_EXTRACT_SIZE_THRESHOLD,
    PDF_MAX_EXTRACT_SIZE,
    PDF_MAX_PAGES_PER_READ,
    PDF_TARGET_RAW_SIZE,
)

# tools
from .tools import (
    AGENT_TOOL_NAME,
    ALL_AGENT_DISALLOWED_TOOLS,
    ASK_USER_QUESTION_TOOL_NAME,
    ASYNC_AGENT_ALLOWED_TOOLS,
    BASH_TOOL_NAME,
    COORDINATOR_MODE_ALLOWED_TOOLS,
    CUSTOM_AGENT_DISALLOWED_TOOLS,
    FILE_EDIT_TOOL_NAME,
    FILE_READ_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
    GLOB_TOOL_NAME,
    GREP_TOOL_NAME,
    IN_PROCESS_TEAMMATE_ALLOWED_TOOLS,
    NOTEBOOK_EDIT_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
    SHELL_TOOL_NAMES,
    SKILL_TOOL_NAME,
    TASK_OUTPUT_TOOL_NAME,
    TODO_WRITE_TOOL_NAME,
    WEB_FETCH_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
)

# prompts
from .prompts import (
    CLAUDE_CODE_DOCS_MAP_URL,
    FRONTIER_MODEL_NAME,
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    prepend_bullets,
)

# keys
from .keys import get_growthbook_client_key

# files
from .files import BINARY_EXTENSIONS, BINARY_CHECK_SIZE, has_binary_extension, is_binary_content

# oauth
from .oauth import (
    ALL_OAUTH_SCOPES,
    ALLOWED_OAUTH_BASE_URLS,
    CLAUDE_AI_INFERENCE_SCOPE,
    CLAUDE_AI_OAUTH_SCOPES,
    CLAUDE_AI_PROFILE_SCOPE,
    CONSOLE_OAUTH_SCOPES,
    MCP_CLIENT_METADATA_URL,
    OAUTH_BETA_HEADER,
    OauthConfig,
    file_suffix_for_oauth_config,
    get_oauth_config,
)

# error_ids
from .error_ids import E_TOOL_USE_SUMMARY_GENERATION_FAILED

# figures
from .figures import (
    BLACK_CIRCLE,
    BLOCKQUOTE_BAR,
    BRIDGE_FAILED_INDICATOR,
    BRIDGE_READY_INDICATOR,
    BRIDGE_SPINNER_FRAMES,
    BULLET_OPERATOR,
    CHANNEL_ARROW,
    DIAMOND_FILLED,
    DIAMOND_OPEN,
    DOWN_ARROW,
    EFFORT_HIGH,
    EFFORT_LOW,
    EFFORT_MAX,
    EFFORT_MEDIUM,
    FLAG_ICON,
    FORK_GLYPH,
    HEAVY_HORIZONTAL,
    INJECTED_ARROW,
    LIGHTNING_BOLT,
    PAUSE_ICON,
    PLAY_ICON,
    REFERENCE_MARK,
    REFRESH_ARROW,
    TEARDROP_ASTERISK,
    UP_ARROW,
)

# xml
from .xml import (
    BASH_INPUT_TAG,
    BASH_STDERR_TAG,
    BASH_STDOUT_TAG,
    CHANNEL_MESSAGE_TAG,
    CHANNEL_TAG,
    COMMAND_ARGS_TAG,
    COMMAND_MESSAGE_TAG,
    COMMAND_NAME_TAG,
    COMMON_HELP_ARGS,
    COMMON_INFO_ARGS,
    CROSS_SESSION_MESSAGE_TAG,
    FORK_BOILERPLATE_TAG,
    FORK_DIRECTIVE_PREFIX,
    LOCAL_COMMAND_CAVEAT_TAG,
    LOCAL_COMMAND_STDERR_TAG,
    LOCAL_COMMAND_STDOUT_TAG,
    REMOTE_REVIEW_PROGRESS_TAG,
    REMOTE_REVIEW_TAG,
    TASK_ID_TAG,
    TASK_NOTIFICATION_TAG,
    TASK_TYPE_TAG,
    TEAMMATE_MESSAGE_TAG,
    TERMINAL_OUTPUT_TAGS,
    TICK_TAG,
    TOOL_USE_ID_TAG,
    ULTRAPLAN_TAG,
    WORKTREE_BRANCH_TAG,
    WORKTREE_PATH_TAG,
    WORKTREE_TAG,
)

# query_source
from .query_source import KNOWN_QUERY_SOURCES, QuerySource

# system
from .system import (
    AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX,
    AGENT_SDK_PREFIX,
    CLI_SYSPROMPT_PREFIXES,
    DEFAULT_PREFIX,
    get_attribution_header,
    get_cli_sysprompt_prefix,
)

__all__ = [
    # common
    "get_local_iso_date",
    "get_local_month_year",
    "get_session_start_date",
    # product
    "PRODUCT_URL",
    "CLAUDE_AI_BASE_URL",
    "CLAUDE_AI_STAGING_BASE_URL",
    "CLAUDE_AI_LOCAL_BASE_URL",
    "is_remote_session_staging",
    "is_remote_session_local",
    "get_claude_ai_base_url",
    "get_remote_session_url",
    # api_limits
    "API_IMAGE_MAX_BASE64_SIZE",
    "IMAGE_TARGET_RAW_SIZE",
    "IMAGE_MAX_WIDTH",
    "IMAGE_MAX_HEIGHT",
    "PDF_TARGET_RAW_SIZE",
    "API_PDF_MAX_PAGES",
    "PDF_EXTRACT_SIZE_THRESHOLD",
    "PDF_MAX_EXTRACT_SIZE",
    "PDF_MAX_PAGES_PER_READ",
    "PDF_AT_MENTION_INLINE_THRESHOLD",
    "API_MAX_MEDIA_PER_REQUEST",
    # tools
    "AGENT_TOOL_NAME",
    "ASK_USER_QUESTION_TOOL_NAME",
    "BASH_TOOL_NAME",
    "FILE_EDIT_TOOL_NAME",
    "FILE_READ_TOOL_NAME",
    "FILE_WRITE_TOOL_NAME",
    "GLOB_TOOL_NAME",
    "GREP_TOOL_NAME",
    "NOTEBOOK_EDIT_TOOL_NAME",
    "SEND_MESSAGE_TOOL_NAME",
    "SHELL_TOOL_NAMES",
    "SKILL_TOOL_NAME",
    "TASK_OUTPUT_TOOL_NAME",
    "TODO_WRITE_TOOL_NAME",
    "WEB_FETCH_TOOL_NAME",
    "WEB_SEARCH_TOOL_NAME",
    "ALL_AGENT_DISALLOWED_TOOLS",
    "CUSTOM_AGENT_DISALLOWED_TOOLS",
    "ASYNC_AGENT_ALLOWED_TOOLS",
    "IN_PROCESS_TEAMMATE_ALLOWED_TOOLS",
    "COORDINATOR_MODE_ALLOWED_TOOLS",
    # prompts
    "CLAUDE_CODE_DOCS_MAP_URL",
    "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
    "FRONTIER_MODEL_NAME",
    "prepend_bullets",
    # keys
    "get_growthbook_client_key",
    # files
    "BINARY_EXTENSIONS",
    "BINARY_CHECK_SIZE",
    "has_binary_extension",
    "is_binary_content",
    # oauth
    "CLAUDE_AI_INFERENCE_SCOPE",
    "CLAUDE_AI_PROFILE_SCOPE",
    "OAUTH_BETA_HEADER",
    "CONSOLE_OAUTH_SCOPES",
    "CLAUDE_AI_OAUTH_SCOPES",
    "ALL_OAUTH_SCOPES",
    "ALLOWED_OAUTH_BASE_URLS",
    "MCP_CLIENT_METADATA_URL",
    "OauthConfig",
    "get_oauth_config",
    "file_suffix_for_oauth_config",
    # error_ids
    "E_TOOL_USE_SUMMARY_GENERATION_FAILED",
    # figures
    "BLACK_CIRCLE",
    "BULLET_OPERATOR",
    "TEARDROP_ASTERISK",
    "UP_ARROW",
    "DOWN_ARROW",
    "LIGHTNING_BOLT",
    "EFFORT_LOW",
    "EFFORT_MEDIUM",
    "EFFORT_HIGH",
    "EFFORT_MAX",
    "PLAY_ICON",
    "PAUSE_ICON",
    "REFRESH_ARROW",
    "CHANNEL_ARROW",
    "INJECTED_ARROW",
    "FORK_GLYPH",
    "DIAMOND_OPEN",
    "DIAMOND_FILLED",
    "REFERENCE_MARK",
    "FLAG_ICON",
    "BLOCKQUOTE_BAR",
    "HEAVY_HORIZONTAL",
    "BRIDGE_SPINNER_FRAMES",
    "BRIDGE_READY_INDICATOR",
    "BRIDGE_FAILED_INDICATOR",
    # xml
    "COMMAND_NAME_TAG",
    "COMMAND_MESSAGE_TAG",
    "COMMAND_ARGS_TAG",
    "BASH_INPUT_TAG",
    "BASH_STDOUT_TAG",
    "BASH_STDERR_TAG",
    "LOCAL_COMMAND_STDOUT_TAG",
    "LOCAL_COMMAND_STDERR_TAG",
    "LOCAL_COMMAND_CAVEAT_TAG",
    "TERMINAL_OUTPUT_TAGS",
    "TICK_TAG",
    "TASK_NOTIFICATION_TAG",
    "TASK_ID_TAG",
    "TOOL_USE_ID_TAG",
    "TASK_TYPE_TAG",
    "ULTRAPLAN_TAG",
    "REMOTE_REVIEW_TAG",
    "REMOTE_REVIEW_PROGRESS_TAG",
    "TEAMMATE_MESSAGE_TAG",
    "CHANNEL_MESSAGE_TAG",
    "CHANNEL_TAG",
    "CROSS_SESSION_MESSAGE_TAG",
    "FORK_BOILERPLATE_TAG",
    "FORK_DIRECTIVE_PREFIX",
    "COMMON_HELP_ARGS",
    "COMMON_INFO_ARGS",
    "WORKTREE_TAG",
    "WORKTREE_PATH_TAG",
    "WORKTREE_BRANCH_TAG",
    # query_source
    "QuerySource",
    "KNOWN_QUERY_SOURCES",
    # system
    "DEFAULT_PREFIX",
    "AGENT_SDK_CLAUDE_CODE_PRESET_PREFIX",
    "AGENT_SDK_PREFIX",
    "CLI_SYSPROMPT_PREFIXES",
    "get_cli_sysprompt_prefix",
    "get_attribution_header",
]
