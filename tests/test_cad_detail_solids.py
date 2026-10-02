"""Hole budget and independent solid mapping regressions."""
import math
import unittest
from cad_mesh_tool.geometry import hole_segment_count, segment_count
from cad_mesh_tool.solids import components, independent_components, solid_partitions, extract_component


class DetailTests(unittest.TestCase):
    def test_identity_and_independent_coarse_budget(self):
        radius, epsilon = .0065, .00015
        baseline=segment_count(radius,math.tau,True,epsilon)
        self.assertEqual(hole_segment_count(radius,64,epsilon),baseline)
        coarse=hole_segment_count(radius,64,epsilon,detail_factor=.5,hole_epsilon=.001)
        self.assertLess(coarse,baseline)
        self.assertGreater(radius*(1-math.cos(math.pi/coarse)),epsilon)
        self.assertLessEqual(radius*(1-math.cos(math.pi/coarse)),.001)
        self.assertGreaterEqual(hole_segment_count(radius,64,epsilon,detail_factor=.1),baseline)
        self.assertLessEqual(hole_segment_count(radius,10,epsilon,detail_factor=2),10)

    def test_invalid_settings(self):
        for value in (0.,-1.,float('nan'),float('inf'),2.1):
            with self.assertRaises(ValueError):
                hole_segment_count(.01,32,.0004,detail_factor=value)
        with self.assertRaises(ValueError):
            hole_segment_count(.01,32,.0004,hole_epsilon=-.1)


class SolidTests(unittest.TestCase):
    def test_nonplanar_shared_interface_is_not_inferred(self):
        vertices = [[0,0,0],[1,0,0],[1,1,.01],[0,1,0],[.5,.5,1],[.5,.5,-1]]
        cap = [[0,2,1],[0,3,2]]
        top = [[0,1,4],[1,2,4],[2,3,4],[3,0,4]]
        bottom = [[1,0,5],[2,1,5],[3,2,5],[0,3,5]]
        partitions = solid_partitions(cap+top+bottom,vertices)
        self.assertTrue(all(not item['shared_interface_faces'] for item in partitions))
        self.assertEqual(len(partitions),1)

    def test_shared_planar_cap_has_opposite_orientation_in_each_solid(self):
        faces = [[0,2,1],[0,1,3],[1,2,3],[2,0,3],
                 [0,4,1],[1,4,2],[2,4,0]]
        vertices = [[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1]]
        partitions = solid_partitions(faces,vertices)
        self.assertEqual(len(partitions),2)
        self.assertEqual(partitions[0]['faces'],[0,1,2,3])
        self.assertEqual(partitions[0]['reversed_faces'],[])
        self.assertEqual(partitions[1]['faces'],[0,4,5,6])
        self.assertEqual(partitions[1]['reversed_faces'],[0])
        snapshot = dict(vertices=vertices,faces=faces,triangles=faces,triangle_polygons=list(range(7)),
                        normals=[[0,0,1]]*21,materials=[0]*7,source_hash='parent')
        result = extract_component(snapshot,partitions[1]['faces'],partitions[1]['reversed_faces'])
        from cad_mesh_tool.geometry import topology
        self.assertEqual(topology(result['faces'])['winding'],0)
        self.assertEqual(topology(result['faces'])['boundary'],0)
        self.assertEqual(result['source_face_ids'],[0,4,5,6])
        self.assertEqual(result['reversed_source_faces'],[0])
        self.assertEqual(result['triangles'],result['faces'])
        self.assertEqual(result['normals'][0],[0.,0.,1.])

    def test_closed_shells_at_four_face_edge_are_separated(self):
        a = [[0,2,1],[0,1,3],[1,2,3],[2,0,3]]
        b = [[0,4,1],[0,1,5],[1,4,5],[4,0,5]]
        self.assertEqual(components(a+b), [list(range(8))])
        self.assertEqual(independent_components(a+b), [list(range(4)),list(range(4,8))])

    def test_open_junction_patches_remain_joined(self):
        faces = [[0,1,2],[1,0,3],[0,1,4],[1,0,5]]
        self.assertEqual(independent_components(faces), [list(range(4))])

    def test_clean_shell_is_peeled_from_ambiguous_junction(self):
        shell = [[0,2,1],[0,1,3],[1,2,3],[2,0,3]]
        faces = shell + [[0,1,4],[1,0,5]]
        self.assertEqual(independent_components(faces), [list(range(4)),[4,5]])

    def test_shared_edge_is_not_split_but_point_contacts_are(self):
        self.assertEqual(components([[0,1,2],[2,1,3],[2,4,5],[6,7,8]]),[[0,1],[2],[3]])

    def test_polygon_triangle_and_attribute_maps(self):
        snapshot=dict(vertices=[[i,0,0] for i in range(7)],faces=[[0,1,2],[3,4,5,6]],
                      triangles=[[0,1,2],[3,4,5],[3,5,6]],triangle_polygons=[0,1,1],
                      materials=[2,4],normals=[[0,0,1]]*7,sharp_edges=[[0,1],[3,4]],
                      cad_roles=['UNCLASSIFIED','BACKGROUND_PLANE'],source_hash='original')
        output=extract_component(snapshot,[1])
        self.assertEqual(output['faces'],[[0,1,2,3]])
        self.assertEqual(output['triangles'],[[0,1,2],[0,2,3]])
        self.assertEqual(output['sharp_edges'],[[0,1]])
        self.assertEqual(output['materials'],[4])
        self.assertEqual(output['source_vertex_ids'],[3,4,5,6])
        self.assertEqual(output['source_hash'],'original')
        self.assertEqual(output['cad_roles'],['BACKGROUND_PLANE'])


if __name__=='__main__':unittest.main()
