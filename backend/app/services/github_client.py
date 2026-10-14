"""GitHub REST API client for pull requests, diffs, and repository files.

Implements timeouts, bounded exponential backoff retries, size limits,
and structured error handling for GitHub API interactions.
"""

import asyncio
import logging
from typing import Any

import httpx

from backend.app.schemas.github import PullRequestMetadata, RepoFileContent
from backend.app.schemas.tools import CommitSummary

logger = logging.getLogger(__name__)

# Named constants (PROJECT.md §6 & §8: no magic numbers, explicit limits)
DEFAULT_TIMEOUT_SECONDS: float = 10.0
MAX_RETRIES: int = 3
INITIAL_BACKOFF_SECONDS: float = 0.5
MAX_DIFF_BYTES: int = 2 * 1024 * 1024  # 2 MB limit for diffs
MAX_FILE_BYTES: int = 1 * 1024 * 1024  # 1 MB limit for individual files
GITHUB_API_BASE_URL: str = "https://api.github.com"
GITHUB_API_VERSION: str = "2022-11-28"


class GitHubClientError(Exception):
    """Base exception for all GitHub client operations."""


class GitHubAuthenticationError(GitHubClientError):
    """Raised when GitHub credentials are missing, invalid, or expired (HTTP 401)."""


class GitHubPermissionError(GitHubClientError):
    """Raised when the token lacks necessary permissions (HTTP 403)."""


class GitHubRateLimitError(GitHubClientError):
    """Raised when GitHub API rate limits are exceeded (HTTP 403 / 429)."""


class GitHubResourceNotFoundError(GitHubClientError):
    """Raised when a repository, PR, or file is not found (HTTP 404)."""


class GitHubPayloadTooLargeError(GitHubClientError):
    """Raised when fetched diff or file content exceeds size limits."""


class GitHubApiError(GitHubClientError):
    """Raised for server-side or unhandled GitHub API errors (HTTP 5xx)."""


class GitHubClient:
    """Async client for interacting with the GitHub REST API."""

    def __init__(
        self,
        token: str = "",
        base_url: str = GITHUB_API_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "CodeCourt-Reviewer",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            transport=transport,
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client session."""
        await self._client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        """Execute an HTTP request with bounded exponential backoff retries.

        Retries on transient network errors and HTTP 502/503/504 responses.
        Fails fast on 4xx client errors without retrying.
        """
        last_exception: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.request(
                    method=method,
                    url=path,
                    headers=headers,
                    params=params,
                    json=json,
                )

                # Transient 5xx errors eligible for retry
                if response.status_code in {502, 503, 504} and attempt < MAX_RETRIES - 1:
                    delay = INITIAL_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "GitHub API returned %d for %s; retrying in %.2fs (attempt %d/%d)",
                        response.status_code,
                        path,
                        delay,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue

                self._handle_response_status(response, path)
                return response

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exception = exc
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "Transient network error calling %s: %s; retrying in %.2fs (attempt %d/%d)",
                        path,
                        exc,
                        delay,
                        attempt + 1,
                        MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                else:
                    break

        raise GitHubApiError(
            f"Failed to communicate with GitHub API after {MAX_RETRIES} attempts: {last_exception}"
        ) from last_exception

    def _handle_response_status(self, response: httpx.Response, path: str) -> None:
        """Map HTTP error status codes to domain-specific exceptions."""
        if response.is_success:
            return

        status_code = response.status_code
        error_msg = f"GitHub API error {status_code} on {path}: {response.text}"

        if status_code == 401:
            raise GitHubAuthenticationError(f"Authentication failed (HTTP 401): {response.text}")

        if status_code == 403:
            remaining = response.headers.get("x-ratelimit-remaining")
            if remaining == "0" or "rate limit" in response.text.lower():
                raise GitHubRateLimitError(
                    f"GitHub rate limit exceeded (HTTP 403): {response.text}"
                )
            raise GitHubPermissionError(f"Access forbidden (HTTP 403): {response.text}")

        if status_code == 429:
            raise GitHubRateLimitError(f"GitHub rate limit exceeded (HTTP 429): {response.text}")

        if status_code == 404:
            raise GitHubResourceNotFoundError(f"Resource not found (HTTP 404): {path}")

        if status_code >= 500:
            raise GitHubApiError(error_msg)

        raise GitHubClientError(error_msg)

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> PullRequestMetadata:
        """Fetch normalized metadata for a pull request.

        Args:
            owner: Repository owner/organization.
            repo: Repository name.
            pull_number: Pull request number.

        Returns:
            Validated PullRequestMetadata instance.
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}"
        response = await self._request_with_retry("GET", path)
        data = response.json()

        return PullRequestMetadata(
            id=data["id"],
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            owner=owner,
            repo=repo,
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            head_ref=data["head"]["ref"],
            base_ref=data["base"]["ref"],
            author=data["user"]["login"],
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
            html_url=data["html_url"],
            diff_url=data["diff_url"],
            changed_files=data.get("changed_files", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
        )

    async def get_pull_request_diff(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> str:
        """Fetch raw unified diff text for a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pull_number: Pull request number.

        Returns:
            Raw diff string.

        Raises:
            GitHubPayloadTooLargeError: If diff exceeds MAX_DIFF_BYTES.
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}"
        headers = {"Accept": "application/vnd.github.v3.diff"}
        response = await self._request_with_retry("GET", path, headers=headers)

        content_bytes = response.content
        if len(content_bytes) > MAX_DIFF_BYTES:
            raise GitHubPayloadTooLargeError(
                f"PR diff ({len(content_bytes)} bytes) exceeds limit of {MAX_DIFF_BYTES} bytes"
            )

        return response.text

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        file_path: str,
        ref: str,
    ) -> RepoFileContent:
        """Fetch raw content of a repository file at a specific commit SHA or ref.

        Args:
            owner: Repository owner.
            repo: Repository name.
            file_path: Relative path to the file in the repository.
            ref: Git commit SHA, branch, or tag (typically PR head_sha).

        Returns:
            RepoFileContent containing path, sha, size, and file string content.

        Raises:
            GitHubPayloadTooLargeError: If file exceeds MAX_FILE_BYTES.
        """
        path = f"/repos/{owner}/{repo}/contents/{file_path.lstrip('/')}"
        headers = {"Accept": "application/vnd.github.raw+json"}
        params = {"ref": ref}

        response = await self._request_with_retry("GET", path, headers=headers, params=params)

        content_bytes = response.content
        if len(content_bytes) > MAX_FILE_BYTES:
            raise GitHubPayloadTooLargeError(
                f"File '{file_path}' ({len(content_bytes)} bytes) exceeds limit of {MAX_FILE_BYTES} bytes"
            )

        return RepoFileContent(
            path=file_path,
            sha=ref,
            content=response.text,
            size=len(content_bytes),
        )

    async def create_pull_request_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_id: str,
        body: str,
        event: str = "COMMENT",
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Submit a pull request review with a summary body and optional inline comments.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pull_number: Pull request number.
            commit_id: The SHA of the commit that needs a review.
            body: Top-level review markdown body.
            event: Review event ('COMMENT', 'APPROVE', 'REQUEST_CHANGES').
            comments: Optional list of inline comment dictionaries.

        Returns:
            Dictionary containing the GitHub review response payload.

        Raises:
            GitHubAuthenticationError: If token is missing/invalid.
            GitHubPermissionError: If token lacks repo write access.
            GitHubResourceNotFoundError: If PR does not exist.
        """
        path = f"/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = comments

        response = await self._request_with_retry("POST", path, json=payload)
        result: dict[str, Any] = response.json()
        return result

    async def get_file_commits(
        self,
        owner: str,
        repo: str,
        file_path: str,
        ref: str,
        limit: int = 5,
    ) -> list[CommitSummary]:
        """Fetch recent commit history for a specific repository file.

        Args:
            owner: Repository owner.
            repo: Repository name.
            file_path: Relative path to the file.
            ref: Git commit SHA, branch, or tag.
            limit: Maximum number of commits to return.

        Returns:
            List of CommitSummary items.
        """
        path = f"/repos/{owner}/{repo}/commits"
        params = {
            "path": file_path.lstrip("/"),
            "sha": ref,
            "per_page": min(limit, 20),
        }
        response = await self._request_with_retry("GET", path, params=params)
        commits_data: list[dict[str, Any]] = response.json()

        results: list[CommitSummary] = []
        for item in commits_data[:limit]:
            sha = item.get("sha", "")[:7]
            commit_info = item.get("commit", {})
            author_info = commit_info.get("author", {})
            author_name = author_info.get("name", "Unknown")
            commit_date = author_info.get("date", "")
            message = commit_info.get("message", "").strip().split("\n")[0]

            results.append(
                CommitSummary(
                    sha=sha,
                    author=author_name,
                    date=commit_date,
                    message=message,
                )
            )
        return results

    async def search_code(
        self,
        owner: str,
        repo: str,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search code in repository for a keyword or symbol query.

        Args:
            owner: Repository owner.
            repo: Repository name.
            query: Keyword or symbol to search for.
            max_results: Maximum number of matching items to return.

        Returns:
            List of search result items with path and sha.
        """
        path = "/search/code"
        search_query = f"{query} repo:{owner}/{repo}"
        params = {
            "q": search_query,
            "per_page": min(max_results, 20),
        }
        try:
            response = await self._request_with_retry("GET", path, params=params)
            data: dict[str, Any] = response.json()
            items: list[dict[str, Any]] = data.get("items", [])
            return [
                {"path": item.get("path", ""), "sha": item.get("sha", "")[:7]}
                for item in items[:max_results]
            ]
        except GitHubClientError as exc:
            logger.warning("Search code failed for '%s' in %s/%s: %s", query, owner, repo, exc)
            return []
