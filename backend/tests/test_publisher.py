"""Tests for the GitHub review publisher service."""

import json

import httpx
import pytest

from backend.app.schemas.finding import RawAgentFinding
from backend.app.services.github_client import GitHubAuthenticationError, GitHubClient
from backend.app.services.review_publisher import (
    build_review_payload,
    determine_review_event,
    format_finding_comment,
    format_review_body,
    publish_pull_request_review,
)


def _sample_finding_critical() -> RawAgentFinding:
    return RawAgentFinding(
        category="security",
        severity="critical",
        file="app/auth.py",
        line_start=10,
        line_end=15,
        title="Hardcoded JWT Secret",
        explanation="The JWT secret is hardcoded in cleartext in the repository.",
        evidence="JWT_SECRET = 'my-secret-123'",
        suggested_fix="JWT_SECRET = os.environ['JWT_SECRET']",
        confidence=0.98,
    )


def _sample_finding_low() -> RawAgentFinding:
    return RawAgentFinding(
        category="maintainability",
        severity="low",
        file="app/utils.py",
        line_start=20,
        line_end=20,
        title="Unused variable",
        explanation="The variable 'unused_counter' is assigned but never referenced.",
        evidence="unused_counter = 0",
        suggested_fix=None,
        confidence=0.85,
    )


def test_format_finding_comment_with_fix() -> None:
    finding = _sample_finding_critical()
    comment = format_finding_comment(finding)

    assert "[CRITICAL] Hardcoded JWT Secret" in comment
    assert "**Category:** `security`" in comment
    assert "0.98" in comment
    assert "JWT_SECRET = 'my-secret-123'" in comment
    assert "```suggestion" in comment
    assert "os.environ['JWT_SECRET']" in comment


def test_format_finding_comment_without_fix() -> None:
    finding = _sample_finding_low()
    comment = format_finding_comment(finding)

    assert "[LOW] Unused variable" in comment
    assert "```suggestion" not in comment
    assert "unused_counter = 0" in comment


def test_format_review_body_clean_pr() -> None:
    body = format_review_body(summary="All clean!", findings=[])
    assert "Executive Summary" in body
    assert "All clean!" in body
    assert "No issues identified" in body
    assert "| Category |" not in body


def test_format_review_body_with_findings() -> None:
    findings = [_sample_finding_critical(), _sample_finding_low()]
    body = format_review_body(
        summary="Found security problems.", findings=findings, model="gemini-2.5-flash"
    )

    assert "Found security problems." in body
    assert "Findings Overview" in body
    assert "Total Issues: **2**" in body
    assert "| `security` | 1 |" in body
    assert "| `maintainability` | 1 |" in body
    assert "using gemini-2.5-flash" in body


def test_determine_review_event() -> None:
    # 0 findings -> APPROVE
    assert determine_review_event([]) == "APPROVE"

    # Only low / medium -> COMMENT
    assert determine_review_event([_sample_finding_low()]) == "COMMENT"

    # Critical or high -> REQUEST_CHANGES
    assert determine_review_event([_sample_finding_critical()]) == "REQUEST_CHANGES"
    assert (
        determine_review_event([_sample_finding_critical(), _sample_finding_low()])
        == "REQUEST_CHANGES"
    )


def test_build_review_payload() -> None:
    findings = [_sample_finding_critical(), _sample_finding_low()]
    payload = build_review_payload(
        commit_id="abc123def456",
        summary="PR Review Summary",
        findings=findings,
    )

    assert payload.commit_id == "abc123def456"
    assert payload.event == "REQUEST_CHANGES"
    assert len(payload.comments) == 2

    # Multi-line comment (lines 10 to 15)
    c1 = payload.comments[0]
    assert c1.path == "app/auth.py"
    assert c1.line == 15
    assert c1.start_line == 10
    assert c1.side == "RIGHT"

    # Single-line comment (line 20)
    c2 = payload.comments[1]
    assert c2.path == "app/utils.py"
    assert c2.line == 20
    assert c2.start_line is None
    assert c2.side == "RIGHT"


@pytest.mark.asyncio
async def test_publish_review_dry_run() -> None:
    client = GitHubClient(token="")
    payload = build_review_payload(
        commit_id="abc123def456",
        summary="Review Summary",
        findings=[_sample_finding_low()],
    )

    result = await publish_pull_request_review(
        github_client=client,
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        payload=payload,
        dry_run=True,
    )

    assert result.is_dry_run is True
    assert result.id is None
    assert result.comment_count == 1
    assert result.state == "COMMENT"
    await client.close()


@pytest.mark.asyncio
async def test_publish_review_missing_token_raises_error() -> None:
    client = GitHubClient(token="")
    payload = build_review_payload(
        commit_id="abc123def456",
        summary="Review Summary",
        findings=[_sample_finding_low()],
    )

    with pytest.raises(GitHubAuthenticationError, match="GitHub token is required"):
        await publish_pull_request_review(
            github_client=client,
            owner="octocat",
            repo="Hello-World",
            pull_number=42,
            payload=payload,
            dry_run=False,
        )
    await client.close()


@pytest.mark.asyncio
async def test_publish_review_success_with_mock_transport() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert "/repos/octocat/Hello-World/pulls/42/reviews" in str(request.url)
        body = json.loads(request.content)
        assert body["commit_id"] == "head123456"
        assert body["event"] == "REQUEST_CHANGES"
        assert len(body["comments"]) == 1
        assert body["comments"][0]["path"] == "app/auth.py"
        assert body["comments"][0]["start_line"] == 10
        assert body["comments"][0]["line"] == 15

        return httpx.Response(
            200,
            json={
                "id": 445566,
                "html_url": "https://github.com/octocat/Hello-World/pull/42#pullrequestreview-445566",
                "state": "CHANGES_REQUESTED",
                "user": {"login": "codecourt-bot"},
            },
        )

    transport = httpx.MockTransport(handler)
    client = GitHubClient(token="ghp_fake_valid_token_123")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://api.github.com")

    payload = build_review_payload(
        commit_id="head123456",
        summary="Found critical vulnerability",
        findings=[_sample_finding_critical()],
    )

    result = await publish_pull_request_review(
        github_client=client,
        owner="octocat",
        repo="Hello-World",
        pull_number=42,
        payload=payload,
        dry_run=False,
    )

    assert result.is_dry_run is False
    assert result.id == 445566
    assert (
        result.html_url == "https://github.com/octocat/Hello-World/pull/42#pullrequestreview-445566"
    )
    assert result.comment_count == 1
    assert result.state == "CHANGES_REQUESTED"
    await client.close()
