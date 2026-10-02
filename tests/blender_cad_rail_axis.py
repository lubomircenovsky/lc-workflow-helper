"""Measured parallel rails correct noisy axis votes without weakening validation."""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover, refine_rail_axis
from cad_mesh_tool.geometry import basis, circle_fit
from cad_mesh_tool.mesh_io import capture
from cad_mesh_tool.rebuild import cylinder_rims, tessellation
from cad_mesh_tool.worker import validated_candidate
from cad_mesh_tool.recovery import decisions

radius = .01
angles = np.linspace(-math.pi / 2, -math.pi, 17)
arc = [radius, radius] + radius * np.column_stack((np.cos(angles), np.sin(angles)))
outline = np.vstack((arc, [[0, .04], [.04, .04], [.04, 0]]))[::-1]
points, triangles = tessellation([outline])
count = len(points)
vertices = [(x, y, z) for z in (0., 1.6) for x, y in points]
faces = [list(reversed(tri)) for tri in triangles]
faces += [[count + i for i in tri] for tri in triangles]
faces += [[i, (i + 1) % count, (i + 1) % count + count, i + count]
          for i in range(count)]
mesh = bpy.data.meshes.new('Long extrusion')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Long extrusion', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
plan = discover(source['vertices'], source['faces'], .0015)
feature = next(f for f in plan['features'] if not f['full'])
frame = basis(np.array([2.7e-5, -9e-6, 1.]))
p = (np.asarray(source['vertices']) - feature['origin']) @ frame.T
center, fitted_radius, residual = circle_fit(p[feature['vertices'], :2])
assert residual > 1e-6, residual
feature.update(frame=frame.tolist(), center=center.tolist(), radius=fitted_radius,
               residual=residual)
refine_rail_axis(source['vertices'], feature, .0015)
assert feature.get('axis_refined_from_rails')
assert feature['residual'] < 1e-6
assert abs(abs(np.array(feature['frame'])[2, 2]) - 1) < 1e-12
p = (np.asarray(source['vertices']) - feature['origin']) @ np.array(feature['frame']).T
assert len(cylinder_rims(feature, p)) == 2
options = dict(circular_holes=True, perimeter_loops=False, arcs=True,
               outer_cylinders=True, background_cleanup=True, straight_walls=True)
candidate, result, origin, validation = validated_candidate(
    source, decisions(plan['features'], options), options,
    dict(epsilon_m=.0015, sample_count=1000))
assert all(validation['checks'].values()), validation['checks']
bpy.data.meshes.remove(result)

# Nonparallel candidate rails must never be averaged into a guessed axis.
feature = dict(feature, residual=1e-5, frame=frame.tolist())
feature.pop('axis_refined_from_rails', None)
altered = np.array(source['vertices'])
altered[count:, 0] += np.linspace(0, .0005, count)
before = dict(feature)
refine_rail_axis(altered, feature, .0015)
assert feature == before
print('CAD_RAIL_AXIS_OK')
