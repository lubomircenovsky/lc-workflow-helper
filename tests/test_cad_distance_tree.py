import unittest

import numpy as np

from cad_mesh_tool.precise_distance import (
    _candidate_tree, _tree_squared, point_triangles_squared,
)


class DistanceTreeTests(unittest.TestCase):
    def compare(self, triangles, points, upper):
        low, high = triangles.min(axis=1), triangles.max(axis=1)
        tree = _candidate_tree(low, high)
        actual = _tree_squared(points, triangles, low, high, tree, upper)
        expected = []
        for point, bound in zip(points, upper):
            separation = np.maximum(np.maximum(low - point, point - high), 0)
            ids = np.flatnonzero(np.sum(separation * separation, axis=1) <= bound + 1e-16)
            expected.append(point_triangles_squared(point, triangles[ids]).min())
        np.testing.assert_array_equal(actual, expected)

    def test_distributed_skinny_and_degenerate_triangles(self):
        rng = np.random.default_rng(4202)
        origin = rng.uniform(-10, 10, (4096, 1, 3))
        triangles = origin + rng.normal(0, .1, (4096, 3, 3))
        triangles[:400, 2] = triangles[:400, 0] + 1e-10
        triangles[400:800, 2] = triangles[400:800, 0]
        indices = rng.integers(len(triangles), size=200)
        points = triangles[indices].mean(axis=1) + rng.normal(0, 1e-8, (200, 3))
        upper = point_triangles_squared(points, triangles[indices])
        self.compare(triangles, points, upper)
        # A float32 BVH may suggest a non-nearest triangle. Its upper bound
        # must still retain every closer exact candidate.
        self.compare(triangles, points[:20], np.full(20, 1000.))

    def test_identical_bounds_and_threshold_rounding(self):
        triangle = np.array(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.)))
        triangles = np.repeat(triangle[None, :, :], 9000, axis=0)
        below = np.nextafter(1e-8, 0.)
        above = np.nextafter(1e-8, np.inf)
        points = np.array(((.2, .2, below), (.2, .2, 1e-8),
                           (.2, .2, above), (1., 0., 0.)))
        upper = point_triangles_squared(points, triangles[:len(points)])
        self.compare(triangles, points, upper)

    def test_translated_geometry_and_empty_sample_batch(self):
        rng = np.random.default_rng(32)
        triangles = rng.normal(size=(2500, 3, 3)) + 100000.
        points = triangles[:60].mean(axis=1)
        upper = point_triangles_squared(points, triangles[:60])
        self.compare(triangles, points, upper)
        low, high = triangles.min(axis=1), triangles.max(axis=1)
        values = _tree_squared(np.empty((0, 3)), triangles, low, high,
                               _candidate_tree(low, high), np.empty(0))
        self.assertEqual(values.shape, (0,))


if __name__ == '__main__':
    unittest.main()
