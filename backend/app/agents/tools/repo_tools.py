"""Read-only repository tools for code review agents.

All tool executions are scoped to the target PR repository and commit ref,
enforce strict 10s timeouts, cap maximum output sizes, and wrap results
in untrusted-content delimiters to prevent prompt injection.
"""

import logging

from backend.app.agents.tools.base import (
    MAX_FILE_LINES_READ,
    execute_tool_with_bounds,
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


async def read_file_tool(
    owner: str,
    repo: str,
    ref: str,
    params: ReadFileParams,
    github_client: GitHubClient,
) -> ToolResult:
    """Read contents of a repository file at a specific commit ref with optional line bounds."""

    async def _action() -> str:
        file_obj = await github_client.get_file_content(
            owner=owner,
            repo=repo,
            file_path=params.file_path,
            ref=ref,
        )

        lines = file_obj.content.splitlines()
        total_lines = len(lines)

        start = params.start_line or 1
        end = params.end_line or total_lines

        # Bound line numbers within actual file range
        start_idx = max(1, start) - 1
        end_idx = min(total_lines, end)

        if start_idx >= total_lines or start_idx > end_idx:
            return f"File '{params.file_path}' has {total_lines} lines; requested range {start}-{end} is out of bounds."

        selected_lines = lines[start_idx:end_idx]

        # Enforce maximum lines read limit
        if len(selected_lines) > MAX_FILE_LINES_READ:
            selected_lines = selected_lines[:MAX_FILE_LINES_READ]
            notice = f"[Notice: Displaying first {MAX_FILE_LINES_READ} lines of requested range]\n"
        else:
            notice = ""

        formatted_lines = [
            f"{start_idx + i + 1:4d} | {line}" for i, line in enumerate(selected_lines)
        ]

        header = f"File: {params.file_path} (lines {start_idx + 1}-{start_idx + len(selected_lines)} of {total_lines})\n"
        return header + notice + "\n".join(formatted_lines)

    return await execute_tool_with_bounds("read_file", _action)


async def search_repo_tool(
    owner: str,
    repo: str,
    ref: str,
    params: SearchRepoParams,
    github_client: GitHubClient,
) -> ToolResult:
    """Search repository code for a keyword or symbol query."""

    async def _action() -> str:
        items = await github_client.search_code(
            owner=owner,
            repo=repo,
            query=params.query,
            max_results=params.max_results,
        )

        if not items:
            return f"No code matches found for query '{params.query}' in {owner}/{repo}."

        lines = [f"Found {len(items)} match(es) for query '{params.query}':"]
        for item in items:
            path = item.get("path", "unknown")
            sha = item.get("sha", "")
            sha_part = f" (sha: {sha})" if sha else ""
            lines.append(f"- {path}{sha_part}")

        return "\n".join(lines)

    return await execute_tool_with_bounds("search_repo", _action)


async def get_file_history_tool(
    owner: str,
    repo: str,
    ref: str,
    params: GetFileHistoryParams,
    github_client: GitHubClient,
) -> ToolResult:
    """Retrieve recent git commit history touching a specific repository file."""

    async def _action() -> str:
        commits = await github_client.get_file_commits(
            owner=owner,
            repo=repo,
            file_path=params.file_path,
            ref=ref,
            limit=params.limit,
        )

        if not commits:
            return f"No commit history found for file '{params.file_path}' at ref {ref}."

        lines = [
            f"Commit history for '{params.file_path}' (latest {len(commits)} commits at {ref}):"
        ]
        for c in commits:
            date_str = f" on {c.date}" if c.date else ""
            lines.append(f"- [{c.sha}] by {c.author}{date_str}: {c.message}")

        return "\n".join(lines)

    return await execute_tool_with_bounds("get_file_history", _action)


async def get_pr_metadata_tool(
    owner: str,
    repo: str,
    default_pull_number: int,
    params: GetPRMetadataParams,
    github_client: GitHubClient,
) -> ToolResult:
    """Retrieve pull request metadata including title, author, branch, and description."""

    async def _action() -> str:
        target_pr = params.pull_number or default_pull_number
        meta = await github_client.get_pull_request(
            owner=owner,
            repo=repo,
            pull_number=target_pr,
        )

        body_text = meta.body.strip() if meta.body else "(No description provided)"

        return (
            f"Pull Request #{meta.number}: {meta.title}\n"
            f"Author: {meta.author}\n"
            f"State: {meta.state}\n"
            f"Base: {meta.base_ref} <- Head: {meta.head_ref} ({meta.head_sha})\n"
            f"Description:\n{body_text}"
        )

    return await execute_tool_with_bounds("get_pr_metadata", _action)
