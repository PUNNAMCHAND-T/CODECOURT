"""Pydantic schemas and data contracts for read-only repository tools."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ToolCall(BaseModel):
    """Represents a tool invocation request from an agent."""

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Represents the structured result of a tool execution."""

    tool_name: str
    success: bool
    output: str
    error: str | None = None
    truncated: bool = False
    execution_seconds: float = 0.0


class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""

    file_path: str = Field(..., description="Repository-relative file path to read")
    start_line: int | None = Field(
        default=None,
        ge=1,
        description="Optional 1-indexed starting line number",
    )
    end_line: int | None = Field(
        default=None,
        ge=1,
        description="Optional 1-indexed ending line number",
    )

    @model_validator(mode="after")
    def validate_line_bounds(self) -> "ReadFileParams":
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class SearchRepoParams(BaseModel):
    """Parameters for search_repo tool."""

    query: str = Field(..., min_length=1, max_length=120, description="Search keyword or symbol")
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of search results to return",
    )


class CommitSummary(BaseModel):
    """Summary of a single git commit touching a file."""

    sha: str
    author: str
    date: str
    message: str


class GetFileHistoryParams(BaseModel):
    """Parameters for get_file_history tool."""

    file_path: str = Field(..., description="Repository-relative file path to inspect")
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of commits to retrieve",
    )


class GetPRMetadataParams(BaseModel):
    """Parameters for get_pr_metadata tool."""

    pull_number: int | None = Field(
        default=None,
        ge=1,
        description="Optional pull request number (defaults to current PR in context)",
    )
