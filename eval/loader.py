"""Dataset loader and integrity validator for CodeCourt evaluation benchmarks.

T4.1: Loads pre-labeled evaluation cases, provides split filtering, and
validates ground-truth coordinate alignment against parsed unified diffs.
"""

import json
from pathlib import Path

from backend.app.services.diff_parser import parse_unified_diff
from eval.dataset_builder import DEV_CASES
from eval.schema import EvalCase, EvalDataset
from eval.test_cases_data import TEST_CASES

DEFAULT_DATA_DIR = Path(__file__).parent / "data"


def get_all_cases() -> list[EvalCase]:
    """Return all 50 predefined evaluation cases (20 dev + 30 test)."""
    return list(DEV_CASES) + list(TEST_CASES)


def load_eval_dataset() -> EvalDataset:
    """Instantiate and return the full 50-case EvalDataset."""
    return EvalDataset(cases=get_all_cases())


def export_datasets_to_json(data_dir: Path | None = None) -> tuple[Path, Path]:
    """Serialize dev and test split cases into JSON files.

    Writes:
    - {data_dir}/dev_cases.json (20 cases)
    - {data_dir}/test_cases.json (30 cases)
    """
    target_dir = data_dir or DEFAULT_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    dev_path = target_dir / "dev_cases.json"
    test_path = target_dir / "test_cases.json"

    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in DEV_CASES], f, indent=2)

    with open(test_path, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in TEST_CASES], f, indent=2)

    return dev_path, test_path


def load_from_json(data_dir: Path | None = None) -> EvalDataset:
    """Load evaluation cases from serialized JSON files."""
    target_dir = data_dir or DEFAULT_DATA_DIR
    dev_path = target_dir / "dev_cases.json"
    test_path = target_dir / "test_cases.json"

    cases: list[EvalCase] = []
    if dev_path.exists():
        with open(dev_path, encoding="utf-8") as f:
            raw_dev = json.load(f)
            cases.extend([EvalCase.model_validate(c) for c in raw_dev])

    if test_path.exists():
        with open(test_path, encoding="utf-8") as f:
            raw_test = json.load(f)
            cases.extend([EvalCase.model_validate(c) for c in raw_test])

    return EvalDataset(cases=cases)


def validate_dataset_integrity(dataset: EvalDataset) -> list[str]:
    """Perform rigorous deterministic validation on evaluation dataset.

    Checks:
    1. Overall count and split balance (50 total: 20 dev, 30 test).
    2. Bug and clean counts (35 buggy, 15 clean).
    3. Globally unique identifiers.
    4. Valid unified diff parsing via backend parse_unified_diff.
    5. Ground truth coordinate intersection with modified diff lines.
    6. Non-empty evidence snippet matching diff text.
    7. Clean case constraints (has_bug=False, ground_truth=None).

    Returns:
        List of validation error strings (empty list indicates full integrity).
    """
    errors: list[str] = []

    # 1. Total and split counts
    if len(dataset.cases) != 50:
        errors.append(f"Expected 50 total cases, got {len(dataset.cases)}")
    if len(dataset.dev_cases) != 20:
        errors.append(f"Expected 20 dev cases, got {len(dataset.dev_cases)}")
    if len(dataset.test_cases) != 30:
        errors.append(f"Expected 30 test cases, got {len(dataset.test_cases)}")

    # 2. Bug vs clean balance
    if len(dataset.buggy_cases) != 35:
        errors.append(f"Expected 35 buggy cases, got {len(dataset.buggy_cases)}")
    if len(dataset.clean_cases) != 15:
        errors.append(f"Expected 15 clean cases, got {len(dataset.clean_cases)}")

    # 3. Unique IDs
    ids = [c.id for c in dataset.cases]
    if len(ids) != len(set(ids)):
        duplicates = [x for x in ids if ids.count(x) > 1]
        errors.append(f"Duplicate case IDs found: {set(duplicates)}")

    # 4. Diff and ground-truth validation per case
    for case in dataset.cases:
        if not case.diff_text or not case.diff_text.strip():
            errors.append(f"Case {case.id}: diff_text is empty")
            continue

        try:
            parsed = parse_unified_diff(case.diff_text)
        except Exception as exc:
            errors.append(f"Case {case.id}: failed to parse unified diff: {exc}")
            continue

        if not parsed.files:
            errors.append(f"Case {case.id}: diff parsed into 0 files")
            continue

        file_diff = parsed.files[0]
        modified_lines = file_diff.modified_line_numbers

        if case.has_bug:
            gt = case.ground_truth
            if gt is None:
                errors.append(f"Case {case.id}: has_bug=True but ground_truth is None")
                continue

            if gt.file != case.filename:
                errors.append(
                    f"Case {case.id}: ground_truth file '{gt.file}' != case filename '{case.filename}'"
                )

            if gt.line_start > gt.line_end:
                errors.append(
                    f"Case {case.id}: line_start ({gt.line_start}) > line_end ({gt.line_end})"
                )

            # At least one line in [line_start, line_end] MUST be a modified line in the diff
            gt_range = set(range(gt.line_start, gt.line_end + 1))
            intersection = gt_range.intersection(modified_lines)
            if not intersection:
                errors.append(
                    f"Case {case.id}: ground-truth range [{gt.line_start}, {gt.line_end}] "
                    f"does not intersect modified diff lines {sorted(modified_lines)}"
                )

            if not gt.evidence_snippet.strip():
                errors.append(f"Case {case.id}: evidence_snippet is empty")

        else:
            # Clean case checks
            if case.ground_truth is not None:
                errors.append(f"Case {case.id}: clean case has non-None ground_truth")
            if case.category != "clean":
                errors.append(
                    f"Case {case.id}: clean case category is '{case.category}', expected 'clean'"
                )

    return errors
