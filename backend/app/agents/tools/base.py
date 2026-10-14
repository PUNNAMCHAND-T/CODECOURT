"""Base infrastructure, constants, and untrusted-content wrapping for repository tools."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from backend.app.agents.prompts.delimiters import sanitize_untrusted_text
from backend.app.schemas.tools import ToolResult

logger = logging.getLogger(__name__)

# Named constants (PROJECT.md §4, §6, §8: no magic numbers, explicit limits)
TOOL_TIMEOUT_SECONDS: float = 10.0
MAX_TOOL_OUTPUT_BYTES: int = 50_000
MAX_TOOL_CALLS_PER_NODE: int = 5
MAX_FILE_LINES_READ: int = 500


def wrap_untrusted_tool_output(tool_name: str, raw_output: str) -> str:
    """Sanitize and enclose untrusted tool outputs in strict boundary tags.

    Neutralizes delimiter injection attempts originating in repository files,
    commit messages, or search responses.
    """
    sanitized = sanitize_untrusted_text(raw_output)
    return (
        f'<<<UNTRUSTED_TOOL_OUTPUT tool="{tool_name}">>>\n{sanitized}\n<<</UNTRUSTED_TOOL_OUTPUT>>>'
    )


async def execute_tool_with_bounds(
    tool_name: str,
    tool_coroutine_fn: Callable[[], Awaitable[str]],
    timeout_seconds: float = TOOL_TIMEOUT_SECONDS,
    max_output_bytes: int = MAX_TOOL_OUTPUT_BYTES,
) -> ToolResult:
    """Execute a tool coroutine under strict timeout and output size limits."""
    start_time = time.perf_counter()
    truncated = False

    try:
        raw_output = await asyncio.wait_for(tool_coroutine_fn(), timeout=timeout_seconds)
        execution_seconds = time.perf_counter() - start_time

        # Enforce output byte size cap
        if len(raw_output.encode("utf-8")) > max_output_bytes:
            # Truncate string to fit within byte budget
            raw_output = (
                raw_output[:max_output_bytes]
                + f"\n[TRUNCATED: Tool output exceeded {max_output_bytes} bytes limit]"
            )
            truncated = True

        wrapped_output = wrap_untrusted_tool_output(tool_name, raw_output)

        return ToolResult(
            tool_name=tool_name,
            success=True,
            output=wrapped_output,
            error=None,
            truncated=truncated,
            execution_seconds=execution_seconds,
        )

    except TimeoutError:
        execution_seconds = time.perf_counter() - start_time
        logger.warning(
            "Tool %s timed out after %.2f seconds",
            tool_name,
            timeout_seconds,
        )
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Error: Tool '{tool_name}' timed out after {timeout_seconds}s limit.",
            error=f"Timeout after {timeout_seconds}s",
            truncated=False,
            execution_seconds=execution_seconds,
        )

    except Exception as exc:
        execution_seconds = time.perf_counter() - start_time
        logger.warning("Tool %s execution failed: %s", tool_name, exc)
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Error: Tool '{tool_name}' failed with error: {exc}",
            error=str(exc),
            truncated=False,
            execution_seconds=execution_seconds,
        )
