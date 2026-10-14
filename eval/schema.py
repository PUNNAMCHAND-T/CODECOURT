"""Schemas for evaluation cases, ground truth annotations, and datasets.

T4.1: Defines strongly-typed models for benchmark pull request cases with
pre-labeled ground truth coordinates, category tags, and fixed dev/test splits.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvalSplit = Literal["dev", "test"]
EvalLanguage = Literal["python", "typescript", "javascript"]
EvalCategory = Literal["security", "performance", "maintainability", "correctness", "clean"]
EvalSeverity = Literal["low", "medium", "high", "critical"]


class GroundTruthFinding(BaseModel):
    """Ground-truth vulnerability or bug annotation for an evaluation case."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(..., description="File path relative to repository root")
    line_start: int = Field(..., ge=1, description="1-indexed starting line number in the diff")
    line_end: int = Field(..., ge=1, description="1-indexed ending line number in the diff")
    category: Literal["security", "performance", "maintainability", "correctness"] = Field(
        ..., description="Taxonomy category of the injected bug"
    )
    severity: EvalSeverity = Field(..., description="Expected severity classification")
    title: str = Field(..., description="Short canonical title for the issue")
    description: str = Field(..., description="Explanation of why this change is defective")
    evidence_snippet: str = Field(
        ..., description="Exact diff line or code fragment demonstrating the issue"
    )


class EvalCase(BaseModel):
    """A single pull request evaluation case with diff and ground-truth metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Globally unique case identifier, e.g. 'dev_01_py_sec_sqli'")
    split: EvalSplit = Field(..., description="Fixed dataset split: 'dev' or 'test'")
    language: EvalLanguage = Field(..., description="Programming language of the pull request")
    category: EvalCategory = Field(
        ..., description="Primary category of the case or 'clean' if no bug is present"
    )
    has_bug: bool = Field(..., description="True if this case contains an injected bug")
    pr_title: str = Field(..., description="Simulated GitHub pull request title")
    pr_description: str = Field(..., description="Simulated GitHub pull request description")
    filename: str = Field(..., description="Main modified file path in the diff")
    diff_text: str = Field(..., description="Valid unified git diff format text")
    ground_truth: GroundTruthFinding | None = Field(
        default=None,
        description="Pre-labeled ground truth finding for buggy cases; None for clean cases",
    )


class EvalDataset(BaseModel):
    """Collection of evaluation cases with split and category filtering utilities."""

    model_config = ConfigDict(extra="forbid")

    cases: list[EvalCase] = Field(default_factory=list)

    @property
    def dev_cases(self) -> list[EvalCase]:
        """Return cases assigned to the dev split."""
        return [c for c in self.cases if c.split == "dev"]

    @property
    def test_cases(self) -> list[EvalCase]:
        """Return cases assigned to the test split."""
        return [c for c in self.cases if c.split == "test"]

    @property
    def buggy_cases(self) -> list[EvalCase]:
        """Return cases containing injected bugs."""
        return [c for c in self.cases if c.has_bug]

    @property
    def clean_cases(self) -> list[EvalCase]:
        """Return cases with no injected bugs."""
        return [c for c in self.cases if not c.has_bug]

    def get_case(self, case_id: str) -> EvalCase | None:
        """Find an evaluation case by unique identifier."""
        for case in self.cases:
            if case.id == case_id:
                return case
        return None


class EvalCaseFinding(BaseModel):
    """Standardized finding representation produced during an evaluation run."""

    model_config = ConfigDict(extra="ignore")

    category: str = Field(..., description="Reported finding category")
    severity: str = Field(..., description="Reported finding severity")
    file: str = Field(..., description="Target file path")
    line_start: int = Field(..., ge=1, description="1-indexed starting line")
    line_end: int = Field(..., ge=1, description="1-indexed ending line")
    title: str = Field(..., description="Finding title")
    explanation: str = Field(default="", description="Finding explanation")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")


class EvalCaseResult(BaseModel):
    """Result of running a single evaluation case through a review configuration."""

    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Identifier of the evaluated case")
    split: EvalSplit = Field(..., description="Dataset split of the case ('dev' or 'test')")
    language: EvalLanguage = Field(..., description="Programming language")
    category: EvalCategory = Field(..., description="Original case category")
    has_bug: bool = Field(..., description="Whether the case has an injected bug")
    config: str = Field(..., description="Review pipeline configuration used")
    model: str = Field(..., description="LLM model identifier used")
    status: str = Field(..., description="Pipeline outcome: 'completed', 'partial', or 'failed'")
    error: str | None = Field(default=None, description="Error message if pipeline failed")
    latency_ms: int = Field(default=0, ge=0, description="Total pipeline latency in milliseconds")
    tokens_prompt: int = Field(default=0, ge=0, description="Prompt tokens consumed")
    tokens_completion: int = Field(default=0, ge=0, description="Completion tokens produced")
    tokens_total: int = Field(default=0, ge=0, description="Total tokens consumed")
    cost_usd: float = Field(default=0.0, ge=0.0, description="Total cost in USD")
    findings: list[EvalCaseFinding] = Field(default_factory=list, description="Validated findings")
    summary: str = Field(default="", description="Review summary text")
    trace_node_count: int = Field(default=0, ge=0, description="Number of executed graph nodes")


class EvalRunSummary(BaseModel):
    """Aggregated summary metrics for a complete evaluation run."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Unique evaluation run identifier")
    config: str = Field(..., description="Review configuration tested")
    model: str = Field(..., description="Model identifier used")
    split: str = Field(..., description="Dataset split ('dev', 'test', or 'all')")
    total_cases: int = Field(..., ge=0)
    completed_cases: int = Field(..., ge=0)
    partial_cases: int = Field(..., ge=0)
    failed_cases: int = Field(..., ge=0)
    total_findings: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    total_cost_usd: float = Field(..., ge=0.0)
    duration_seconds: float = Field(..., ge=0.0)
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class EvalRunResult(BaseModel):
    """Complete container for an evaluation run containing summary and case results."""

    model_config = ConfigDict(extra="ignore")

    summary: EvalRunSummary
    case_results: list[EvalCaseResult] = Field(default_factory=list)


class MatchingConfig(BaseModel):
    """Configuration options for deterministic ground-truth candidate matching."""

    model_config = ConfigDict(extra="forbid")

    iou_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum line intersection-over-union required (0.0 = any line overlap)",
    )
    line_tolerance: int = Field(
        default=0,
        ge=0,
        description="Allowable line offset distance when checking interval overlap",
    )
    strict_category: bool = Field(
        default=True,
        description="Whether candidate finding category must strictly match ground truth",
    )


class MetricScores(BaseModel):
    """Core evaluation metrics: precision, recall, F1, false discovery rate."""

    model_config = ConfigDict(extra="ignore")

    tp: int = Field(default=0, ge=0, description="True positive finding matches")
    fp: int = Field(default=0, ge=0, description="False positive / ungrounded findings")
    fn: int = Field(default=0, ge=0, description="False negative / missed ground truth bugs")
    precision: float = Field(default=0.0, ge=0.0, le=1.0, description="TP / (TP + FP)")
    recall: float = Field(default=0.0, ge=0.0, le=1.0, description="TP / (TP + FN)")
    f1: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Harmonic mean of precision & recall"
    )
    fdr: float = Field(
        default=0.0, ge=0.0, le=1.0, description="False discovery rate: FP / (TP + FP)"
    )


class CaseMatchDetail(BaseModel):
    """Detailed matching record for an individual benchmark case."""

    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Unique case identifier")
    split: str = Field(..., description="Dataset split ('dev' or 'test')")
    has_bug: bool = Field(..., description="Whether this case contains an injected bug")
    category: str = Field(..., description="Primary case category")
    status: str = Field(..., description="Pipeline execution outcome status")
    tp: int = Field(default=0, ge=0)
    fp: int = Field(default=0, ge=0)
    fn: int = Field(default=0, ge=0)
    matched_ground_truth: bool = Field(default=False)
    candidate_findings_count: int = Field(default=0, ge=0)


class LatencyMetrics(BaseModel):
    """Latency percentile metrics across evaluated benchmark cases."""

    model_config = ConfigDict(extra="ignore")

    mean_ms: float = Field(default=0.0, ge=0.0)
    median_ms: float = Field(default=0.0, ge=0.0)
    p95_ms: float = Field(default=0.0, ge=0.0)
    min_ms: int = Field(default=0, ge=0)
    max_ms: int = Field(default=0, ge=0)


class CostMetrics(BaseModel):
    """Token and cost consumption metrics for an evaluation run."""

    model_config = ConfigDict(extra="ignore")

    total_cost_usd: float = Field(default=0.0, ge=0.0)
    mean_cost_usd: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    mean_tokens: float = Field(default=0.0, ge=0.0)
    tokens_prompt: int = Field(default=0, ge=0)
    tokens_completion: int = Field(default=0, ge=0)


class EvalRunMetrics(BaseModel):
    """Comprehensive evaluation metrics computed from an EvalRunResult."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(..., description="Run identifier")
    config: str = Field(..., description="Review pipeline configuration")
    model: str = Field(..., description="LLM model identifier")
    split: str = Field(..., description="Evaluated split ('dev', 'test', or 'all')")
    total_cases: int = Field(default=0, ge=0)
    completed_cases: int = Field(default=0, ge=0)
    partial_cases: int = Field(default=0, ge=0)
    failed_cases: int = Field(default=0, ge=0)
    clean_cases_total: int = Field(default=0, ge=0)
    clean_cases_passed: int = Field(default=0, ge=0)
    clean_specificity: float = Field(default=1.0, ge=0.0, le=1.0)
    buggy_cases_total: int = Field(default=0, ge=0)
    buggy_cases_detected: int = Field(default=0, ge=0)
    buggy_detection_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    overall: MetricScores = Field(default_factory=MetricScores)
    by_category: dict[str, MetricScores] = Field(default_factory=dict)
    latency: LatencyMetrics = Field(default_factory=LatencyMetrics)
    cost: CostMetrics = Field(default_factory=CostMetrics)
    matching_config: MatchingConfig = Field(default_factory=MatchingConfig)
    case_details: list[CaseMatchDetail] = Field(default_factory=list)
