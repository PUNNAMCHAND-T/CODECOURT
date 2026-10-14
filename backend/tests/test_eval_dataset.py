"""Unit tests for T4.1: Evaluation dataset, ground-truth annotations, and dev/test splits.

Verifies:
1. Dataset cardinality: exactly 50 cases (20 dev, 30 test; 35 buggy, 15 clean).
2. Category coverage across security, performance, maintainability, correctness, and clean.
3. Language coverage: Python and TypeScript.
4. Diff validity and ground-truth coordinate intersection with modified diff lines.
5. JSON round-trip serialization and loading.
"""

from pathlib import Path

from eval.loader import (
    get_all_cases,
    load_eval_dataset,
    load_from_json,
    validate_dataset_integrity,
)

from backend.app.services.diff_parser import parse_unified_diff


def test_dataset_cardinality_and_splits() -> None:
    """Verify exact 50 total cases: 20 dev (14 bugs, 6 clean) and 30 test (21 bugs, 9 clean)."""
    dataset = load_eval_dataset()

    assert len(dataset.cases) == 50
    assert len(dataset.dev_cases) == 20
    assert len(dataset.test_cases) == 30
    assert len(dataset.buggy_cases) == 35
    assert len(dataset.clean_cases) == 15

    dev_bugs = [c for c in dataset.dev_cases if c.has_bug]
    dev_clean = [c for c in dataset.dev_cases if not c.has_bug]
    assert len(dev_bugs) == 14
    assert len(dev_clean) == 6

    test_bugs = [c for c in dataset.test_cases if c.has_bug]
    test_clean = [c for c in dataset.test_cases if not c.has_bug]
    assert len(test_bugs) == 21
    assert len(test_clean) == 9


def test_dataset_integrity_validator_reports_zero_errors() -> None:
    """Rigorous programmatic integrity check must report zero defects."""
    dataset = load_eval_dataset()
    errors = validate_dataset_integrity(dataset)
    assert errors == []


def test_unique_case_ids() -> None:
    """Every evaluation case must possess a globally unique identifier."""
    cases = get_all_cases()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))
    for cid in ids:
        assert cid.startswith("dev_") or cid.startswith("test_")


def test_language_and_category_coverage() -> None:
    """Ensure balanced language and category coverage across both splits."""
    dataset = load_eval_dataset()

    # Both Python and TypeScript/JavaScript must be represented
    languages = {c.language for c in dataset.cases}
    assert "python" in languages
    assert "typescript" in languages

    # All taxonomy categories must be represented in buggy cases
    bug_categories = {c.category for c in dataset.buggy_cases}
    assert bug_categories == {"security", "performance", "maintainability", "correctness"}

    # Both dev and test splits have all categories
    dev_categories = {c.category for c in dataset.dev_cases}
    assert dev_categories == {"security", "performance", "maintainability", "correctness", "clean"}

    test_categories = {c.category for c in dataset.test_cases}
    assert test_categories == {"security", "performance", "maintainability", "correctness", "clean"}


def test_diff_parsing_and_ground_truth_intersection() -> None:
    """Every buggy case's ground-truth coordinates must intersect real modified diff lines."""
    dataset = load_eval_dataset()

    for case in dataset.buggy_cases:
        assert case.ground_truth is not None, f"Case {case.id} missing ground truth"
        gt = case.ground_truth

        parsed = parse_unified_diff(case.diff_text)
        assert len(parsed.files) == 1, f"Case {case.id} should have exactly 1 file diff"

        f_diff = parsed.files[0]
        assert f_diff.new_path == gt.file, (
            f"Case {case.id}: diff path '{f_diff.new_path}' != gt file '{gt.file}'"
        )

        gt_lines = set(range(gt.line_start, gt.line_end + 1))
        overlap = gt_lines.intersection(f_diff.modified_line_numbers)
        assert overlap, (
            f"Case {case.id}: GT range [{gt.line_start}, {gt.line_end}] does not "
            f"overlap diff modified lines {sorted(f_diff.modified_line_numbers)}"
        )


def test_clean_cases_invariants() -> None:
    """All 15 clean cases must have has_bug=False, ground_truth=None, and category='clean'."""
    dataset = load_eval_dataset()
    assert len(dataset.clean_cases) == 15

    for case in dataset.clean_cases:
        assert case.has_bug is False
        assert case.ground_truth is None
        assert case.category == "clean"

        # Even clean cases have valid unified diffs representing normal PR changes
        parsed = parse_unified_diff(case.diff_text)
        assert len(parsed.files) == 1
        assert len(parsed.files[0].modified_line_numbers) > 0


def test_dataset_json_roundtrip(tmp_path: Path) -> None:
    """Verify serialized JSON files reload identically without data loss."""
    from eval.loader import export_datasets_to_json

    dev_json, test_json = export_datasets_to_json(tmp_path)
    assert dev_json.exists()
    assert test_json.exists()

    reloaded = load_from_json(tmp_path)
    assert len(reloaded.cases) == 50
    assert len(reloaded.dev_cases) == 20
    assert len(reloaded.test_cases) == 30
    assert len(reloaded.buggy_cases) == 35
    assert len(reloaded.clean_cases) == 15

    # Check case retrieval utility
    found = reloaded.get_case("dev_01_py_sec_sqli")
    assert found is not None
    assert found.category == "security"
    assert found.has_bug is True

    not_found = reloaded.get_case("non_existent_id")
    assert not_found is None
