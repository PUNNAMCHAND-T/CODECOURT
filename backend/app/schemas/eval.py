"""Pydantic schemas for benchmark evaluation endpoints.

PROJECT.md §2 & §5: Data contracts for dashboard evaluation results.
"""

from pydantic import BaseModel, ConfigDict, Field


class AggregateMetricResponse(BaseModel):
    """Mean, standard deviation, min, and max for a benchmark metric."""

    model_config = ConfigDict(extra="ignore")

    mean: float = Field(..., description="Sample mean")
    std: float = Field(..., description="Sample standard deviation")
    min: float = Field(..., description="Minimum recorded value")
    max: float = Field(..., description="Maximum recorded value")
    formatted: str = Field(..., description="Human-readable formatted string (e.g. '85.2 ± 3.1%')")


class ConfigComparisonResponse(BaseModel):
    """Aggregated evaluation metrics for a review configuration across multiple runs."""

    model_config = ConfigDict(extra="ignore")

    config: str = Field(..., description="Review configuration key")
    label: str = Field(..., description="Display title for architecture")
    model: str = Field(..., description="Evaluated LLM model")
    split: str = Field(..., description="Dataset split evaluated ('dev' or 'test')")
    num_runs: int = Field(..., ge=1, description="Number of benchmark repetitions")
    precision: AggregateMetricResponse
    recall: AggregateMetricResponse
    f1: AggregateMetricResponse
    fdr: AggregateMetricResponse
    clean_specificity: AggregateMetricResponse
    buggy_detection_rate: AggregateMetricResponse
    mean_latency_s: AggregateMetricResponse
    cost_per_pr_usd: AggregateMetricResponse
    tokens_per_pr: AggregateMetricResponse


class EvalRunSummaryItem(BaseModel):
    """Summary of an individual evaluation run."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    config: str
    model: str
    split: str
    total_cases: int
    completed_cases: int
    partial_cases: int
    failed_cases: int
    total_findings: int
    total_tokens: int
    total_cost_usd: float
    duration_seconds: float
    created_at: str


class BenchmarkOverviewResponse(BaseModel):
    """Complete benchmark evaluation payload for the dashboard."""

    model_config = ConfigDict(extra="ignore")

    split: str
    total_cases: int
    num_runs_per_config: int
    model: str
    comparisons: list[ConfigComparisonResponse]
    runs: list[EvalRunSummaryItem]
    report_markdown: str


class FailureAnalysisResponse(BaseModel):
    """Aggregated failure taxonomy diagnosis across evaluated runs."""

    model_config = ConfigDict(extra="ignore")

    total_evaluated_cases: int
    total_failures: int
    by_failure_mode: dict[str, int]
    by_category: dict[str, int]
    by_language: dict[str, int]
    report_markdown: str
