"""Compare batched CAD distances with the original per-point float64 path."""

import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.precise_distance import accurate_distances, point_triangles_squared


def original_distances(points, triangles, bvh):
    low = triangles.min(axis=1)
    high = triangles.max(axis=1)
    values = []
    for point in points:
        index = bvh.find_nearest(Vector(point))[2]
        upper = float(point_triangles_squared(point, triangles[index:index + 1])[0])
        separation = np.maximum(np.maximum(low - point, point - high), 0)
        eligible = np.flatnonzero(np.sum(separation * separation, axis=1) <= upper + 1e-16)
        values.append(float(np.min(point_triangles_squared(point, triangles[eligible]))))
    return np.sqrt(values)


root = Path(__file__).resolve().parents[2] / ".codex" / "temp"
fixture = next(root.glob("cad_active_protected_probe_*/source.json"), None)
if fixture is not None:
    source = json.loads(fixture.read_text(encoding="utf-8"))
    vertices = np.asarray(source["vertices"], dtype=float)
    triangles = np.asarray(source["triangles"], dtype=int)
else:
    vertices = np.asarray(((0., 0., 0.), (1., 0., 0.), (0., 1., 0.),
                           (1., 1., 0.), (0., 0., 1e-7)), dtype=float)
    triangles = np.asarray(((0, 1, 2), (1, 3, 2), (0, 1, 4)), dtype=int)

bvh = BVHTree.FromPolygons([Vector(point) for point in vertices],
                           [tuple(map(int, face)) for face in triangles], all_triangles=True)
faces = vertices[triangles]
rng = np.random.default_rng(17)
points = np.concatenate((vertices[:min(1000, len(vertices))],
                         vertices[:min(1000, len(vertices))] + (1e-5, 2e-5, -1e-5),
                         rng.uniform(vertices.min(0), vertices.max(0), size=(120, 3))))
expected = original_distances(points, faces, bvh)
actual = accurate_distances(points, faces, bvh)
assert np.array_equal(actual, expected), float(np.max(np.abs(actual - expected)))
assert np.isfinite(actual).all() and np.count_nonzero(actual) > 0
assert len(accurate_distances(np.empty((0, 3)), faces, bvh)) == 0
dense_faces = np.repeat(faces[:1], 9000, axis=0)
dense_bvh = BVHTree.FromPolygons(
    [Vector(point) for point in vertices],
    [tuple(map(int, triangles[0])) for _ in range(len(dense_faces))], all_triangles=True)
dense_points = np.asarray((faces[0].mean(0), faces[0].mean(0) + (0, 0, 1e-5)))
dense_expected = original_distances(dense_points, dense_faces, dense_bvh)
dense_actual = accurate_distances(dense_points, dense_faces, dense_bvh)
assert np.array_equal(dense_actual, dense_expected)
print("CAD_DISTANCE_EXACT_OK", len(points), len(triangles), bpy.app.version_string)
