"""Completed cylindrical support must update the feature's closure contract."""
import math
import unittest

from cad_mesh_tool.detect import complete_cylinders, discover


class CompletedCylinderTests(unittest.TestCase):
    def test_missing_sector_becomes_closed_hole_or_outer_cylinder(self):
        count = 36
        vertices = [[.02 * math.cos(i * math.tau / count),
                     .02 * math.sin(i * math.tau / count), z]
                    for z in (0., .008) for i in range(count)]
        faces = [[i, (i + 1) % count, (i + 1) % count + count, i + count]
                 for i in range(count)]
        for sign, category in ((-1, 'circular_hole'), (1, 'outer_cylinder')):
            feature = dict(id=0, faces=list(range(count - 1)), vertices=[],
                           frame=[[1,0,0],[0,1,0],[0,0,1]], origin=[0,0,0],
                           center=[0,0], radius=.02, full=False, sign=sign,
                           category='concave_arc' if sign < 0 else 'convex_arc')
            completed = complete_cylinders(vertices, faces, [feature], .0015)[0]
            self.assertTrue(completed['full'])
            self.assertEqual(completed['category'], category)
            self.assertEqual(completed['segments_before'], count)
            self.assertEqual(len(completed['faces']), count)
            self.assertAlmostEqual(completed['span'], math.tau)

    def test_flat_rectangular_strip_is_not_a_cylinder(self):
        # Four corners fit a circle, but the long flat walls do not follow it.
        outline = [(0.,0.), (.008,0.), (.008,.064), (0.,.064)]
        vertices = [[x,y,z] for z in (0.,6.366) for x,y in outline]
        faces = []
        for i in range(4):
            j=(i+1)%4
            faces.extend([[i,j,j+4],[i,j+4,i+4]])
        self.assertEqual(discover(vertices, faces, .0015)['features'], [])


if __name__ == '__main__':
    unittest.main()
