"""Pure geometry tests for CAD-aware UV cut planning."""

import math
import unittest

from cad_reconstruction.uv_prep_core import plan_uv_cuts


class UVCutPlanTests(unittest.TestCase):
    def test_smooth_bend_stays_joined_and_hard_fold_cuts(self):
        vertices = ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.),
                    (0., 1., 0.), (0., 2., 0.), (1., 2., 0.),
                    (0., 3., 0.), (1., 3., 0.))
        faces = ((0, 1, 2, 3), (3, 2, 5, 4), (4, 5, 7, 6))
        normals = ((0., 0., 1.), (0., .5, math.sqrt(3) / 2), (0., 1., 0.))
        plan = plan_uv_cuts(vertices, faces, normals, (0, 0, 0))
        self.assertNotIn((2, 3), plan.cuts)
        self.assertIn((4, 5), plan.cuts)
        self.assertEqual(plan.angle_cuts, 1)

    def test_material_boundary_is_cut(self):
        vertices = ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.),
                    (0., 1., 0.), (0., 2., 0.), (1., 2., 0.))
        faces = ((0, 1, 2, 3), (3, 2, 5, 4))
        plan = plan_uv_cuts(vertices, faces, ((0., 0., 1.),) * 2, (0, 1))
        self.assertIn((2, 3), plan.cuts)
        self.assertEqual(plan.material_cuts, 1)

    def test_closed_cylindrical_wall_gets_one_axial_slit(self):
        segments = 8
        vertices = tuple(
            (math.cos(2 * math.pi * i / segments),
             math.sin(2 * math.pi * i / segments), float(z))
            for z in (0, 1) for i in range(segments)
        )
        faces = tuple((i, (i + 1) % segments,
                       (i + 1) % segments + segments, i + segments)
                      for i in range(segments))
        normals = tuple((math.cos(2 * math.pi * (i + .5) / segments),
                         math.sin(2 * math.pi * (i + .5) / segments), 0.)
                        for i in range(segments))
        plan = plan_uv_cuts(vertices, faces, normals, (0,) * segments)
        self.assertEqual(plan.annulus_slits, 1)
        self.assertEqual(len(plan.cuts), segments * 2 + 1)

    def test_sheet_hole_walls_separate_from_broad_faces(self):
        segments = 12
        vertices = tuple(
            (radius * math.cos(2 * math.pi * i / segments),
             radius * math.sin(2 * math.pi * i / segments), float(z))
            for radius, z in ((2, 1), (1, 1), (1, 0), (2, 0))
            for i in range(segments)
        )
        faces = []
        normals = []
        for i in range(segments):
            following = (i + 1) % segments
            faces.extend((
                (i, following, following + segments, i + segments),
                (i + segments, following + segments,
                 following + 2 * segments, i + 2 * segments),
                (i + 2 * segments, following + 2 * segments,
                 following + 3 * segments, i + 3 * segments),
                (i + 3 * segments, following + 3 * segments, following, i),
            ))
            radial = (math.cos(2 * math.pi * (i + .5) / segments),
                      math.sin(2 * math.pi * (i + .5) / segments), 0.)
            normals.extend(((0., 0., 1.), radial, (0., 0., -1.), radial))
        plan = plan_uv_cuts(vertices, tuple(faces), tuple(normals), (0,) * len(faces))
        self.assertIn((segments, segments + 1), plan.cuts)
        self.assertIn((2 * segments, 2 * segments + 1), plan.cuts)
        self.assertEqual(plan.annulus_slits, 2)


if __name__ == "__main__":
    unittest.main()
