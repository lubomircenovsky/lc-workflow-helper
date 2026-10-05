"""Detection of sustained cylindrical bends with measured non-level ends."""
import math
import unittest

import numpy as np

from cad_mesh_tool.detect import discover, _discover
from cad_mesh_tool.geometry import measured_cylinder_ends, expanded_edge_chain


def curved_strip(count=18, angle=math.pi/2):
    theta=np.linspace(0.,angle,count+1)
    vertices=np.array([[.02*math.cos(t),.02*math.sin(t),z+.012*math.sin(2*t)]
                       for z in (0.,1.) for t in theta])
    faces=[]
    for i in range(count):
        j=i+count+1
        faces.extend([[i,i+1,j+1],[i,j+1,j]])
    ring=list(range(count+1))+list(reversed(range(count+1,2*(count+1))))
    boundary=list(zip(ring,ring[1:]+ring[:1]))
    return vertices,faces,boundary


class MeasuredDetectionTests(unittest.TestCase):
    def test_nested_transition_subdivisions_are_all_sewn(self):
        splits={(0,3):[0,2,3],(0,2):[0,1,2]}
        self.assertEqual(expanded_edge_chain(splits,0,3),[0,1,2,3])
        splits[0,1]=[0,3,1]
        with self.assertRaises(ValueError):
            expanded_edge_chain(splits,0,3)

    def test_curved_ends_detected_without_selection_or_world_axis(self):
        vertices,faces,_=curved_strip()
        ax=.731;ay=.419
        rotation=np.array([[math.cos(ax),-math.sin(ax),0.],
                           [math.sin(ax),math.cos(ax),0.],[0.,0.,1.]])
        rotation=rotation@np.array([[1.,0.,0.],[0.,math.cos(ay),-math.sin(ay)],
                                   [0.,math.sin(ay),math.cos(ay)]])
        for points in (vertices,vertices@rotation.T+[4.,-2.,7.]):
            self.assertEqual(_discover(points,faces)['features'],[])
            plan=discover(points,faces,.0015)
            self.assertEqual(len(plan['features']),1)
            cy=plan['features'][0]
            self.assertTrue(cy['measured_end_contours'])
            self.assertEqual(set(cy['faces']),set(range(len(faces))))
            self.assertEqual(cy['segments_before'],18)
            self.assertLess(cy['segments'],18)
            self.assertLess(cy['residual'],1e-6)

    def test_existing_features_keep_identity(self):
        vertices,faces,_=curved_strip()
        vertices[:,2]=np.repeat([0.,1.],19)
        original=_discover(vertices,faces,.0015)['features']
        plan=discover(vertices,faces,.0015)
        self.assertTrue(original)
        self.assertEqual(plan['features'][:len(original)],original)

    def test_short_compound_patch_and_cone_not_added(self):
        vertices,faces,_=curved_strip(count=3)
        self.assertEqual(discover(vertices,faces)['supplemental_features'],0)
        vertices,faces,_=curved_strip()
        vertices[19:,:2]*=1.5
        self.assertEqual(discover(vertices,faces)['supplemental_features'],0)

    def test_strict_boundary_and_end_order(self):
        points,_,boundary=curved_strip()
        def ends(edges=boundary,p=points):
            return measured_cylinder_ends(edges,p,[0.,0.],.02,0.,math.pi/2)
        expected=[list(range(19)),list(range(19,38))]
        self.assertEqual(ends(),expected)
        self.assertEqual(ends([(b,a) for a,b in reversed(boundary)]),expected)
        self.assertIsNone(ends(boundary[:-1]))
        self.assertIsNone(ends(boundary+[(0,2)]))
        self.assertIsNone(ends(boundary+boundary[:1]))
        folded=points.copy();folded[[5,6]]=folded[[6,5]]
        self.assertIsNone(ends(p=folded))
        crossed=points.copy();crossed[25,2]=-1.
        self.assertIsNone(ends(p=crossed))


if __name__=='__main__':
    unittest.main()
