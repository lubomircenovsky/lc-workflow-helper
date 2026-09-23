"""Run in background Blender to check a manifold open-arc reconstruction."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.mesh_io import ROLES, capture, cleanup, make_mesh, topology_problem
from cad_mesh_tool.rebuild import reconstruct, tessellation
from cad_mesh_tool.straight_walls import cleanup_straight_walls
from cad_mesh_tool.validate import validate


radius = 0.006
center = np.array([radius, radius])
angles = np.linspace(-math.pi / 2, -math.pi, 9)
arc = center + radius * np.column_stack((np.cos(angles), np.sin(angles)))
profile = np.vstack((arc, [[0.0, 0.02], [0.02, 0.02], [0.02, 0.0]]))[::-1]
points, triangles = tessellation([profile])
count = len(points)
vertices = [(x, y, z) for z in (0.0, 0.01) for x, y in points]
faces = [list(reversed(tri)) for tri in triangles]
faces += [[count + i for i in tri] for tri in triangles]
faces += [[i, (i + 1) % count, (i + 1) % count + count, i + count] for i in range(count)]

mesh = bpy.data.meshes.new("CAD Open Arc")
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new("CAD Open Arc", mesh)
bpy.context.scene.collection.objects.link(obj)
assert not topology_problem(obj), topology_problem(obj)
source = capture(obj)
plan = discover(source["vertices"], source["faces"])
arcs = [feature for feature in plan["features"] if not feature["full"]]
assert arcs, "Open arc was not detected"
assert all(feature["segments"] <= feature["segments_before"] for feature in arcs)
candidate = reconstruct(source, plan["features"])
result_mesh, origin = make_mesh(candidate, "CAD Arc Result")
checkpoint = validate(
    source, result_mesh, origin, candidate["roles"], candidate["perimeters"],
    epsilon=0.0004, sample_count=500,
)
assert all(checkpoint["checks"].values()), checkpoint["checks"]
clean_mesh, _, _ = cleanup(result_mesh)
final_mesh, wall_report = cleanup_straight_walls(clean_mesh, {"enabled": True})
remap = wall_report["vertex_map"]
final_perimeters = [
    dict(item, ids=[remap[i] for i in item["ids"]],
         hole=[remap[i] for i in item["hole"]],
         strips=[[remap[i] for i in face] for face in item["strips"]])
    for item in candidate["perimeters"]
]
final_roles = [ROLES[value.value] for value in final_mesh.attributes["cad_role"].data]
final = validate(
    source, final_mesh, origin, final_roles, final_perimeters,
    epsilon=0.0004, sample_count=20000,
)
assert all(final["checks"].values()), final["checks"]
assert not topology_problem(obj)
print("CAD_ARC_OK", len(arcs), [(item["segments_before"], item["segments"]) for item in arcs])
