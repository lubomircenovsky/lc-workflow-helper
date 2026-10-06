import unittest

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


def reference_intersections(vertices, triangles):
    """Scalar narrow phase over exhaustive pairs (the pre-vectorization code)."""
    p = vertices[triangles]
    low = p.min(axis=1)
    high = p.max(axis=1)
    cr = np.cross(p[:, 1]-p[:, 0], p[:, 2]-p[:, 0])
    norm = cr/np.maximum(np.linalg.norm(cr, axis=1)[:, None], 1e-30)
    hits = []
    tested = 0
    for i, j in exhaustive(low, high):
        da = (p[j]-p[i, 0])@norm[i]
        db = (p[i]-p[j, 0])@norm[j]
        if da.min() > 1e-9 or da.max() < -1e-9 or db.min() > 1e-9 or db.max() < -1e-9:
            continue
        tested += 1
        if max(abs(da)) < 1e-9 and max(abs(db)) < 1e-9:
            axis = int(np.argmax(abs(norm[i])))
            axes = [k for k in range(3) if k != axis]
            area = module.clipped_area(p[i][:, axes]-p[i, 0, axes], p[j][:, axes]-p[i, 0, axes])
            if area > 1e-12:
                hits.append({'a': int(i), 'b': int(j), 'type': 'coplanar_positive_area', 'area_projected': area})
        elif module.proper_cross(p[i], p[j], norm[j]) or module.proper_cross(p[j], p[i], norm[i]):
            hits.append({'a': int(i), 'b': int(j), 'type': 'proper_crossing'})
    hits.sort(key=lambda hit: (hit['a'], hit['b']))
    result = module.intersections(np.zeros((3, 3)), np.zeros((0, 3), dtype=int))
    result.update(intersections=hits, narrow_phase_pairs=tested)
    return result


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
        self.assertEqual(actual, reference_intersections(vertices, triangles))
        self.assertTrue(actual['intersections'])

    def test_planar_fans_and_overlaps_match_scalar_reference(self):
        rng = np.random.default_rng(5)
        for trial in range(12):
            # Shared-vertex fans, shared edges and genuinely overlapping
            # coplanar triangles, plus exact duplicates.
            points = np.column_stack((rng.uniform(-.02, .02, (40, 2)), np.zeros(40)))
            triangles = [rng.choice(40, 3, replace=False) for _ in range(45)]
            triangles += [[0, i, i+1] for i in range(1, 12)] + [list(triangles[0])]
            triangles = np.array(triangles)
            actual = module.intersections(points, triangles)
            expected = reference_intersections(points, triangles)
            self.assertEqual(actual, expected, trial)


if __name__ == '__main__':
    unittest.main()
