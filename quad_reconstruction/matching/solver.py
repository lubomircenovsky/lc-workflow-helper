from __future__ import annotations

from dataclasses import replace

from ..models import CandidatePair, MatchingResult, TriangleRegion
from .augmenting import solve_seed_augment
from .blossom import solve_exact_blossom


def _hypothesis_margin(
    preferred: MatchingResult,
    comparison: MatchingResult,
) -> float:
    if preferred.cardinality != comparison.cardinality:
        return min(
            1.0,
            abs(preferred.cardinality - comparison.cardinality)
            / max(preferred.cardinality, comparison.cardinality, 1),
        )
    if preferred.selected_candidate_indices == comparison.selected_candidate_indices:
        return 1.0
    return min(
        1.0,
        abs(preferred.total_cost - comparison.total_cost)
        / max(abs(preferred.total_cost), abs(comparison.total_cost), 1.0),
    )


def _combine_results(
    regions: tuple[TriangleRegion, ...],
    candidates: tuple[CandidatePair, ...],
    exact_result: MatchingResult,
    fallback_result: MatchingResult,
) -> MatchingResult:
    selected = tuple(
        sorted(
            set(exact_result.selected_candidate_indices)
            | set(fallback_result.selected_candidate_indices)
        )
    )
    matched_faces = {
        face
        for candidate_index in selected
        for face in candidates[candidate_index].face_indices
    }
    all_faces = tuple(sorted(face for region in regions for face in region.face_indices))
    return MatchingResult(
        backend="AUTO_MIXED",
        selected_candidate_indices=selected,
        unmatched_face_indices=tuple(face for face in all_faces if face not in matched_faces),
        cardinality=len(selected),
        total_cost=sum(candidates[index].cost for index in selected),
        exact=False,
        warnings=tuple(
            dict.fromkeys(
                (
                    *exact_result.warnings,
                    "Oversized regions used deterministic Seed + Augment fallback; "
                    "the combined result is not mathematically exact.",
                    *fallback_result.warnings,
                )
            )
        ),
    )


def solve_matching(
    backend: str,
    regions: tuple[TriangleRegion, ...],
    candidates: tuple[CandidatePair, ...],
    *,
    seed_edge_indices: tuple[int, ...] = (),
    exact_component_limit: int = 2000,
    maximum_iterations: int = 8,
) -> MatchingResult:
    if backend == "SEED_AUGMENT":
        return solve_seed_augment(
            regions,
            candidates,
            seed_edge_indices=seed_edge_indices,
            maximum_iterations=maximum_iterations,
        )

    seed_hypothesis = solve_seed_augment(
        regions,
        candidates,
        seed_edge_indices=seed_edge_indices,
        maximum_iterations=maximum_iterations,
    )
    if backend == "EXACT_BLOSSOM":
        exact = solve_exact_blossom(
            regions,
            candidates,
            max_region_triangles=exact_component_limit,
        )
        return replace(
            exact,
            hypothesis_margin=_hypothesis_margin(exact, seed_hypothesis),
        )
    if backend != "AUTO":
        raise ValueError(f"Unsupported matching backend: {backend}")

    exact_regions = tuple(
        region
        for region in regions
        if len(region.face_indices) <= exact_component_limit
    )
    oversized_regions = tuple(
        region
        for region in regions
        if len(region.face_indices) > exact_component_limit
    )
    exact = solve_exact_blossom(
        exact_regions,
        candidates,
        max_region_triangles=exact_component_limit,
    )
    if not oversized_regions:
        return replace(
            exact,
            backend="AUTO_EXACT_BLOSSOM",
            hypothesis_margin=_hypothesis_margin(exact, seed_hypothesis),
        )
    fallback = solve_seed_augment(
        oversized_regions,
        candidates,
        seed_edge_indices=seed_edge_indices,
        maximum_iterations=maximum_iterations,
    )
    combined = _combine_results(regions, candidates, exact, fallback)
    return replace(
        combined,
        hypothesis_margin=_hypothesis_margin(combined, seed_hypothesis),
    )
