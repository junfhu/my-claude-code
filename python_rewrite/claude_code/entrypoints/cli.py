"""
Bootstrap entrypoint for Claude Code CLI.

Implements fast-path dispatchers for startup speed. This module is designed
to import as little as possible at module level, deferring heavy imports
to the specific code paths that need them. This keeps `claude --version`
and `claude --help` snappy.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Optional, Tuple

import click


# ---------------------------------------------------------------------------
# Lightweight helpers (no heavy imports)
# ---------------------------------------------------------------------------

_BOOT_TS = time.monotonic()


def _fast_version() -> str:
    """Return version string without importing the full package."""
    # Try the lightweight path first: read from a static file / env var
    ver = os.environ.get("CLAUDE_CODE_VERSION")
    if ver:
        return ver
    # Fallback: import only the package __init__
    from claude_code import __version__

    return __version__


def _resolve_api_key(explicit: Optional[str]) -> Optional[str]:
    """Resolve the API key from CLI flag, env vars, or credential store."""
    if explicit:
        return explicit
    for env in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"):
        val = os.environ.get(env)
        if val:
            return val
    # Try reading from credential file
    cred_path = os.path.expanduser("~/.claude/credentials.json")
    if os.path.isfile(cred_path):
        try:
            import json

            with open(cred_path, "r") as fh:
                data = json.load(fh)
            return data.get("api_key") or data.get("apiKey")
        except Exception:
            pass
    return None


def _detect_pipe_mode() -> bool:
    """Return True when stdin is piped / not a TTY."""
    return not sys.stdin.isatty()


def _read_stdin_prompt() -> Optional[str]:
    """If stdin has piped data, read it and return as a prompt string."""
    if _detect_pipe_mode():
        try:
            data = sys.stdin.read()
            if data.strip():
                return data.strip()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Click CLI definition
# ---------------------------------------------------------------------------

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("prompt", required=False, default=None)
@click.option("--version", "-v", is_flag=True, help="Print version and exit.")
@click.option("--model", "-m", type=str, default=None, help="Model to use (e.g. claude-sonnet-4-20250514).")
@click.option(
    "--print",
    "-p",
    "print_mode",
    is_flag=True,
    help="Non-interactive (headless) mode — print response and exit.",
)
@click.option(
    "--output-format",
    type=click.Choice(["text", "json", "stream-json"], case_sensitive=False),
    default="text",
    help="Output format for --print mode.",
)
@click.option("--resume", "-r", is_flag=True, help="Resume the last conversation.")
@click.option(
    "--resume-id",
    type=str,
    default=None,
    help="Resume a specific conversation by session ID.",
)
@click.option(
    "--permission-mode",
    type=click.Choice(["default", "plan", "auto-edit", "full-auto"], case_sensitive=False),
    default=None,
    help="Permission mode for tool execution.",
)
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
@click.option("--debug", is_flag=True, help="Enable debug logging (implies --verbose).")
@click.option(
    "--max-turns",
    type=int,
    default=None,
    help="Maximum agentic turns (default: unlimited in interactive, 100 in headless).",
)
@click.option("--system-prompt", type=str, default=None, help="Override the system prompt entirely.")
@click.option(
    "--append-system-prompt",
    type=str,
    default=None,
    help="Append text to the default system prompt.",
)
@click.option("--dump-system-prompt", is_flag=True, help="Print the system prompt and exit.")
@click.option(
    "--add-dir",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Additional directories to include in context.",
)
@click.option("--bare", is_flag=True, help="Minimal UI mode (no chrome).")
@click.option(
    "--api-key",
    type=str,
    default=None,
    envvar="ANTHROPIC_API_KEY",
    help="Anthropic API key.",
)
@click.option("--max-budget", type=float, default=None, help="Maximum USD budget for this session.")
@click.option("--no-telemetry", is_flag=True, help="Disable telemetry collection.")
@click.option(
    "--profile",
    type=str,
    default=None,
    help="Configuration profile to use (~/.claude/profiles/<name>.json).",
)
@click.option("--vim", is_flag=True, help="Enable vim mode for the input widget.")
@click.option(
    "--color/--no-color",
    default=True,
    help="Enable or disable color output.",
)
def main(
    prompt: Optional[str],
    version: bool,
    model: Optional[str],
    print_mode: bool,
    output_format: str,
    resume: bool,
    resume_id: Optional[str],
    permission_mode: Optional[str],
    verbose: bool,
    debug: bool,
    max_turns: Optional[int],
    system_prompt: Optional[str],
    append_system_prompt: Optional[str],
    dump_system_prompt: bool,
    add_dir: Tuple[str, ...],
    bare: bool,
    api_key: Optional[str],
    max_budget: Optional[float],
    no_telemetry: bool,
    profile: Optional[str],
    vim: bool,
    color: bool,
) -> None:
    """Claude Code -- AI coding assistant for the terminal."""
    # ------------------------------------------------------------------
    # Fast-path: --version
    # ------------------------------------------------------------------
    if version:
        click.echo(f"claude-code {_fast_version()}")
        raise SystemExit(0)

    # ------------------------------------------------------------------
    # Fast-path: --dump-system-prompt
    # ------------------------------------------------------------------
    if dump_system_prompt:
        _handle_dump_system_prompt(system_prompt, append_system_prompt)
        raise SystemExit(0)

    # ------------------------------------------------------------------
    # Environment flags
    # ------------------------------------------------------------------
    if bare:
        os.environ["CLAUDE_CODE_SIMPLE"] = "1"
    if debug:
        os.environ["CLAUDE_CODE_DEBUG"] = "1"
        verbose = True
    if verbose:
        os.environ["CLAUDE_CODE_VERBOSE"] = "1"
    if no_telemetry:
        os.environ["CLAUDE_CODE_NO_TELEMETRY"] = "1"
    if not color:
        os.environ["NO_COLOR"] = "1"
    if vim:
        os.environ["CLAUDE_CODE_VIM_MODE"] = "1"

    # ------------------------------------------------------------------
    # Resolve API key
    # ------------------------------------------------------------------
    resolved_key = _resolve_api_key(api_key)
    if resolved_key:
        os.environ["ANTHROPIC_API_KEY"] = resolved_key

    # ------------------------------------------------------------------
    # Piped stdin → treat as prompt
    # ------------------------------------------------------------------
    if prompt is None:
        piped = _read_stdin_prompt()
        if piped is not None:
            prompt = piped
            # Force headless when piped and no explicit --print flag
            if not print_mode and not sys.stdin.isatty():
                print_mode = True

    # ------------------------------------------------------------------
    # Default max_turns
    # ------------------------------------------------------------------
    if max_turns is None:
        max_turns = 100 if print_mode else 0  # 0 = unlimited in interactive

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------
    import asyncio

    try:
        asyncio.run(
            _run(
                prompt=prompt,
                model=model,
                print_mode=print_mode,
                output_format=output_format,
                resume=resume,
                resume_id=resume_id,
                permission_mode=permission_mode,
                verbose=verbose,
                debug=debug,
                max_turns=max_turns,
                system_prompt=system_prompt,
                append_system_prompt=append_system_prompt,
                add_dirs=list(add_dir),
                bare=bare,
                max_budget=max_budget,
                profile=profile,
                vim=vim,
                boot_time=_BOOT_TS,
            )
        )
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        raise SystemExit(130)


# ---------------------------------------------------------------------------
# Deferred heavy-lifting
# ---------------------------------------------------------------------------


def _handle_dump_system_prompt(
    system_prompt: Optional[str],
    append_system_prompt: Optional[str],
) -> None:
    """Print the effective system prompt and exit."""
    from claude_code.main import build_system_prompt

    sp = build_system_prompt(
        override=system_prompt,
        append=append_system_prompt,
    )
    click.echo(sp)


async def _run(
    *,
    prompt: Optional[str],
    model: Optional[str],
    print_mode: bool,
    output_format: str,
    resume: bool,
    resume_id: Optional[str],
    permission_mode: Optional[str],
    verbose: bool,
    debug: bool,
    max_turns: int,
    system_prompt: Optional[str],
    append_system_prompt: Optional[str],
    add_dirs: list[str],
    bare: bool,
    max_budget: Optional[float],
    profile: Optional[str],
    vim: bool,
    boot_time: float,
) -> None:
    """Main async entry point — delegates to :mod:`claude_code.main`."""
    from claude_code.main import run

    await run(
        prompt=prompt,
        model=model,
        print_mode=print_mode,
        output_format=output_format,
        resume=resume,
        resume_id=resume_id,
        permission_mode=permission_mode,
        verbose=verbose,
        debug=debug,
        max_turns=max_turns,
        system_prompt=system_prompt,
        append_system_prompt=append_system_prompt,
        add_dirs=add_dirs,
        bare=bare,
        max_budget=max_budget,
        profile=profile,
        vim=vim,
        boot_time=boot_time,
    )


# ---------------------------------------------------------------------------
# Allow `python -m claude_code.entrypoints.cli`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
