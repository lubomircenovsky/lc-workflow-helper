"""Geometric causes observed on the original triangulated production parts."""
import math
import unittest
import numpy as np

from cad_mesh_tool.detect import refine_open_interval
from cad_mesh_tool.geometry import adjacency, face_normals, planar_regions, loops
from cad_mesh_tool.segment_backoff import relax_near_distance_failure


class RegionBoundaryTests(unittest.TestCase):
    def test_distance_backoff_is_local_bounded_and_respects_disabled_features(self):
        source = dict(vertices=[[0,0,0], [0,1,0], [0,0,1], [10,0,0]])
        features = [dict(id=i, vertices=[vertex], segments=3, segments_before=10,
                         decision=decision) for i,vertex,decision in
                    [(0,0,'REBUILD'), (1,1,'DISABLED'), (2,2,'SKIP'), (3,3,'REBUILD')]]
        measured = dict(checks=dict(sampled_distance=False, closed_oriented=True),
                        distance_reference_center_m=[0,0,0],
                        distance=dict(forward=dict(within_limits=False,
                                      worst_sample_centered_m=[10,0,0],
                                      worst_budget_sample_centered_m=[0,0,0])))
        changes = relax_near_distance_failure(source, features, measured)
        self.assertEqual(changes, [dict(id=0, previous=3, actual=7)])
        self.assertEqual([f['segments'] for f in features], [7,3,3,3])
        for _ in range(5):relax_near_distance_failure(source, features, measured)
        self.assertEqual(features[0]['segments'], 10)
        self.assertEqual(relax_near_distance_failure(source, features, measured), [])
        measured['checks']['closed_oriented'] = False
        features[0]['segments'] = 3
        self.assertEqual(relax_near_distance_failure(source, features, measured), [])

    def test_large_reference_avoids_fragmentation_from_a_thin_triangle(self):
        vertices = np.array([[0,0,0], [1,0,0], [1,.0001,1e-8],
                             [1,.1,0], [0,.1,0]], dtype=float)
        faces = [[0,1,2], [0,2,3], [0,3,4]]
        normals = face_normals(vertices, faces)
        _, adjacent = adjacency(faces)
        self.assertGreater(len(planar_regions(vertices, faces, normals, adjacent)), 1)
        stable = planar_regions(vertices, faces, normals, adjacent, stable_seeds=True)
        self.assertEqual(len(stable), 1)
        self.assertEqual(set(stable[0]), {0,1,2})
        self.assertEqual(len(loops([faces[i] for i in stable[0]])), 1)
        # Exclusion still splits the region; stable seeds never consume protected faces.
        protected = planar_regions(vertices, faces, normals, adjacent, [1], stable_seeds=True)
        self.assertEqual({i for group in protected for i in group}, {0,2})
        self.assertEqual(len(protected), 2)

    def test_stable_reference_does_not_expand_planarity_tolerance(self):
        vertices = np.array([[0,0,0], [1,0,0], [1,.1,0], [0,.1,.0001]])
        faces = [[0,1,2], [0,2,3]]
        _, adjacent = adjacency(faces)
        self.assertEqual(len(planar_regions(vertices, faces, face_normals(vertices, faces),
                                           adjacent, stable_seeds=True)), 2)

    def test_measured_rails_override_the_wrong_largest_gap(self):
        angles = np.radians([84,180,264,360])
        vertices = [[.27*math.cos(a), .27*math.sin(a), z]
                    for z in (0,.02) for a in angles]
        boundary = [[0,1], [1,2], [2,3], [3,7], [7,6], [6,5], [5,4], [4,0]]
        feature = dict(id=7, faces=[1,2,3], full=False, frame=np.eye(3).tolist(),
                       origin=[0,0,0], center=[0,0], radius=.27, residual=0,
                       boundary=boundary, start=0., span=math.radians(264),
                       category='convex_arc', segments=3, segments_before=3)
        refine_open_interval(vertices, feature, .0015)
        self.assertAlmostEqual(feature['start'], math.radians(84))
        self.assertAlmostEqual(feature['span'], math.radians(276))
        self.assertEqual(feature['faces'], [1,2,3])
        self.assertEqual(feature['segments'], 3)
        self.assertTrue(feature['interval_refined_from_boundary'])
        ambiguous = dict(feature, start=0., span=math.radians(264),
                         boundary=boundary+[[1,6]])
        refine_open_interval(vertices, ambiguous, .0015)
        self.assertEqual(ambiguous['start'], 0.)


if __name__ == '__main__':
    unittest.main()
