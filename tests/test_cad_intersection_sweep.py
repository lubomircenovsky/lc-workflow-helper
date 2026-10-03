import unittest
from unittest.mock import patch

import numpy as np

from cad_mesh_tool import intersections as module


def exhaustive(low, high, tolerance=1e-9):
    for index in range(len(low)):
        candidates = np.flatnonzero(
            np.all(high >= low[index]-tolerance, axis=1)
            & np.all(low <= high[index]+tolerance, axis=1))
        for other in candidates:
            if other > index:
                yield index, other


class IntersectionSweepTests(unittest.TestCase):
    def test_exact_candidates_random_flat_and_extreme_scales(self):
        rng = np.random.default_rng(413)
        for scale in (1e-12, 1e-9, 1., 1e9):
            low = rng.normal(size=(300, 3))*scale
            high = low+rng.uniform(0, .3, size=low.shape)*scale
            for flat in (False, True):
                if flat:
                    high[:, 2] = low[:, 2] = 0
                expected = set(exhaustive(low, high))
                actual = list(module.candidate_pairs(low, high))
                self.assertEqual(set(actual), expected)
                self.assertEqual(len(actual), len(expected))

    def test_rounding_at_tolerance_boundary_and_reversed_indices(self):
        for origin in (0., -1., 1., 1e8):
            edge = origin+1e-9
            positions = [origin, edge, np.nextafter(edge, np.inf),
                         np.nextafter(edge, -np.inf)]
            for order in (positions, positions[::-1]):
                low = np.column_stack((order, np.zeros((4, 2))))
                self.assertEqual(set(module.candidate_pairs(low, low)),
                                 set(exhaustive(low, low)))

    def test_exact_narrow_phase_results_and_order(self):
        rng = np.random.default_rng(812)
        vertices = rng.normal(size=(90, 3))*.01
        vertices[:30, 2] = 0  # includes coplanar positive-area overlaps
        triangles = rng.permutation(90).reshape(-1, 3)
        actual = module.intersections(vertices, triangles)
        with patch.object(module, 'candidate_pairs', exhaustive):
            expected = module.intersections(vertices, triangles)
        self.assertEqual(actual, expected)
        self.assertTrue(actual['intersections'])


if __name__ == '__main__':
    unittest.main()
