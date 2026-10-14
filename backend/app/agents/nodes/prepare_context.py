"""Context preparation node for the review graph."""

import time
from typing import Any

from backend.app.agents.state import ReviewState
from backend.app.services.diff_parser import parse_unified_diff


def prepare_context_node(state: ReviewState) -> dict[str, Any]:
    """Parse diff and prepare input context for reviewers."""
    start_time = time.perf_counter()

    diff_text = state.get("diff_text", "")
    parsed = state.get("parsed_diff")
    if parsed is None:
        parsed = parse_unified_diff(diff_text)

    latency = time.perf_counter() - start_time

    trace = {
        "node": "prepare_context",
        "latency_seconds": latency,
        "files_count": len(parsed.files),
        "total_additions": parsed.total_additions,
        "total_deletions": parsed.total_deletions,
    }

    return {
        "parsed_diff": parsed,
        "status": "running",
        "node_latencies": {"prepare_context": latency},
        "traces": [trace],
    }
