"""Auto reduces a requested support clearance that does not fit; Power user keeps it fixed.

blender --background --factory-startup --python tests/blender_cad_clearance_shrink.py
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.mesh_io import capture
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.rebuild import reconstruct, tessellation
from cad_mesh_tool.recovery import decisions

outer = np.array([[-.03, -.03], [.03, -.03], [.03, .03], [-.03, .03]])
theta = np.arange(32) * math.tau / 32
# Hole close to the right edge: a 4 mm support does not fit, ~2 mm does.
hole = np.array([.021, 0.]) + .0065 * np.column_stack((np.cos(theta), np.sin(theta)))
points, triangles = tessellation([outer, hole])
n = len(points)
vertices = [(x, y, z) for z in (0., .004) for x, y in points]
faces = [list(reversed(f)) for f in triangles] + [[n + i for i in f] for f in triangles]
for ring, reverse in ((list(range(4)), False), (list(range(4, n)), True)):
    for a, b in zip(ring, ring[1:] + ring[:1]):
        faces.append([b, a, a + n, b + n] if reverse else [a, b, b + n, a + n])
mesh = bpy.data.meshes.new('Shrink plate')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Shrink plate', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
plan = discover(source['vertices'], source['faces'], .0015)
options = dict(DEFAULTS, arcs=False, outer_cylinders=False)
selected = decisions(plan['features'], options)


def circular(policy):
    candidate = reconstruct(source, selected, options, preferred_clearance_m=.004, clearance_policy=policy)
    return [p for p in candidate['perimeters'] if p.get('kind') == 'circular']


fixed = circular('fixed')
assert fixed and all(p['layout'] == 'direct_join' for p in fixed), [p['layout'] for p in fixed]
shrunk = circular('shrink')
assert shrunk and all(p['layout'] != 'direct_join' and p['ids'] for p in shrunk), [p['layout'] for p in shrunk]
assert all(p['requested_clearance_m'] == .004 and p['clearance_m'] < .004 for p in shrunk)
try:
    reconstruct(source, selected, options, clearance_policy='grow')
except ValueError:
    pass
else:
    raise AssertionError('Unknown clearance policy accepted')
print('PASS blender_cad_clearance_shrink', [round(p['clearance_m'] * 1000, 3) for p in shrunk])
