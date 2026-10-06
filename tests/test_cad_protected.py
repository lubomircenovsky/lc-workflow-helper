"""Pure tests for user-protected faces (cad_protected face attribute)."""
import unittest

from cad_mesh_tool.protected import SKIP_REASON, face_cycles, locked_faces, mark_features, preservation_errors
from cad_mesh_tool.solids import extract_component
from cad_mesh_tool.source_repair import repair_collinear_faces


def snapshot(faces, vertices, locked=()):
    return dict(faces=faces, vertices=vertices, triangles=faces, materials=[0]*len(faces),
                normals=[[0, 0, 1]]*sum(map(len, faces)), user_protected_faces=list(locked))


class ProtectedFaceTests(unittest.TestCase):
    def test_features_touching_protected_vertices_are_forced_to_skip(self):
        snap = snapshot([[0, 1, 2], [2, 3, 0]], [[0, 0, 0]]*4, locked=[0])
        features = [dict(id=0, vertices=[2, 5]), dict(id=1, vertices=[3, 7]),
                    dict(id=2, vertices=[1], forced_skip_reason='Touches an unchanged source non-manifold junction')]
        self.assertEqual(mark_features(snap, features), [0, 2])
        self.assertEqual(features[0]['forced_skip_reason'], SKIP_REASON)
        self.assertNotIn('forced_skip_reason', features[1])
        # An existing, stricter reason is never replaced.
        self.assertTrue(features[2]['forced_skip_reason'].startswith('Touches an unchanged'))
        self.assertEqual(mark_features(snapshot([[0, 1, 2]], [[0, 0, 0]]*3), features), [])

    def test_preservation_compares_cycles_and_positions(self):
        source = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [5., 5., 5.]]
        cycles = [[0, 1, 2]]
        output_vertices = [[1., 0., 0.], [0., 1., 0.], [0., 0., 0.]]
        source_to_output = [2, 0, 1, -1]
        self.assertEqual(preservation_errors(cycles, source, [[0, 1, 2]], output_vertices, source_to_output), [])
        self.assertEqual(preservation_errors(cycles, source, [[1, 2, 0]], output_vertices, source_to_output), [])
        self.assertTrue(preservation_errors(cycles, source, [[0, 2, 1]], output_vertices, source_to_output))
        moved = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1e-6]]
        self.assertTrue(preservation_errors(cycles, source, [[0, 1, 2]], moved, source_to_output))
        self.assertTrue(preservation_errors(cycles, source, [[0, 1, 2]], output_vertices, [2, 0, -1, -1]))

    def test_component_extraction_remaps_protected_faces(self):
        snap = snapshot([[0, 1, 2], [3, 4, 5], [3, 5, 6]], [[float(i), 0., 0.] for i in range(7)], locked=[2])
        snap['triangle_polygons'] = [0, 1, 2]
        part = extract_component(snap, [1, 2])
        self.assertEqual(part['user_protected_faces'], [1])
        self.assertEqual(face_cycles(part), [part['faces'][1]])
        self.assertEqual(locked_faces(extract_component(snap, [0])), [])

    def test_clean_source_repair_keeps_protected_faces(self):
        snap = snapshot([[0, 1, 2]], [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], locked=[0])
        repaired, report = repair_collinear_faces(snap)
        self.assertIs(repaired, snap)
        self.assertEqual(report['removed_zero_area_faces'], [])


if __name__ == '__main__':
    unittest.main()
