"""Analyze screens each solid separately and honours protected faces.

blender --background --factory-startup --python tests/blender_cad_analysis_solids.py
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.analysis_worker import analyze
from cad_mesh_tool.mesh_io import capture
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.protected import ATTRIBUTE
from cad_mesh_tool.rebuild import tessellation

outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
theta = np.arange(32) * math.tau / 32
hole = .0065 * np.column_stack((np.cos(theta), np.sin(theta)))
points, triangles = tessellation([outer, hole])
n = len(points)
vertices, faces = [], []
for k in range(3):
    o = len(vertices)
    vertices += [(x + k * .1, y, z) for z in (0, .01) for x, y in points]
    faces += [[o + i for i in f[::-1]] for f in triangles] + [[o + n + i for i in f] for f in triangles]
    for ring, reverse in ((list(range(4)), False), (list(range(4, n)), True)):
        for a, b in zip(ring, ring[1:] + ring[:1]):
            faces.append([o + b, o + a, o + a + n, o + b + n] if reverse else [o + a, o + b, o + b + n, o + a + n])
mesh = bpy.data.meshes.new('Analysis plates')
mesh.from_pydata(vertices, [], faces)
mesh.update()
attr = mesh.attributes.new(ATTRIBUTE, 'BOOLEAN', 'FACE')
values = [False] * len(mesh.polygons)
values[0] = True
attr.data.foreach_set('value', values)
obj = bpy.data.objects.new('Analysis plates', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
profile = dict(epsilon_m=.0015, sample_count=750, operations=dict(DEFAULTS), preserve_curve_segmentation=False,
               perimeter_clearance_mm=0., hole_epsilon_mm=0., hole_detail_factor=1., separate_solids=True)
result = analyze(source, profile)
assert result['solids'] == 3 and len(result['solid_screens']) == 3, result.get('solid_screens')
assert all(item.get('recommendation') for item in result['solid_screens']), result['summary']
assert result['recommendation']['separate_solids'] is True
assert result['user_protected_faces'] == 1
assert 'Screened 3 solid(s): 3 passed' in result['summary'], result['summary']
whole = analyze(source, dict(profile, separate_solids=False))
assert len(whole['solid_screens']) == 1 and whole['solid_screens'][0]['solid'] is None
assert whole['recommendation'] and 'separate_solids' not in whole['recommendation']
print('PASS blender_cad_analysis_solids')
