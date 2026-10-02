"""Exact surface repair and explicit rejection of guessed or protected repairs."""
import unittest
import numpy as np
from cad_mesh_tool.geometry import topology
from cad_mesh_tool.source_repair import repair_collinear_faces


def collinear_fixture():
    vertices = [[0,0,0],[1,0,0],[0,1,0],[0,0,1],[.25,0,0],[.75,0,0]]
    faces = [[0,2,1],[0,4,3],[4,5,3],[5,1,3],[1,2,3],[2,0,3],
             [1,4,0],[1,5,4]]
    return dict(vertices=vertices,faces=faces,triangles=faces,triangle_polygons=list(range(8)),
                materials=list(range(8)),normals=[[0,0,1]]*24,sharp_edges=[],
                source_hash='immutable',cad_roles=None)


class SourceRepairTests(unittest.TestCase):
    def test_exact_surface_and_attribute_mapping(self):
        source = collinear_fixture()
        repaired, report = repair_collinear_faces(source)
        self.assertIs(repaired['vertices'],source['vertices'])
        self.assertEqual(repaired['source_hash'],'immutable')
        self.assertEqual(report['removed_zero_area_faces'],[6,7])
        self.assertEqual(report['subdivided_source_faces'],[0])
        self.assertEqual(report['vertices_moved'],0)
        self.assertEqual(len(repaired['faces']),8)
        self.assertEqual(repaired['materials'][:3],[0,0,0])
        self.assertEqual(repaired['source_face_ids'][:3],[0,0,0])
        self.assertEqual(topology(repaired['faces']),topology(source['faces']))
        v=np.asarray(repaired['vertices']);t=np.asarray(repaired['triangles'])
        self.assertTrue(np.all(np.linalg.norm(np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]]),axis=1)>2e-16))
        self.assertEqual(source['faces'][6],[1,4,0])

    def test_sharp_or_locked_boundary_is_not_silently_changed(self):
        source=collinear_fixture();source['sharp_edges']=[[0,1]]
        with self.assertRaisesRegex(ValueError,'sharp boundary'):
            repair_collinear_faces(source)
        source=collinear_fixture();source['cad_roles']=['LOCKED_FEATURE']*8
        with self.assertRaisesRegex(ValueError,'protected CAD'):
            repair_collinear_faces(source)

    def test_tiny_nonzero_surface_is_not_treated_as_collinear(self):
        source=collinear_fixture();source['vertices'][4][1]=1e-18
        with self.assertRaisesRegex(ValueError,'not exact collinear'):
            repair_collinear_faces(source)

    def test_open_or_entirely_collapsed_input_is_rejected(self):
        source=collinear_fixture();source['faces']=source['faces'][:-1];source['triangles']=source['faces']
        with self.assertRaisesRegex(ValueError,'closed independent solid'):
            repair_collinear_faces(source)
        source=collinear_fixture();source['vertices']=[[i,0,0] for i in range(6)]
        with self.assertRaisesRegex(ValueError,'nondegenerate surface'):
            repair_collinear_faces(source)


if __name__=='__main__':unittest.main()
