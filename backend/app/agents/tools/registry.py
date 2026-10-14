"""Tool registry and dispatcher for CodeCourt reviewer agents."""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from backend.app.agents.tools.repo_tools import (
    get_file_history_tool,
    get_pr_metadata_tool,
    read_file_tool,
    search_repo_tool,
)
from backend.app.schemas.tools import (
    GetFileHistoryParams,
    GetPRMetadataParams,
    ReadFileParams,
    SearchRepoParams,
    ToolResult,
)
from backend.app.services.github_client import GitHubClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolContext:
    """Scoped repository and pull request execution context for tools."""

    owner: str
    repo: str
    head_sha: str
    pull_number: int


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read file contents from repository at the PR's head commit. Optionally specify start_line and end_line.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to file in repository",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional 1-indexed starting line number",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional 1-indexed ending line number",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "search_repo",
        "description": "Search repository code for a keyword, symbol, or function name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword, symbol, or identifier to search for",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of search results to return (default 5, max 20)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_file_history",
        "description": "Retrieve recent git commits that modified a specific file to understand recent changes or refactors.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Relative path to file in repository",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of commits to retrieve (default 5, max 20)",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "get_pr_metadata",
        "description": "Retrieve full pull request title, author, branch names, and description.",
        "parameters": {
            "type": "object",
            "properties": {
                "pull_number": {
                    "type": "integer",
                    "description": "Optional pull request number (defaults to current PR)",
                },
            },
        },
    },
]


async def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    context: ToolContext,
    github_client: GitHubClient,
) -> ToolResult:
    """Validate arguments and dispatch tool execution to the appropriate tool handler."""
    try:
        if tool_name == "read_file":
            read_params = ReadFileParams.model_validate(arguments)
            return await read_file_tool(
                owner=context.owner,
                repo=context.repo,
                ref=context.head_sha,
                params=read_params,
                github_client=github_client,
            )

        if tool_name == "search_repo":
            search_params = SearchRepoParams.model_validate(arguments)
            return await search_repo_tool(
                owner=context.owner,
                repo=context.repo,
                ref=context.head_sha,
                params=search_params,
                github_client=github_client,
            )

        if tool_name == "get_file_history":
            history_params = GetFileHistoryParams.model_validate(arguments)
            return await get_file_history_tool(
                owner=context.owner,
                repo=context.repo,
                ref=context.head_sha,
                params=history_params,
                github_client=github_client,
            )

        if tool_name == "get_pr_metadata":
            pr_params = GetPRMetadataParams.model_validate(arguments)
            return await get_pr_metadata_tool(
                owner=context.owner,
                repo=context.repo,
                default_pull_number=context.pull_number,
                params=pr_params,
                github_client=github_client,
            )

        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Error: Unknown tool '{tool_name}'. Available tools: read_file, search_repo, get_file_history, get_pr_metadata",
            error=f"Unknown tool: {tool_name}",
        )

    except ValidationError as val_err:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Error: Invalid arguments for tool '{tool_name}': {val_err}",
            error=str(val_err),
        )
