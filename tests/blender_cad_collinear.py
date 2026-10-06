"""Collinear crease vertices are removed without moving the surface.

blender --background --factory-startup --python tests/blender_cad_collinear.py
"""
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.collinear import remove_collinear_vertices
from cad_mesh_tool.geometry import topology
from cad_mesh_tool.mesh_io import ROLES

# A box whose top-front edge carries two extra collinear vertices (8, 9), as a
# plane triangulation pinned onto a bend rim would leave them.
V = [(0, 0, 0), (3, 0, 0), (3, 1, 0), (0, 1, 0), (0, 0, 1), (3, 0, 1), (3, 1, 1), (0, 1, 1),
     (1, 0, 1), (2, 0, 1)]
F = [
    [0, 3, 2, 1],                     # bottom
    [4, 8, 7], [8, 9, 7], [9, 6, 7], [9, 5, 6],   # top, fanned onto the edge
    [0, 1, 5, 9, 8, 4],               # front n-gon holding the same vertices
    [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7],
]
PLANE = ROLES.index('BACKGROUND_PLANE')


def build(name, roles=None, sharp=()):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(V, [], F)
    mesh.update()
    mesh.attributes.new('cad_role', 'INT', 'FACE').data.foreach_set('value', roles or [PLANE] * len(F))
    for e in mesh.edges:
        e.use_edge_sharp = tuple(sorted(e.vertices)) in sharp
    for p in mesh.polygons:
        p.use_smooth = True
    mesh.normals_split_custom_set([n.vector.copy() for n in mesh.corner_normals])
    return mesh


def area(mesh):
    return sum(p.area for p in mesh.polygons)


# 1) Both vertices go; the top becomes one quad; every kept vertex is exact.
mesh = build('Collinear')
result, report = remove_collinear_vertices(mesh)
assert report['removed_vertices'] == 2, report
assert report['vertex_map'][8] == report['vertex_map'][9] == -1
assert len(result.vertices) == 8 and len(result.polygons) == 6, (len(result.vertices), len(result.polygons))
for old, new in enumerate(report['vertex_map']):
    if new >= 0:
        assert tuple(result.vertices[new].co) == tuple(mesh.vertices[old].co)
assert abs(area(result) - area(mesh)) < 1e-6
counts = topology([list(p.vertices) for p in result.polygons])
assert not any(counts[k] for k in ('boundary', 'nonmanifold', 'winding', 'duplicates')), counts

# 2) A blocked vertex (e.g. on a perimeter ring) stays; the other one goes.
result, report = remove_collinear_vertices(build('Blocked'), blocked_vertices={8})
assert report['removed_vertices'] == 1 and report['vertex_map'][8] >= 0 and report['vertex_map'][9] == -1, report

# 2b) A user-protected (frozen) front face is never merged, so neither goes.
result, report = remove_collinear_vertices(build('Frozen'), frozen_vertices={0, 1, 5, 9, 8, 4})
assert report['removed_vertices'] == 0, report

# 3) Different roles inside one side are not merged.
roles = [PLANE] * len(F)
roles[2] = ROLES.index('DETAIL_REBUILT')
result, report = remove_collinear_vertices(build('Mixed', roles))
assert report['removed_vertices'] == 0, report

# 4) A sharp flag on the crease survives on the merged edge.
sharp = {(4, 8), (8, 9), (5, 9)}
result, report = remove_collinear_vertices(build('Sharp', sharp=sharp))
assert report['removed_vertices'] == 2
m = report['vertex_map']
edge = next(e for e in result.edges if tuple(sorted(e.vertices)) == tuple(sorted((m[4], m[5]))))
assert edge.use_edge_sharp

# 4b) A sharp flag on a flat edge is a display hint and does not block.
result, report = remove_collinear_vertices(build('FlatSharp', sharp={(7, 8)}))
assert report['removed_vertices'] == 2, report

# 5) A vertex off the line (a real corner) is never removed.
V[8] = (1, 0, 1.001)
result, report = remove_collinear_vertices(build('Corner'))
assert report['vertex_map'][8] >= 0, report
print('PASS blender_cad_collinear')
