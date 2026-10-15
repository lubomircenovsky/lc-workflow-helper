"""Presentation rules for CAD result severity in the N-panel.

Pure functions: they map fields already stored on ``LCW_PG_CADResult`` and
``LCW_PG_CADAnalysisLine`` to a status kind understood by
``icons.status_icon()`` and a short text. They never compute or change a result.
"""
from __future__ import annotations

# status kind, display text; REVIEW is resolved separately because of ``partial``.
_RESULT_STATUS = {
    "PENDING": ("idle", "PENDING"),
    "RUNNING": ("running", "RUNNING"),
    "PASS": ("ok", "PASS"),
    "FAIL": ("error", "FAIL"),
}


def result_status(status: str, partial: bool) -> tuple[str, str]:
    """Status kind and header text for one CAD result row."""
    if status == "REVIEW":
        return "warning", "PARTIAL / REVIEW" if partial else "REVIEW"
    if status in _RESULT_STATUS:
        return _RESULT_STATUS[status]
    return "idle", f"Unknown status: {status}" if status else "Unknown status"


def analysis_line_status(severity: str) -> str:
    """Status kind for one Last Analysis line: a blocker is an error, the rest is a note."""
    return "error" if severity == "BLOCKER" else "info"


def analysis_line_text(severity: str, message: str) -> str:
    """Message text that states a blocker in words, not only by icon."""
    return f"BLOCKER: {message}" if severity == "BLOCKER" else message


def analysis_summary_status(blockers: int) -> str:
    """Status kind for the Last Analysis summary line."""
    return "error" if blockers else "ok"
