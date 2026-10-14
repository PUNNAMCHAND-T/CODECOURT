"""Git unified diff parser.

Parses unified diff output into structured files, hunks, and line number mappings.
Handles added, modified, deleted, renamed, and binary files accurately.
"""

import re

from backend.app.schemas.diff import (
    DiffHunk,
    DiffLine,
    FileDiff,
    FileDiffStatus,
    ParsedDiff,
)

# Regex matching hunk headers: @@ -old_start[,old_count] +new_start[,new_count] @@ [heading]
HUNK_HEADER_REGEX = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(?:[ ]?(.*))?$")

# Regex matching git diff file header
DIFF_GIT_REGEX = re.compile(r"^diff --git a/(.*?) b/(.*?)$")


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    """Parse raw git unified diff text into a structured ParsedDiff object.

    Args:
        diff_text: Raw unified diff output from Git or GitHub API.

    Returns:
        ParsedDiff containing list of FileDiff instances with line mappings.
    """
    if not diff_text or not diff_text.strip():
        return ParsedDiff(files=[])

    files: list[FileDiff] = []
    lines = diff_text.splitlines()
    i = 0
    total_lines = len(lines)

    while i < total_lines:
        line = lines[i]

        # Look for start of a file diff: diff --git a/... b/...
        git_match = DIFF_GIT_REGEX.match(line)
        if git_match:
            old_path: str | None = git_match.group(1)
            new_path: str | None = git_match.group(2)
            status: FileDiffStatus = "modified"
            is_binary: bool = False
            hunks: list[DiffHunk] = []
            i += 1

            # Parse file headers until the first hunk (@@) or next diff --git
            while i < total_lines and not lines[i].startswith("diff --git"):
                curr = lines[i]

                if curr.startswith("new file mode"):
                    status = "added"
                    old_path = None
                elif curr.startswith("deleted file mode"):
                    status = "deleted"
                    new_path = None
                elif curr.startswith("rename from"):
                    status = "renamed"
                    old_path = curr.removeprefix("rename from ").strip()
                elif curr.startswith("rename to"):
                    status = "renamed"
                    new_path = curr.removeprefix("rename to ").strip()
                elif curr.startswith("Binary files") or curr.startswith("GIT binary patch"):
                    is_binary = True
                    status = "binary"
                elif curr.startswith("--- "):
                    raw_old = curr.removeprefix("--- ").strip()
                    if raw_old == "/dev/null":
                        status = "added"
                        old_path = None
                    elif raw_old.startswith("a/"):
                        old_path = raw_old[2:]
                elif curr.startswith("+++ "):
                    raw_new = curr.removeprefix("+++ ").strip()
                    if raw_new == "/dev/null":
                        status = "deleted"
                        new_path = None
                    elif raw_new.startswith("b/"):
                        new_path = raw_new[2:]
                elif curr.startswith("@@"):
                    # Start of hunks reached
                    break

                i += 1

            # If not binary, parse all hunks for this file
            if not is_binary:
                while i < total_lines and not lines[i].startswith("diff --git"):
                    hunk_match = HUNK_HEADER_REGEX.match(lines[i])
                    if not hunk_match:
                        # Extra metadata or unexpected line; advance
                        i += 1
                        continue

                    old_start = int(hunk_match.group(1))
                    old_lines = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
                    new_start = int(hunk_match.group(3))
                    new_lines = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
                    heading = hunk_match.group(5).strip() if hunk_match.group(5) else None

                    diff_lines: list[DiffLine] = []
                    curr_old = old_start
                    curr_new = new_start
                    i += 1

                    # Read hunk lines until next hunk or next diff --git
                    while i < total_lines:
                        hunk_line = lines[i]

                        if hunk_line.startswith("@@") or hunk_line.startswith("diff --git"):
                            break

                        if hunk_line.startswith("+"):
                            diff_lines.append(
                                DiffLine(
                                    line_type="add",
                                    content=hunk_line[1:],
                                    new_lineno=curr_new,
                                )
                            )
                            curr_new += 1
                        elif hunk_line.startswith("-"):
                            diff_lines.append(
                                DiffLine(
                                    line_type="delete",
                                    content=hunk_line[1:],
                                    old_lineno=curr_old,
                                )
                            )
                            curr_old += 1
                        elif hunk_line.startswith(" ") or hunk_line == "":
                            content = hunk_line[1:] if hunk_line.startswith(" ") else hunk_line
                            diff_lines.append(
                                DiffLine(
                                    line_type="context",
                                    content=content,
                                    old_lineno=curr_old,
                                    new_lineno=curr_new,
                                )
                            )
                            curr_old += 1
                            curr_new += 1
                        elif hunk_line.startswith(r"\ No newline at end of file"):
                            # Git marker, do not advance line numbers
                            pass

                        i += 1

                    hunks.append(
                        DiffHunk(
                            old_start=old_start,
                            old_lines=old_lines,
                            new_start=new_start,
                            new_lines=new_lines,
                            heading=heading,
                            lines=diff_lines,
                        )
                    )

            files.append(
                FileDiff(
                    old_path=old_path,
                    new_path=new_path,
                    status=status,
                    is_binary=is_binary,
                    hunks=hunks,
                )
            )
        else:
            i += 1

    return ParsedDiff(files=files)
