"""Tests for GitHubClient service with mock transport and realistic fixtures."""

import httpx
import pytest

from backend.app.services.github_client import (
    MAX_DIFF_BYTES,
    MAX_FILE_BYTES,
    GitHubAuthenticationError,
    GitHubClient,
    GitHubPayloadTooLargeError,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubResourceNotFoundError,
)
from backend.tests.fixtures.github_fixtures import (
    SAMPLE_DIFF,
    SAMPLE_FILE_CONTENT,
    SAMPLE_PR_RESPONSE,
)


@pytest.mark.asyncio
async def test_get_pull_request_metadata_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/repos/octocat/Hello-World/pulls/101"
        assert "application/vnd.github+json" in request.headers["Accept"]
        assert request.headers["Authorization"] == "Bearer mock-token-123"
        return httpx.Response(200, json=SAMPLE_PR_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="mock-token-123", transport=transport) as client:
        pr = await client.get_pull_request("octocat", "Hello-World", 101)

    assert pr.id == 8492019
    assert pr.number == 101
    assert pr.title == "feat(auth): implement JWT token verification with expiration"
    assert pr.author == "octocat"
    assert pr.state == "open"
    assert pr.head_sha == "7d9b9a6d89283f3e1b01c34a2c9182390234abcd"
    assert pr.base_sha == "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
    assert pr.changed_files == 2


@pytest.mark.asyncio
async def test_get_pull_request_diff_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/repos/octocat/Hello-World/pulls/101"
        assert request.headers["Accept"] == "application/vnd.github.v3.diff"
        return httpx.Response(200, text=SAMPLE_DIFF)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="mock-token-123", transport=transport) as client:
        diff = await client.get_pull_request_diff("octocat", "Hello-World", 101)

    assert "diff --git a/auth/jwt.py" in diff
    assert "insecure-hardcoded-secret" in diff


@pytest.mark.asyncio
async def test_get_file_content_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/repos/octocat/Hello-World/contents/auth/jwt.py"
        assert request.url.query.decode("utf-8") == "ref=7d9b9a6d"
        assert request.headers["Accept"] == "application/vnd.github.raw+json"
        return httpx.Response(200, text=SAMPLE_FILE_CONTENT)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="mock-token-123", transport=transport) as client:
        file_obj = await client.get_file_content(
            "octocat", "Hello-World", "auth/jwt.py", "7d9b9a6d"
        )

    assert file_obj.path == "auth/jwt.py"
    assert file_obj.sha == "7d9b9a6d"
    assert "import jwt" in file_obj.content
    assert file_obj.size == len(SAMPLE_FILE_CONTENT.encode("utf-8"))


@pytest.mark.asyncio
async def test_not_found_raises_resource_not_found_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        with pytest.raises(GitHubResourceNotFoundError) as exc_info:
            await client.get_pull_request("owner", "nonexistent", 999)
        assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unauthorized_raises_authentication_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(handler)
    async with GitHubClient(token="bad-token", transport=transport) as client:
        with pytest.raises(GitHubAuthenticationError) as exc_info:
            await client.get_pull_request("owner", "repo", 1)
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rate_limit_exceeded_raises_rate_limit_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        headers = {"x-ratelimit-remaining": "0"}
        return httpx.Response(403, json={"message": "API rate limit exceeded"}, headers=headers)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        with pytest.raises(GitHubRateLimitError) as exc_info:
            await client.get_pull_request("owner", "repo", 1)
        assert "rate limit exceeded" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_forbidden_without_rate_limit_raises_permission_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        headers = {"x-ratelimit-remaining": "50"}
        return httpx.Response(
            403, json={"message": "Resource not accessible by integration"}, headers=headers
        )

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        with pytest.raises(GitHubPermissionError) as exc_info:
            await client.get_pull_request("owner", "repo", 1)
        assert "403" in str(exc_info.value)


@pytest.mark.asyncio
async def test_transient_503_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(_s: float) -> None:
        return

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json=SAMPLE_PR_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        pr = await client.get_pull_request("octocat", "Hello-World", 101)

    assert call_count == 2
    assert pr.number == 101


@pytest.mark.asyncio
async def test_diff_exceeding_max_size_raises_payload_too_large() -> None:
    oversized_diff = "x" * (MAX_DIFF_BYTES + 10)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=oversized_diff)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        with pytest.raises(GitHubPayloadTooLargeError) as exc_info:
            await client.get_pull_request_diff("owner", "repo", 1)
        assert "exceeds limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_file_exceeding_max_size_raises_payload_too_large() -> None:
    oversized_file = "y" * (MAX_FILE_BYTES + 10)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=oversized_file)

    transport = httpx.MockTransport(handler)
    async with GitHubClient(transport=transport) as client:
        with pytest.raises(GitHubPayloadTooLargeError) as exc_info:
            await client.get_file_content("owner", "repo", "big.py", "sha123")
        assert "exceeds limit" in str(exc_info.value)
