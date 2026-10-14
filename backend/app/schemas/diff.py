"""Pydantic schemas for parsed Git diff structures.

Represents files, hunks, and line mappings for diff analysis and finding validation.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DiffLineType = Literal["add", "delete", "context"]
FileDiffStatus = Literal["added", "modified", "deleted", "renamed", "binary"]


class DiffLine(BaseModel):
    """A single line within a diff hunk."""

    model_config = ConfigDict(frozen=True)

    line_type: DiffLineType
    content: str
    old_lineno: int | None = None
    new_lineno: int | None = None


class DiffHunk(BaseModel):
    """A contiguous hunk of changes within a file diff."""

    model_config = ConfigDict(frozen=True)

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    heading: str | None = None
    lines: list[DiffLine] = Field(default_factory=list)


class FileDiff(BaseModel):
    """All changes belonging to a single file in the diff."""

    model_config = ConfigDict(frozen=True)

    old_path: str | None = None
    new_path: str | None = None
    status: FileDiffStatus = "modified"
    is_binary: bool = False
    hunks: list[DiffHunk] = Field(default_factory=list)

    @property
    def file_path(self) -> str:
        """Return the relevant target file path (new_path or old_path)."""
        return self.new_path or self.old_path or "unknown"

    @property
    def added_line_numbers(self) -> set[int]:
        """Set of line numbers in the new file that were newly added."""
        return {
            line.new_lineno
            for hunk in self.hunks
            for line in hunk.lines
            if line.line_type == "add" and line.new_lineno is not None
        }

    @property
    def modified_line_numbers(self) -> set[int]:
        """Set of all line numbers in the new file covered by hunks (added or context)."""
        return {
            line.new_lineno
            for hunk in self.hunks
            for line in hunk.lines
            if line.new_lineno is not None
        }

    @property
    def additions(self) -> int:
        """Count of added lines in this file."""
        return sum(1 for hunk in self.hunks for line in hunk.lines if line.line_type == "add")

    @property
    def deletions(self) -> int:
        """Count of deleted lines in this file."""
        return sum(1 for hunk in self.hunks for line in hunk.lines if line.line_type == "delete")


class ParsedDiff(BaseModel):
    """Container for all parsed file diffs from a PR."""

    model_config = ConfigDict(frozen=True)

    files: list[FileDiff] = Field(default_factory=list)

    @property
    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def file_paths(self) -> list[str]:
        return [f.file_path for f in self.files]

    def get_file(self, path: str) -> FileDiff | None:
        """Find a file diff by its new or old path."""
        for f in self.files:
            if f.new_path == path or f.old_path == path:
                return f
        return None

    def is_line_in_diff(self, file_path: str, line_no: int) -> bool:
        """Check if a specific new line number falls within modified diff hunks.

        Used by the deterministic finding validator to verify finding coordinates.
        """
        f = self.get_file(file_path)
        if not f:
            return False
        return line_no in f.modified_line_numbers
