"""Presentation rules for Quad Reconstruction result severity in the N-panel.

Pure functions: they read fields already stored on ``LCW_PG_QuadAnalysisResult``
and ``LCW_PG_QuadReconstructionState`` and return a status kind understood by
``icons.status_icon()`` plus text. They never change a result or rescore it.
"""
from __future__ import annotations

from typing import NamedTuple


class ResultStatus(NamedTuple):
    kind: str  # ok / warning / error / info / idle
    text: str  # full text for the details box
    short: str  # one word or two for the UIList row


def review_reasons(item) -> list[str]:
    """Existing metrics that keep a validated output in review (never green)."""
    reasons = []
    if not item.solver_exact:
        reasons.append("fallback solver")
    if item.relaxation_count > 0:
        reasons.append(f"{item.relaxation_count} relaxation(s)")
    if item.unresolved_triangle_count > 0:
        reasons.append(f"{item.unresolved_triangle_count} unresolved")
    if item.warning_count > 0:
        reasons.append(f"{item.warning_count} warning(s)")
    if item.confidence_label != "HIGH":
        reasons.append(f"{item.confidence_label or 'unknown'} confidence")
    return reasons


def result_status(item, output_available: bool) -> ResultStatus:
    """Status of one per-object result; rules are evaluated in this order."""
    status = item.status
    if status == "FAILED":
        text = f"FAILED: {item.details}" if item.details else "FAILED"
        return ResultStatus("error", text, "Failed")
    if status in {"ANALYZED", "RECONSTRUCTED"} and not item.fingerprint_unchanged:
        return ResultStatus("error", "Source integrity check failed", "Source changed")
    if status == "ANALYZED":
        if item.warning_count > 0:
            return ResultStatus(
                "warning", f"ANALYZED: {item.warning_count} warning(s)", "Warnings"
            )
        classification = item.classification.replace("_", " ").title()
        text = f"ANALYZED: {classification}" if classification else "ANALYZED"
        return ResultStatus("info", text, "Analyzed")
    if status == "RECONSTRUCTED":
        if not item.validation_passed:
            return ResultStatus("error", "Validation failed", "Invalid")
        if not output_available:
            return ResultStatus(
                "warning", "Output unavailable: last result retained", "No output"
            )
        reasons = review_reasons(item)
        if reasons:
            return ResultStatus("warning", f"Validated, review: {', '.join(reasons)}", "Review")
        return ResultStatus("ok", "Validated", "Validated")
    return ResultStatus("idle", "Result unavailable", "Unknown")


# job_status -> (status kind, text). A finished batch stays "info", never "ok":
# RECONSTRUCTED is also set when only some objects succeeded.
_BATCH_STATUS = {
    "IDLE": ("idle", "Idle"),
    "ANALYZING": ("running", "Analyzing"),
    "RECONSTRUCTING": ("running", "Reconstructing"),
    "ANALYZED": ("info", "Analysis finished"),
    "RECONSTRUCTED": ("info", "Run finished"),
    "FAILED": ("error", "Run failed"),
    "CANCELLED": ("cancelled", "Run cancelled"),
}


def batch_status(job_status: str) -> tuple[str, str]:
    """Status kind and text for the batch ``Status:`` line."""
    if job_status in _BATCH_STATUS:
        return _BATCH_STATUS[job_status]
    return "idle", job_status.replace("_", " ").title() or "Idle"
