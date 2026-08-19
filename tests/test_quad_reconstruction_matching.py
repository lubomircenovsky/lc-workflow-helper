from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ADDON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADDON_ROOT))

from quad_reconstruction.candidates import CandidateSettings, generate_candidates
from quad_reconstruction.confidence import calculate_confidence
from quad_reconstruction.matching.augmenting import solve_seed_augment
from quad_reconstruction.matching.blossom import solve_exact_blossom
from quad_reconstruction.matching.solver import solve_matching
from quad_reconstruction.models import (
    CandidateMetrics,
    CandidatePair,
    MatchingResult,
    TriangleRegion,
    ValidationResult,
)
from quad_reconstruction.profiles import profile_defaults
from quad_reconstruction.regions import RegionSettings, build_triangle_regions
from quad_reconstruction.scoring import (
    ScoringWeights,
    normalized_candidate_cost,
    robust_metric_scales,
)
from test_quad_reconstruction_core import make_snapshot


ZERO_METRICS = CandidateMetrics(
    planarity_error=0.0,
    warp_error=0.0,
    corner_error=0.0,
    log_aspect_error=0.0,
    opposite_edge_error=0.0,
    diagonal_balance_error=0.0,
    flow_alignment_error=0.0,
    curvature_continuity_error=0.0,
    valence_delta=0.0,
    uv_discontinuity_penalty=0.0,
    sharp_or_seam_penalty=0.0,
    material_boundary_penalty=0.0,
    attribute_violation_count=0,
)


def graph_candidate(index, face_a, face_b, cost, *, region_index=0, metrics=ZERO_METRICS):
    return CandidatePair(
        index=index,
        region_index=region_index,
        face_indices=(face_a, face_b),
        dissolve_edge_index=index,
        quad_vertices=(0, 1, 2, 3),
        metrics=metrics,
        cost=cost,
        hard_valid=True,
        rejection_reasons=(),
        relaxation_flags=(),
    )


class CandidateTests(unittest.TestCase):
    def test_known_pair_produces_cyclic_quad(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        regions = build_triangle_regions(snapshot, RegionSettings())
        candidates = generate_candidates(snapshot, regions, CandidateSettings())
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].hard_valid)
        self.assertEqual(candidates[0].quad_vertices, (0, 1, 3, 2))

    def test_self_intersecting_geometry_is_rejected(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        snapshot = replace(
            snapshot,
            vertices=((0.0, 0.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        )
        regions = build_triangle_regions(snapshot, RegionSettings())
        candidate = generate_candidates(snapshot, regions, CandidateSettings())[0]
        self.assertFalse(candidate.hard_valid)
        self.assertIn("SELF_INTERSECTION", candidate.rejection_reasons)

    def test_uv_relaxation_is_reported_when_not_protected(self):
        snapshot = make_snapshot(
            ((0, 1, 2), (2, 1, 3)),
            split_uv_edge=(1, 2),
        )
        regions = build_triangle_regions(
            snapshot,
            RegionSettings(protect_uv=False),
        )
        candidate = generate_candidates(
            snapshot,
            regions,
            CandidateSettings(profile="BALANCED", protect_uv=False),
        )[0]
        self.assertTrue(candidate.hard_valid)
        self.assertIn("UV", candidate.relaxation_flags)


class ScoringTests(unittest.TestCase):
    def test_region_metrics_use_deterministic_median_mad_scaling(self):
        metrics = tuple(
            replace(ZERO_METRICS, planarity_error=value)
            for value in (10.0, 12.0, 100.0)
        )
        scales = robust_metric_scales(metrics)
        self.assertEqual(scales["planarity_error"], 12.0)
        cost = normalized_candidate_cost(metrics[0], ScoringWeights(), scales)
        self.assertAlmostEqual(cost, 3.0 * 10.0 / 12.0)


class ExactMatchingTests(unittest.TestCase):
    def test_blossom_solves_odd_cycle_exactly(self):
        region = TriangleRegion(0, (0, 1, 2, 3, 4), (0, 1, 2, 3, 4), ())
        candidates = tuple(
            graph_candidate(index, index, (index + 1) % 5, 0.0)
            for index in range(5)
        )
        result = solve_exact_blossom((region,), candidates, max_region_triangles=8)
        self.assertTrue(result.exact)
        self.assertEqual(result.cardinality, 2)
        self.assertEqual(len(result.unmatched_face_indices), 1)

    def test_blossom_minimizes_cost_at_maximum_cardinality(self):
        region = TriangleRegion(0, (0, 1, 2, 3), (0, 1, 2, 3), ())
        candidates = (
            graph_candidate(0, 0, 1, 5.0),
            graph_candidate(1, 2, 3, 5.0),
            graph_candidate(2, 1, 2, 1.0),
            graph_candidate(3, 3, 0, 1.0),
        )
        result = solve_exact_blossom((region,), candidates)
        self.assertEqual(result.selected_candidate_indices, (2, 3))
        self.assertEqual(result.total_cost, 2.0)

    def test_lexicographic_attribute_penalty_breaks_equal_cost_tie(self):
        region = TriangleRegion(0, (0, 1, 2, 3), (0, 1, 2, 3), ())
        relaxed_metrics = replace(ZERO_METRICS, attribute_violation_count=1)
        candidates = (
            graph_candidate(0, 0, 1, 1.0, metrics=relaxed_metrics),
            graph_candidate(1, 2, 3, 1.0, metrics=relaxed_metrics),
            graph_candidate(2, 1, 2, 1.0),
            graph_candidate(3, 3, 0, 1.0),
        )
        first = solve_exact_blossom((region,), candidates)
        second = solve_exact_blossom((region,), candidates)
        self.assertEqual(first.selected_candidate_indices, (2, 3))
        self.assertEqual(first, second)

    def test_explicit_exact_leaves_oversized_region_unresolved(self):
        region = TriangleRegion(0, (0, 1, 2), (0,), ())
        candidates = (graph_candidate(0, 0, 1, 0.0),)
        result = solve_exact_blossom((region,), candidates, max_region_triangles=2)
        self.assertFalse(result.exact)
        self.assertEqual(result.cardinality, 0)
        self.assertEqual(result.unmatched_face_indices, (0, 1, 2))

    def test_auto_uses_fallback_only_for_oversized_regions(self):
        regions = (
            TriangleRegion(0, (0, 1), (0,), ()),
            TriangleRegion(1, (2, 3, 4), (1,), ()),
        )
        candidates = (
            graph_candidate(0, 0, 1, 0.0),
            graph_candidate(1, 2, 3, 0.0, region_index=1),
        )
        result = solve_matching(
            "AUTO",
            regions,
            candidates,
            exact_component_limit=2,
        )
        self.assertEqual(result.backend, "AUTO_MIXED")
        self.assertFalse(result.exact)
        self.assertEqual(result.selected_candidate_indices, (0, 1))


class ProfileAndConfidenceTests(unittest.TestCase):
    def test_profile_defaults_express_relaxation_policy(self):
        self.assertTrue(profile_defaults("STRICT").protect_uv)
        self.assertTrue(profile_defaults("BALANCED").protect_materials)
        self.assertFalse(profile_defaults("BALANCED").protect_uv)
        self.assertFalse(profile_defaults("AGGRESSIVE").protect_materials)

    def test_hard_validation_failure_forces_failed_confidence(self):
        matching = MatchingResult("EXACT_BLOSSOM", (), (), 0, 0.0, True)
        validation = ValidationResult(False, True, True, True, True, 0, 0, ("bad",))
        confidence = calculate_confidence(matching, (), validation)
        self.assertEqual(confidence.label, "FAILED")
        self.assertEqual(confidence.score, 0.0)

    def test_exact_clean_result_has_high_confidence(self):
        candidate = graph_candidate(0, 0, 1, 0.0)
        matching = MatchingResult("EXACT_BLOSSOM", (0,), (), 1, 0.0, True, hypothesis_margin=1.0)
        validation = ValidationResult(True, True, True, True, True, 1, 1)
        confidence = calculate_confidence(matching, (candidate,), validation)
        self.assertEqual(confidence.label, "HIGH")
        self.assertEqual(confidence.score, 100.0)


class MatchingTests(unittest.TestCase):
    def test_augmenting_path_increases_cardinality(self):
        region = TriangleRegion(0, (0, 1, 2, 3), (0, 1, 2), ())
        candidates = (
            graph_candidate(0, 1, 2, 0.0),
            graph_candidate(1, 0, 1, 1.0),
            graph_candidate(2, 2, 3, 1.0),
        )
        result = solve_seed_augment((region,), candidates)
        self.assertEqual(result.cardinality, 2)
        self.assertEqual(result.selected_candidate_indices, (1, 2))
        self.assertEqual(result.unmatched_face_indices, ())

    def test_odd_cycle_is_safe_and_explicitly_inexact(self):
        region = TriangleRegion(0, (0, 1, 2), (0, 1, 2), ())
        candidates = (
            graph_candidate(0, 0, 1, 0.0),
            graph_candidate(1, 1, 2, 0.0),
            graph_candidate(2, 2, 0, 0.0),
        )
        result = solve_seed_augment((region,), candidates)
        self.assertEqual(result.cardinality, 1)
        self.assertFalse(result.exact)
        self.assertEqual(len(result.unmatched_face_indices), 1)

    def test_matching_is_deterministic(self):
        region = TriangleRegion(0, (0, 1, 2, 3), (0, 1, 2, 3), ())
        candidates = (
            graph_candidate(0, 0, 1, 1.0),
            graph_candidate(1, 1, 2, 1.0),
            graph_candidate(2, 2, 3, 1.0),
            graph_candidate(3, 3, 0, 1.0),
        )
        first = solve_seed_augment((region,), candidates)
        second = solve_seed_augment((region,), candidates)
        self.assertEqual(first, second)

    def test_matching_is_face_disjoint_on_odd_cycle_with_tails(self):
        region = TriangleRegion(0, tuple(range(7)), tuple(range(8)), ())
        candidates = (
            graph_candidate(0, 0, 1, 0.0),
            graph_candidate(1, 1, 2, 0.0),
            graph_candidate(2, 2, 0, 0.0),
            graph_candidate(3, 0, 3, 1.0),
            graph_candidate(4, 1, 4, 1.0),
            graph_candidate(5, 2, 5, 1.0),
            graph_candidate(6, 3, 6, 1.0),
            graph_candidate(7, 5, 6, 1.0),
        )
        result = solve_seed_augment((region,), candidates)
        selected_faces = [
            face
            for index in result.selected_candidate_indices
            for face in candidates[index].face_indices
        ]
        self.assertEqual(len(selected_faces), len(set(selected_faces)))

    def test_region_solver_does_not_select_candidates_from_other_regions(self):
        regions = (
            TriangleRegion(0, (0, 1, 2, 3), (0, 1, 2), ()),
            TriangleRegion(1, (4, 5, 6, 7), (3, 4, 5), ()),
        )
        candidates = (
            graph_candidate(0, 0, 1, 2.0),
            graph_candidate(1, 2, 3, 2.0),
            graph_candidate(2, 1, 2, 1.0),
            graph_candidate(3, 3, 0, 1.0),
            graph_candidate(4, 4, 5, 0.0, region_index=1),
        )
        result = solve_seed_augment((regions[0],), candidates)
        self.assertTrue(
            all(candidates[index].region_index == 0 for index in result.selected_candidate_indices)
        )


if __name__ == "__main__":
    unittest.main()
