"""
Content hashing and diff generation utilities.
"""

import difflib
import hashlib
import logging

logger = logging.getLogger(__name__)


def compute_hash(content: str) -> str:
    """
    Return the SHA-256 hex digest of the content string.

    Args:
        content: The text to hash.

    Returns:
        64-character lowercase hex string.
    """
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


def generate_diff(old: str, new: str) -> str:
    """
    Generate a unified diff between old and new content.

    Args:
        old: Previous version of the content.
        new: New version of the content.

    Returns:
        Unified diff string.  Empty string if no difference.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="previous",
            tofile="current",
            lineterm="",
        )
    )
    return "\n".join(diff_lines)


def is_meaningful_diff(diff: str, min_lines: int = 3) -> bool:
    """
    Return True if the diff has at least min_lines changed lines.

    Only actual +/- content lines count (not the diff header or @@ lines).

    Args:
        diff: Unified diff string.
        min_lines: Minimum number of changed lines to be considered meaningful.

    Returns:
        True if the diff meets the threshold.
    """
    if not diff:
        return False
    changed = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++") or line.startswith("-") and not line.startswith("---"):
            changed += 1
        if changed >= min_lines:
            return True
    return False


def get_diff_stats(diff: str) -> dict:
    """
    Count added, removed, and total changed lines in a unified diff.

    Args:
        diff: Unified diff string.

    Returns:
        Dictionary with keys: added, removed, total_changed.
    """
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {
        "added": added,
        "removed": removed,
        "total_changed": added + removed,
    }
