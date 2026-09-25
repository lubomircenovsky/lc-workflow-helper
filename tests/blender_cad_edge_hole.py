"""Run in background Blender to check a closed near-edge cylindrical hole."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.geometry import topology
from cad_mesh_tool.mesh_io import ROLES, capture, cleanup, make_mesh, topology_problem
from cad_mesh_tool.rebuild import reconstruct, select_rim_samples, tessellation
from cad_mesh_tool.straight_walls import cleanup_straight_walls
from cad_mesh_tool.validate import validate
from cad_mesh_tool.diagnostics import add_review_groups


clustered = {0: 0.0, 1: 0.01, 2: 0.02, 3: 0.5, 4: 1.0}
assert select_rim_samples(list(clustered), clustered, 4, 1.0, False) == [0, 2, 3, 4]
rotated = {index: 2 * math.pi * index / 17 for index in range(17)}
assert select_rim_samples(list(rotated), rotated, 17, 2 * math.pi, True) == list(rotated)


outer = np.array([[-0.02, -0.02], [0.02, -0.02], [0.02, 0.02], [-0.02, 0.02]])
radius = 0.0065
center = np.array([0.0133, 0.0])
angles = np.arange(32) * 2 * math.pi / 32
hole = center + radius * np.column_stack((np.cos(angles), np.sin(angles)))
points, triangles = tessellation([outer, hole])
count = len(points)
vertices = [(x, y, z) for z in (0.0, 0.01) for x, y in points]
faces = [list(reversed(tri)) for tri in triangles]
faces += [[count + i for i in tri] for tri in triangles]
for loop, reverse in ((range(4), False), (range(4, count), True)):
    ids = list(loop)
    for a, b in zip(ids, ids[1:] + ids[:1]):
        faces.append([b, a, a + count, b + count] if reverse else [a, b, b + count, a + count])

mesh = bpy.data.meshes.new("CAD Near Edge Hole")
mesh.from_pydata(vertices, [], faces)
mesh.update()
next(edge for edge in mesh.edges if set(edge.vertices) == {0, 1}).use_edge_sharp = True
obj = bpy.data.objects.new("CAD Near Edge Hole", mesh)
bpy.context.scene.collection.objects.link(obj)
assert not topology_problem(obj), topology(faces)
source = capture(obj)
plan = discover(source["vertices"], source["faces"])
assert any(item["category"] == "circular_hole" for item in plan["features"])
candidate = reconstruct(source, plan["features"])
direct = [item for item in candidate["perimeters"] if item["layout"] == "direct_join"]
assert direct, "Near-edge circular hole did not use direct triangulation"
result_mesh, origin = make_mesh(candidate, "CAD Near Edge Result")
assert any(edge.use_edge_sharp for edge in result_mesh.edges)
review_object = bpy.data.objects.new('CAD Near Edge Review', result_mesh)
assert any(item['group'] == 'CAD_Skipped' for item in candidate['review_features'])
assert any(item['group'] == 'CAD_Skipped' for item in add_review_groups(review_object, candidate))
assert review_object.vertex_groups.get('CAD_Skipped') is not None
validation = validate(
    source, result_mesh, origin, candidate["roles"], candidate["perimeters"],
    epsilon=0.0004, sample_count=500,
    source_to_output=candidate['source_to_candidate'],
)
assert all(validation["checks"].values()), validation["checks"]
checkpoint_sharp = next(edge for edge in result_mesh.edges if edge.use_edge_sharp)
checkpoint_sharp.use_edge_sharp = False
rejected = validate(source, result_mesh, origin, candidate['roles'], candidate['perimeters'],
                    epsilon=0.0004, sample_count=100,
                    source_to_output=candidate['source_to_candidate'])
assert not rejected['sharp_edges_preserved']
assert all(rejected['checks'].values())
checkpoint_sharp.use_edge_sharp = True
clean_mesh, _, _ = cleanup(result_mesh)
assert any(edge.use_edge_sharp for edge in clean_mesh.edges)
final_mesh, wall_report = cleanup_straight_walls(clean_mesh, {"enabled": True})
sharp = {tuple(sorted(edge.vertices)) for edge in final_mesh.edges if edge.use_edge_sharp}
assert tuple(sorted(wall_report['vertex_map'][candidate['source_to_candidate'][i]]
                    for i in (0, 1))) in sharp
remap = wall_report["vertex_map"]
final_perimeters = [
    dict(item, ids=[remap[i] for i in item["ids"]],
         hole=[remap[i] for i in item["hole"]],
         strips=[[remap[i] for i in face] for face in item["strips"]])
    for item in candidate["perimeters"]
]
final_roles = [ROLES[value.value] for value in final_mesh.attributes["cad_role"].data]
final_validation = validate(
    source, final_mesh, origin, final_roles, final_perimeters,
    epsilon=0.0004, sample_count=20000,
    source_to_output=[remap[i] if i >= 0 else -1 for i in candidate['source_to_candidate']],
)
assert all(final_validation["checks"].values()), final_validation["checks"]
assert not topology_problem(obj)
bad_mesh = bpy.data.meshes.new("CAD Non Manifold")
bad_mesh.from_pydata(vertices, [], faces + [faces[0]])
bad_mesh.update()
bad_obj = bpy.data.objects.new("CAD Non Manifold", bad_mesh)
bpy.context.scene.collection.objects.link(bad_obj)
assert "nonmanifold=" in topology_problem(bad_obj)
try:
    capture(bad_obj)
except ValueError as exc:
    assert "closed manifold" in str(exc)
else:
    raise AssertionError("Non-manifold source was accepted")
print("CAD_EDGE_HOLE_OK", len(plan["features"]), len(direct), final_validation["checks"])
