"""Deterministic code review finding validator.

Enforces PROJECT.md Rule 23:
"Every finding MUST be validated by a deterministic validator before being accepted:
file must exist in the PR diff, line range must fall within modified lines (or file range
if whole-file), evidence must match. If validation fails, the finding is dropped (or repaired
if trivial) and logged."

Zero LLM calls. Fully deterministic, offline-capable, and auditable.
"""

import logging
from collections.abc import Sequence

from backend.app.schemas.diff import FileDiff, ParsedDiff
from backend.app.schemas.finding import (
    FindingCreate,
    FindingValidationResult,
    RawAgentFinding,
    ValidatedFinding,
)

logger = logging.getLogger(__name__)


def _normalize_line(line: str) -> str:
    """Normalize a code or diff line by trimming whitespace and leading diff prefixes."""
    line = line.strip()
    if line.startswith(("+", "-")):
        line = line[1:].strip()
    return line


def _match_file_in_diff(
    file_path: str, parsed_diff: ParsedDiff
) -> tuple[FileDiff | None, str | None]:
    """Resolve finding file path to a FileDiff in ParsedDiff.

    Tolerates common LLM path formatting artifacts such as leading './',
    leading '/', or git diff prefixes 'b/' and 'a/'.

    Returns:
        Tuple of (FileDiff or None, repaired_path or None).
    """
    clean_path = file_path.strip().lstrip("./").lstrip("/")

    # 1. Exact match with original or clean path
    direct_match = parsed_diff.get_file(file_path) or parsed_diff.get_file(clean_path)
    if direct_match:
        repaired = direct_match.file_path if direct_match.file_path != file_path else None
        return direct_match, repaired

    # 2. Match with git diff prefix removed (e.g. b/app/main.py -> app/main.py)
    if clean_path.startswith(("b/", "a/")):
        stripped_prefix = clean_path[2:]
        prefix_match = parsed_diff.get_file(stripped_prefix)
        if prefix_match:
            return prefix_match, prefix_match.file_path

    # 3. Match by suffix (e.g. LLM outputs repo/app/main.py when diff is app/main.py)
    for f in parsed_diff.files:
        fp = f.file_path
        if clean_path.endswith(fp) or fp.endswith(clean_path):
            return f, fp

    return None, None


def _verify_evidence_in_file_diff(evidence: str, file_diff: FileDiff) -> bool:
    """Verify that quoted evidence actually appears within the file's diff hunks.

    Requires at least one non-trivial evidence line (>= 3 chars) to match a hunk line,
    or normalized evidence to be a substring of combined hunk content.
    """
    if not evidence or not evidence.strip():
        return False

    raw_evidence_lines = [line.strip() for line in evidence.splitlines() if line.strip()]
    if not raw_evidence_lines:
        return False

    normalized_evidence_lines = [
        _normalize_line(line_text)
        for line_text in raw_evidence_lines
        if len(_normalize_line(line_text)) >= 3
    ]
    hunk_lines = [
        _normalize_line(line.content)
        for hunk in file_diff.hunks
        for line in hunk.lines
        if len(_normalize_line(line.content)) >= 3
    ]

    # Check if any non-trivial normalized evidence line matches a hunk line
    for ev_line in normalized_evidence_lines:
        if ev_line in hunk_lines:
            return True

    # Fallback: substring match against combined hunk text
    combined_hunk_text = " ".join(hunk_lines)
    combined_ev_text = " ".join(normalized_evidence_lines)
    return bool(combined_ev_text and combined_ev_text in combined_hunk_text)


def validate_finding(
    finding: RawAgentFinding,
    parsed_diff: ParsedDiff,
) -> ValidatedFinding:
    """Deterministically validate a single finding against the parsed diff.

    Checks:
    1. File path exists in diff (with trivial prefix repair).
    2. File is not binary and not deleted.
    3. Line numbers are positive and range intersects modified hunk lines.
    4. Evidence code is present and matches diff hunk lines.
    5. Confidence score is valid [0.0, 1.0].

    Returns:
        ValidatedFinding with is_valid, repaired flag, and drop_reason if rejected.
    """
    repair_details: list[str] = []
    repaired = False

    # 1. File path validation
    file_diff, repaired_path = _match_file_in_diff(finding.file, parsed_diff)
    if not file_diff:
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=f"file_not_in_diff: '{finding.file}'",
        )

    current_file = finding.file
    if repaired_path and repaired_path != finding.file:
        current_file = repaired_path
        repair_details.append(f"Normalized file path '{finding.file}' to '{repaired_path}'")
        repaired = True

    # 2. File status guards
    if file_diff.is_binary:
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=f"binary_file: '{file_diff.file_path}'",
        )

    if file_diff.status == "deleted":
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=f"deleted_file: '{file_diff.file_path}'",
        )

    # 3. Line range checks & repairs
    current_start = finding.line_start
    current_end = finding.line_end

    if current_start < 1 or current_end < 1:
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=f"invalid_line_numbers: [{current_start}, {current_end}] must be >= 1",
        )

    if current_start > current_end:
        # Inverted line range: trivial swap repair
        current_start, current_end = current_end, current_start
        repair_details.append(
            f"Swapped inverted line numbers: {finding.line_start}->{finding.line_end} to {current_start}->{current_end}"
        )
        repaired = True

    # Verify line range intersects with modified lines in diff
    finding_range = set(range(current_start, current_end + 1))
    overlap = finding_range.intersection(file_diff.modified_line_numbers)
    if not overlap:
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=(
                f"lines_not_in_diff: lines {current_start}-{current_end} in "
                f"'{file_diff.file_path}' do not intersect diff hunks"
            ),
        )

    # 4. Evidence verification
    if not _verify_evidence_in_file_diff(finding.evidence, file_diff):
        return ValidatedFinding(
            finding=finding,
            is_valid=False,
            drop_reason=(
                f"evidence_not_found_in_diff: quoted evidence not found in hunks of '{file_diff.file_path}'"
            ),
        )

    # 5. Confidence score clamping
    current_confidence = finding.confidence
    if current_confidence < 0.0:
        current_confidence = 0.0
        repair_details.append(f"Clamped negative confidence {finding.confidence} to 0.0")
        repaired = True
    elif current_confidence > 1.0:
        current_confidence = 1.0
        repair_details.append(f"Clamped excessive confidence {finding.confidence} to 1.0")
        repaired = True

    # Construct the final (potentially repaired) finding
    final_finding = finding
    if repaired:
        final_finding = RawAgentFinding(
            category=finding.category,
            severity=finding.severity,
            file=current_file,
            line_start=current_start,
            line_end=current_end,
            title=finding.title.strip(),
            explanation=finding.explanation.strip(),
            evidence=finding.evidence.strip(),
            suggested_fix=finding.suggested_fix.strip() if finding.suggested_fix else None,
            confidence=current_confidence,
        )

    return ValidatedFinding(
        finding=final_finding,
        is_valid=True,
        repaired=repaired,
        repair_details=repair_details,
    )


def validate_findings(
    findings: Sequence[RawAgentFinding],
    parsed_diff: ParsedDiff,
) -> FindingValidationResult:
    """Validate a collection of raw agent findings against a parsed diff.

    Drops hallucinated files/lines, verifies evidence, and repairs trivial artifacts.
    """
    accepted: list[RawAgentFinding] = []
    dropped: list[ValidatedFinding] = []
    repaired_count = 0

    for finding in findings:
        outcome = validate_finding(finding, parsed_diff)
        if outcome.is_valid:
            accepted.append(outcome.finding)
            if outcome.repaired:
                repaired_count += 1
        else:
            dropped.append(outcome)
            logger.warning(
                "Finding rejected by deterministic validator: file=%s, lines=%d-%d, reason=%s",
                finding.file,
                finding.line_start,
                finding.line_end,
                outcome.drop_reason,
            )

    return FindingValidationResult(
        total_evaluated=len(findings),
        accepted=accepted,
        dropped=dropped,
        repaired_count=repaired_count,
    )


def to_finding_create_models(
    result: FindingValidationResult,
    review_id: int,
    agent: str,
    include_dropped: bool = True,
) -> list[FindingCreate]:
    """Convert a FindingValidationResult into persistable FindingCreate models.

    Accepted findings receive status='active'.
    Dropped findings receive status='dropped' with the validator drop_reason.
    """
    models: list[FindingCreate] = []

    for finding in result.accepted:
        models.append(
            FindingCreate(
                review_id=review_id,
                agent=agent,
                category=finding.category,
                severity=finding.severity,
                file=finding.file,
                line_start=finding.line_start,
                line_end=finding.line_end,
                title=finding.title,
                explanation=finding.explanation,
                evidence=finding.evidence,
                suggested_fix=finding.suggested_fix,
                confidence=finding.confidence,
                status="active",
            )
        )

    if include_dropped:
        for dropped_outcome in result.dropped:
            f = dropped_outcome.finding
            models.append(
                FindingCreate(
                    review_id=review_id,
                    agent=agent,
                    category=f.category,
                    severity=f.severity,
                    file=f.file,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    title=f.title,
                    explanation=f.explanation,
                    evidence=f.evidence,
                    suggested_fix=f.suggested_fix,
                    confidence=f.confidence,
                    status="dropped",
                    drop_reason=dropped_outcome.drop_reason,
                )
            )

    return models
