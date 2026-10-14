"""Review publication node for the review graph."""

import time
from typing import Any

from backend.app.agents.state import ReviewState
from backend.app.services.github_client import GitHubClient
from backend.app.services.review_publisher import (
    build_review_payload,
    publish_pull_request_review,
)


async def publish_node(
    state: ReviewState,
    github_client: GitHubClient | None = None,
) -> dict[str, Any]:
    """Format and publish review to GitHub or dry-run storage."""
    start_time = time.perf_counter()

    findings = state.get("final_findings", [])
    summary = state.get("summary", "")
    head_sha = state.get("head_sha", "")
    owner = state.get("owner", "")
    repo = state.get("repo", "")
    pull_number = state.get("pull_number", 0)
    model = state.get("model", "")
    dry_run = state.get("dry_run", True)

    payload = build_review_payload(
        commit_id=head_sha,
        summary=summary,
        findings=findings,
        model=model,
    )

    client = github_client or GitHubClient(token="")
    try:
        published_review = await publish_pull_request_review(
            github_client=client,
            owner=owner,
            repo=repo,
            pull_number=pull_number,
            payload=payload,
            dry_run=dry_run,
        )
    finally:
        if github_client is None:
            await client.close()

    latency = time.perf_counter() - start_time

    cb_tripped = bool(
        state.get("circuit_breaker_tripped")
        or any(t.get("circuit_breaker_tripped") for t in state.get("traces", []))
    )
    trace = {
        "node": "publish",
        "latency_seconds": latency,
        "is_dry_run": published_review.is_dry_run,
        "published_state": published_review.state,
        "comments_count": published_review.comment_count,
        "circuit_breaker_tripped": cb_tripped,
    }

    current_status = state.get("status", "running")
    final_status = "partial" if (current_status == "partial" or cb_tripped) else "completed"

    return {
        "published_review": published_review,
        "status": final_status,
        "node_latencies": {"publish": latency},
        "traces": [trace],
    }
