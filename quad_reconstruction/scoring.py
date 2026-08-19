from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .models import CandidateMetrics


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    planarity: float = 3.00
    corner: float = 1.40
    aspect: float = 0.12
    opposite_edge: float = 0.10
    diagonal_balance: float = 0.04
    flow: float = 0.20
    curvature: float = 0.35
    valence: float = 0.20
    uv: float = 8.00
    seam_or_sharp: float = 8.00
    material: float = 12.00
    attribute: float = 6.00


def scoring_weights_from_state(state) -> ScoringWeights:
    return ScoringWeights(
        planarity=state.weight_planarity,
        corner=state.weight_corner,
        aspect=state.weight_aspect,
        opposite_edge=state.weight_opposite_edge,
        diagonal_balance=state.weight_diagonal_balance,
        flow=state.weight_flow,
        curvature=state.weight_curvature,
        valence=state.weight_valence,
        uv=state.weight_uv,
        seam_or_sharp=state.weight_seam_or_sharp,
        material=state.weight_material,
        attribute=state.weight_attribute,
    )


NORMALIZED_METRIC_NAMES = (
    "planarity_error",
    "corner_error",
    "log_aspect_error",
    "opposite_edge_error",
    "diagonal_balance_error",
    "flow_alignment_error",
    "curvature_continuity_error",
    "valence_delta",
)


def robust_metric_scales(
    metrics: tuple[CandidateMetrics, ...],
) -> dict[str, float]:
    scales = {}
    for name in NORMALIZED_METRIC_NAMES:
        values = tuple(abs(float(getattr(item, name))) for item in metrics)
        if not values:
            scales[name] = 1.0
            continue
        center = median(values)
        mad = median(abs(value - center) for value in values)
        scale = max(center, 1.4826 * mad)
        scales[name] = scale if scale > 1e-12 else 1.0
    return scales


def normalized_candidate_cost(
    metrics: CandidateMetrics,
    weights: ScoringWeights,
    scales: dict[str, float],
) -> float:
    normalized = CandidateMetrics(
        **{
            field_name: (
                getattr(metrics, field_name) / scales[field_name]
                if field_name in NORMALIZED_METRIC_NAMES
                else getattr(metrics, field_name)
            )
            for field_name in CandidateMetrics.__dataclass_fields__
        }
    )
    return candidate_cost(normalized, weights)


def candidate_cost(metrics: CandidateMetrics, weights: ScoringWeights) -> float:
    return (
        weights.planarity * metrics.planarity_error
        + weights.corner * metrics.corner_error
        + weights.aspect * metrics.log_aspect_error
        + weights.opposite_edge * metrics.opposite_edge_error
        + weights.diagonal_balance * metrics.diagonal_balance_error
        + weights.flow * metrics.flow_alignment_error
        + weights.curvature * metrics.curvature_continuity_error
        + weights.valence * metrics.valence_delta
        + weights.uv * metrics.uv_discontinuity_penalty
        + weights.seam_or_sharp * metrics.sharp_or_seam_penalty
        + weights.material * metrics.material_boundary_penalty
        + weights.attribute * metrics.attribute_violation_count
    )
