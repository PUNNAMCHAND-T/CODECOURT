"""Untrusted content delimiters and sanitization utilities.

Protects LLM reviewer prompts against prompt injection attacks by wrapping
untrusted PR diffs, commit messages, and metadata in explicit boundary tags
and neutralizing delimiter escape attempts.
"""

import re

# Boundary tags (PROJECT.md §6: wrap untrusted content in delimiters)
DELIMITER_START_DIFF = "<<<UNTRUSTED_DIFF>>>"
DELIMITER_END_DIFF = "<<</UNTRUSTED_DIFF>>>"

DELIMITER_START_METADATA = "<<<UNTRUSTED_PR_METADATA>>>"
DELIMITER_END_METADATA = "<<</UNTRUSTED_PR_METADATA>>>"

DELIMITER_START_FILE = "<<<UNTRUSTED_FILE_CONTENT>>>"
DELIMITER_END_FILE = "<<</UNTRUSTED_FILE_CONTENT>>>"


def sanitize_untrusted_text(text: str) -> str:
    """Sanitize untrusted text to prevent escaping delimiter boundary tags.

    Neutralizes any closing or opening tags embedded maliciously inside
    PR diffs, titles, commit messages, or comments, case-insensitively.
    """
    if not text:
        return ""

    # Neutralize closing and opening delimiter injection attempts (case-insensitive)
    sanitized = re.sub(r"<<</untrusted_", r"<\\<\\</UNTRUSTED_", text, flags=re.IGNORECASE)
    sanitized = re.sub(r"<<<untrusted_", r"<\\<\\<UNTRUSTED_", sanitized, flags=re.IGNORECASE)
    return sanitized


def wrap_untrusted_diff(diff_text: str) -> str:
    """Wrap a unified git diff inside untrusted diff delimiters."""
    clean_diff = sanitize_untrusted_text(diff_text.strip())
    return f"{DELIMITER_START_DIFF}\n{clean_diff}\n{DELIMITER_END_DIFF}"


def wrap_untrusted_metadata(
    title: str,
    body: str | None,
    author: str,
    head_ref: str,
    base_ref: str,
) -> str:
    """Wrap pull request metadata inside untrusted metadata delimiters."""
    safe_title = sanitize_untrusted_text(title.strip())
    safe_body = sanitize_untrusted_text((body or "").strip())
    safe_author = sanitize_untrusted_text(author.strip())
    safe_head = sanitize_untrusted_text(head_ref.strip())
    safe_base = sanitize_untrusted_text(base_ref.strip())

    lines = [
        DELIMITER_START_METADATA,
        f"Title: {safe_title}",
        f"Author: {safe_author}",
        f"Branch: {safe_head} -> {safe_base}",
        f"Description:\n{safe_body if safe_body else '(No description provided)'}",
        DELIMITER_END_METADATA,
    ]
    return "\n".join(lines)
