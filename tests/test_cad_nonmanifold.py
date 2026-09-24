"""Pure tests for exact preservation of existing non-manifold junctions."""

import unittest

from cad_mesh_tool.nonmanifold import protection, preservation_errors
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.recovery import recover


def joined_tetrahedra(offset=0):
    return [[offset + vi for vi in face] for face in (
        (0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3),
        (0, 4, 1), (0, 1, 5), (0, 5, 4), (1, 4, 5),
    )]


class NonManifoldTests(unittest.TestCase):
    def setUp(self):
        self.faces = joined_tetrahedra() + [
            [6, 8, 7], [6, 7, 9], [6, 9, 8], [7, 8, 9],
        ]
        self.snapshot = dict(faces=self.faces, vertices=[
            [0., 0., 0.], [0., 0., 1.], [1., 0., 0.], [0., 1., 0.],
            [-1., 0., 0.], [0., -1., 0.], [4., 0., 0.], [5., 0., 0.],
            [4., 1., 0.], [4., 0., 1.],
        ])
        self.features = [
            dict(id=3, category='concave_arc', faces=[0], vertices=[0, 2, 1]),
            dict(id=4, category='circular_hole', faces=[8], vertices=[6, 8, 7]),
        ]

    def test_patch_closes_over_touching_features_only(self):
        policy = protection(self.snapshot, self.features)
        self.assertEqual(policy['edges'], [[0, 1]])
        self.assertEqual(policy['faces'], list(range(8)))
        self.assertEqual(policy['features'], [3])
        self.assertEqual(policy['vertices'], list(range(6)))

    def test_exact_defect_and_faces_must_survive(self):
        policy = protection(self.snapshot, self.features)
        mapping = list(range(len(self.snapshot['vertices'])))
        self.assertEqual(preservation_errors(self.snapshot, self.faces,
                         self.snapshot['vertices'], mapping, policy), [])
        moved = [list(vertex) for vertex in self.snapshot['vertices']]
        moved[0][2] += .001
        self.assertIn('moved', ' '.join(preservation_errors(
            self.snapshot, self.faces, moved, mapping, policy)))
        changed = [list(face) for face in self.faces]
        changed[0] = list(reversed(changed[0]))
        self.assertIn('face', ' '.join(preservation_errors(
            self.snapshot, changed, self.snapshot['vertices'], mapping, policy)))
        added = self.faces + [[0, 1, 6]]
        self.assertIn('incidence', ' '.join(preservation_errors(
            self.snapshot, added, self.snapshot['vertices'], mapping, policy)))

    def test_multiple_bad_edges_are_tracked_individually(self):
        snapshot = dict(faces=joined_tetrahedra() + joined_tetrahedra(6),
                        vertices=[[float(i), 0., 0.] for i in range(12)])
        policy = protection(snapshot, [])
        self.assertEqual(policy['edges'], [[0, 1], [6, 7]])
        self.assertEqual(preservation_errors(snapshot, snapshot['faces'],
                         snapshot['vertices'], list(range(12)), policy), [])

    def test_forced_patch_is_not_retried(self):
        features = [dict(feature, forced_skip_reason='Existing non-manifold junction')
                    if feature['id'] == 3 else feature for feature in self.features]
        choices = []

        def attempt(selected):
            choices.append([(item['id'], item['decision']) for item in selected])
            return selected

        _, skipped, count = recover(features, DEFAULTS, attempt, lambda _result: None)
        self.assertEqual(count, 1)
        self.assertEqual(choices[0], [(3, 'SKIP'), (4, 'REBUILD')])
        self.assertEqual([item['feature'] for item in skipped], [3])


if __name__ == '__main__':
    unittest.main()
