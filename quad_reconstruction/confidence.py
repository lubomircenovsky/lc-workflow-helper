from __future__ import annotations

import math

from .models import CandidatePair, ConfidenceResult, MatchingResult, ValidationResult


def _percentile_95(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def calculate_confidence(
    matching: MatchingResult,
    candidates: tuple[CandidatePair, ...],
    validation: ValidationResult,
) -> ConfidenceResult:
    selected = tuple(candidates[index] for index in matching.selected_candidate_indices)
    triangle_total = matching.cardinality * 2 + len(matching.unmatched_face_indices)
    coverage = matching.cardinality * 2 / triangle_total if triangle_total else 1.0
    mean_cost = (
        sum(candidate.cost for candidate in selected) / len(selected)
        if selected
        else 0.0
    )
    warps = tuple(candidate.metrics.warp_error for candidate in selected)
    p95_warp = _percentile_95(warps)
    max_warp = max(warps, default=0.0)
    relaxation_count = sum(len(candidate.relaxation_flags) for candidate in selected)

    if not validation.valid:
        return ConfidenceResult(
            score=0.0,
            label="FAILED",
            coverage=coverage,
            mean_cost=mean_cost,
            p95_warp=p95_warp,
            max_warp=max_warp,
            relaxation_count=relaxation_count,
            solver_exact=matching.exact,
            hypothesis_margin=matching.hypothesis_margin,
            warnings=("Hard validation failed.",),
        )

    cost_quality = max(0.0, 1.0 - mean_cost / 10.0)
    p95_warp_quality = max(0.0, 1.0 - p95_warp / 0.05)
    max_warp_quality = max(0.0, 1.0 - max_warp / 0.05)
    relaxation_quality = max(
        0.0,
        1.0 - relaxation_count / max(len(selected), 1),
    )
    surface_quality = 1.0
    if validation.surface_deviation is not None:
        surface_quality = max(
            0.0,
            1.0 - validation.surface_deviation.p95 / 0.01,
        )
    subdivision_quality = (
        1.0
        if validation.subdivision is None or validation.subdivision.passed
        else 0.0
    )
    score = (
        45.0 * coverage
        + 15.0 * cost_quality
        + 6.0 * p95_warp_quality
        + 4.0 * max_warp_quality
        + 10.0 * relaxation_quality
        + (10.0 if matching.exact else 3.0)
        + 5.0 * matching.hypothesis_margin
        + 3.0 * surface_quality * coverage
        + 2.0 * subdivision_quality * coverage
    )
    score = max(0.0, min(100.0, score))
    label = "HIGH" if score >= 80.0 else "MEDIUM" if score >= 55.0 else "LOW"
    warnings = list(matching.warnings)
    if not matching.exact:
        warnings.append("Confidence reduced because the selected solver is not exact.")
    if relaxation_count:
        warnings.append(f"{relaxation_count} attribute relaxation(s) were used.")
    return ConfidenceResult(
        score=score,
        label=label,
        coverage=coverage,
        mean_cost=mean_cost,
        p95_warp=p95_warp,
        max_warp=max_warp,
        relaxation_count=relaxation_count,
        solver_exact=matching.exact,
        hypothesis_margin=matching.hypothesis_margin,
        warnings=tuple(dict.fromkeys(warnings)),
    )
