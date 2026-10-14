"""Tests for the deterministic finding validator."""

from backend.app.schemas.diff import DiffHunk, DiffLine, FileDiff, ParsedDiff
from backend.app.schemas.finding import RawAgentFinding
from backend.app.services.finding_validator import (
    to_finding_create_models,
    validate_finding,
    validate_findings,
)


def _build_sample_diff() -> ParsedDiff:
    """Helper to create a realistic parsed diff fixture."""
    file1 = FileDiff(
        old_path="app/auth.py",
        new_path="app/auth.py",
        status="modified",
        is_binary=False,
        hunks=[
            DiffHunk(
                old_start=10,
                old_lines=5,
                new_start=10,
                new_lines=8,
                lines=[
                    DiffLine(
                        line_type="context", content="def login(username, password):", new_lineno=10
                    ),
                    DiffLine(line_type="add", content="    if not password:", new_lineno=11),
                    DiffLine(
                        line_type="add",
                        content="        raise ValueError('Empty password')",
                        new_lineno=12,
                    ),
                    DiffLine(
                        line_type="context",
                        content="    return verify_hash(username, password)",
                        new_lineno=13,
                    ),
                ],
            )
        ],
    )
    file_deleted = FileDiff(
        old_path="old_script.py",
        new_path=None,
        status="deleted",
        is_binary=False,
        hunks=[],
    )
    file_binary = FileDiff(
        old_path="assets/logo.png",
        new_path="assets/logo.png",
        status="modified",
        is_binary=True,
        hunks=[],
    )
    return ParsedDiff(files=[file1, file_deleted, file_binary])


def test_validate_valid_finding() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="security",
        severity="high",
        file="app/auth.py",
        line_start=11,
        line_end=12,
        title="Insecure empty password check",
        explanation="Checking for empty password does not enforce minimum password length.",
        evidence="if not password:\n    raise ValueError('Empty password')",
        suggested_fix="if len(password) < 8:\n    raise ValueError('Password too short')",
        confidence=0.9,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is True
    assert result.repaired is False
    assert result.drop_reason is None
    assert result.finding.file == "app/auth.py"
    assert result.finding.line_start == 11


def test_reject_file_not_in_diff() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="security",
        severity="medium",
        file="app/database.py",  # Not in diff
        line_start=10,
        line_end=12,
        title="SQL Injection",
        explanation="Query string uses direct formatting without sanitization.",
        evidence="cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
        confidence=0.8,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is False
    assert result.drop_reason is not None
    assert "file_not_in_diff" in result.drop_reason


def test_reject_lines_not_in_diff() -> None:
    diff = _build_sample_diff()
    # File is in diff, but hunk only covers lines 10-13. Line 100 is not in diff.
    finding = RawAgentFinding(
        category="performance",
        severity="medium",
        file="app/auth.py",
        line_start=100,
        line_end=105,
        title="Slow hashing loop",
        explanation="Iterating over hash table without indexing.",
        evidence="for i in range(1000): pass",
        confidence=0.75,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is False
    assert result.drop_reason is not None
    assert "lines_not_in_diff" in result.drop_reason


def test_reject_evidence_not_found_in_diff() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="security",
        severity="high",
        file="app/auth.py",
        line_start=11,
        line_end=12,
        title="Fabricated evidence issue",
        explanation="Finding claims code exists that is completely absent from the diff.",
        evidence="hardcoded_secret = 'super_secret_key_12345'",
        confidence=0.85,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is False
    assert result.drop_reason is not None
    assert "evidence_not_found_in_diff" in result.drop_reason


def test_reject_deleted_file() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="maintainability",
        severity="low",
        file="old_script.py",
        line_start=1,
        line_end=5,
        title="Deprecated script",
        explanation="Script is being deleted.",
        evidence="print('legacy')",
        confidence=0.5,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is False
    assert result.drop_reason is not None
    assert "deleted_file" in result.drop_reason


def test_reject_binary_file() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="maintainability",
        severity="low",
        file="assets/logo.png",
        line_start=1,
        line_end=1,
        title="Binary asset check",
        explanation="Image asset is too large.",
        evidence="PNG image data",
        confidence=0.5,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is False
    assert result.drop_reason is not None
    assert "binary_file" in result.drop_reason


def test_repair_path_with_git_diff_prefix() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="security",
        severity="high",
        file="b/app/auth.py",  # Prefixed with git diff 'b/'
        line_start=11,
        line_end=12,
        title="Insecure password check",
        explanation="Explanation text here.",
        evidence="if not password:",
        confidence=0.9,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is True
    assert result.repaired is True
    assert result.finding.file == "app/auth.py"
    assert any("Normalized file path" in r for r in result.repair_details)


def test_repair_path_with_relative_dots() -> None:
    diff = _build_sample_diff()
    finding = RawAgentFinding(
        category="security",
        severity="high",
        file="./app/auth.py",  # Prefixed with './'
        line_start=11,
        line_end=12,
        title="Insecure password check",
        explanation="Explanation text here.",
        evidence="if not password:",
        confidence=0.9,
    )

    result = validate_finding(finding, diff)
    assert result.is_valid is True
    assert result.finding.file == "app/auth.py"


def test_validate_findings_batch() -> None:
    diff = _build_sample_diff()
    f1 = RawAgentFinding(
        category="security",
        severity="high",
        file="app/auth.py",
        line_start=11,
        line_end=12,
        title="Valid finding",
        explanation="Explanation of issue.",
        evidence="if not password:",
        confidence=0.9,
    )
    f2 = RawAgentFinding(
        category="maintainability",
        severity="low",
        file="missing.py",  # Hallucinated file
        line_start=1,
        line_end=2,
        title="Missing file finding",
        explanation="Explanation of issue.",
        evidence="some code",
        confidence=0.5,
    )

    batch_result = validate_findings([f1, f2], diff)
    assert batch_result.total_evaluated == 2
    assert len(batch_result.accepted) == 1
    assert len(batch_result.dropped) == 1
    assert batch_result.accepted[0].title == "Valid finding"
    assert "file_not_in_diff" in (batch_result.dropped[0].drop_reason or "")


def test_to_finding_create_models() -> None:
    diff = _build_sample_diff()
    f1 = RawAgentFinding(
        category="security",
        severity="high",
        file="app/auth.py",
        line_start=11,
        line_end=12,
        title="Valid finding",
        explanation="Explanation of issue.",
        evidence="if not password:",
        confidence=0.9,
    )
    f2 = RawAgentFinding(
        category="maintainability",
        severity="low",
        file="missing.py",
        line_start=1,
        line_end=2,
        title="Hallucinated finding",
        explanation="Explanation of issue.",
        evidence="some code",
        confidence=0.5,
    )

    batch_result = validate_findings([f1, f2], diff)
    models = to_finding_create_models(
        batch_result,
        review_id=1,
        agent="single_agent",
        include_dropped=True,
    )

    assert len(models) == 2
    # First model is active
    assert models[0].status == "active"
    assert models[0].drop_reason is None
    assert models[0].agent == "single_agent"
    assert models[0].review_id == 1

    # Second model is dropped
    assert models[1].status == "dropped"
    assert models[1].drop_reason is not None
    assert "file_not_in_diff" in models[1].drop_reason


def test_to_finding_create_models_exclude_dropped() -> None:
    diff = _build_sample_diff()
    f1 = RawAgentFinding(
        category="security",
        severity="high",
        file="app/auth.py",
        line_start=11,
        line_end=12,
        title="Valid finding",
        explanation="Explanation of issue.",
        evidence="if not password:",
        confidence=0.9,
    )
    f2 = RawAgentFinding(
        category="maintainability",
        severity="low",
        file="missing.py",
        line_start=1,
        line_end=2,
        title="Hallucinated finding",
        explanation="Explanation of issue.",
        evidence="some code",
        confidence=0.5,
    )

    batch_result = validate_findings([f1, f2], diff)
    models = to_finding_create_models(
        batch_result,
        review_id=1,
        agent="single_agent",
        include_dropped=False,
    )
    assert len(models) == 1
    assert models[0].status == "active"
