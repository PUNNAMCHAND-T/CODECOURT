"""Pydantic schemas package."""

from backend.app.schemas.auth import (
    LoginRequest,
    TokenPayload,
    TokenResponse,
    UserSummary,
)
from backend.app.schemas.diff import DiffHunk, DiffLine, FileDiff, ParsedDiff
from backend.app.schemas.eval import (
    AggregateMetricResponse,
    BenchmarkOverviewResponse,
    ConfigComparisonResponse,
    EvalRunSummaryItem,
    FailureAnalysisResponse,
)
from backend.app.schemas.finding import (
    AgentReviewOutput,
    FindingCategory,
    FindingCreate,
    FindingResponse,
    FindingSeverity,
    FindingStatus,
    FindingValidationResult,
    RawAgentFinding,
    ValidatedFinding,
)
from backend.app.schemas.github import (
    GitHubPublishedReview,
    GitHubReviewComment,
    GitHubReviewPublishPayload,
    PullRequestMetadata,
    RepoFileContent,
)
from backend.app.schemas.review import (
    ReviewDetailResponse,
    ReviewListResponse,
    ReviewResponse,
    ReviewSummaryCounts,
    ReviewTriggerRequest,
)
from backend.app.schemas.tools import (
    CommitSummary,
    GetFileHistoryParams,
    GetPRMetadataParams,
    ReadFileParams,
    SearchRepoParams,
    ToolCall,
    ToolResult,
)
from backend.app.schemas.webhook import (
    PingWebhookPayload,
    PullRequestWebhookPayload,
    RepositorySummary,
)

__all__ = [
    "AgentReviewOutput",
    "AggregateMetricResponse",
    "BenchmarkOverviewResponse",
    "CommitSummary",
    "ConfigComparisonResponse",
    "DiffHunk",
    "DiffLine",
    "EvalRunSummaryItem",
    "FailureAnalysisResponse",
    "FileDiff",
    "FindingCategory",
    "FindingCreate",
    "FindingResponse",
    "FindingSeverity",
    "FindingStatus",
    "FindingValidationResult",
    "GetFileHistoryParams",
    "GetPRMetadataParams",
    "GitHubPublishedReview",
    "GitHubReviewComment",
    "GitHubReviewPublishPayload",
    "LoginRequest",
    "ParsedDiff",
    "PingWebhookPayload",
    "PullRequestMetadata",
    "PullRequestWebhookPayload",
    "RawAgentFinding",
    "ReadFileParams",
    "RepoFileContent",
    "RepositorySummary",
    "ReviewDetailResponse",
    "ReviewListResponse",
    "ReviewResponse",
    "ReviewSummaryCounts",
    "ReviewTriggerRequest",
    "SearchRepoParams",
    "TokenPayload",
    "TokenResponse",
    "ToolCall",
    "ToolResult",
    "UserSummary",
    "ValidatedFinding",
]
