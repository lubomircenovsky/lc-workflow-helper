"""Auto runs each independent solid of one source in its own worker process.

blender --background --factory-startup --python tests/blender_cad_auto_parallel.py
"""
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import auto_jobs
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint
from LC_workflow_addon.cad_mesh_tool.rebuild import tessellation


def plate(offset):
    outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
    theta = np.arange(32) * math.tau / 32
    hole = .0065 * np.column_stack((np.cos(theta), np.sin(theta)))
    points, triangles = tessellation([outer, hole])
    n = len(points)
    vertices = [(x + offset, y, z) for z in (0, .01) for x, y in points]
    faces = [f[::-1] for f in triangles] + [[i + n for i in f] for f in triangles]
    for ring, reverse in ((list(range(4)), False), (list(range(4, n)), True)):
        for a, b in zip(ring, ring[1:] + ring[:1]):
            faces.append([b, a, a + n, b + n] if reverse else [a, b, b + n, a + n])
    return vertices, faces


vertices, faces = [], []
for index in range(3):
    v, f = plate(index * .1)
    faces += [[i + len(vertices) for i in face] for face in f]
    vertices += v
mesh = bpy.data.meshes.new('Three plates')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Three plates', mesh)
bpy.context.scene.collection.objects.link(obj)

addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = 'SELECTED'
    state.concurrent_workers = 3
    state.auto_epsilon_mm = 1.5
    before = fingerprint(obj)
    with tempfile.TemporaryDirectory() as temp:
        batch = auto_jobs.AutoBatch(bpy.context, [obj], Path(temp))
        started = []
        while batch.step():
            started.append(len(batch.running))
            time.sleep(.02)
        assert len(batch.items) == 3, batch.items
        assert max(started) == 3, 'three solids should run concurrently'
        assert sorted(item['component'] for item in batch.items) == [0, 1, 2]
        rows = list(state.results)
        assert len(rows) == 3, [(r.source_label, r.status, r.reason) for r in rows]
        assert sorted(r.component_index for r in rows) == [0, 1, 2]
        assert all(r.status == 'PASS' and r.output for r in rows), [(r.status, r.reason) for r in rows]
        assert sorted(r.source_label for r in rows) == [f'Three plates / Solid {k}' for k in (1, 2, 3)]
        runs = {Path(r.auto_run_dir) for r in rows}
        assert len(runs) == 3
        for run in runs:
            report = json.loads((run / 'auto_manifest.json').read_text())
            assert len(report['partitions']) == 3 and len(report['bodies']) == 1
            assert report['selected_components'] == [json.loads((run / 'profile.json').read_text())['retry_component']]
        sources = {(run / 'source.json').read_bytes() for run in runs}
        assert len(sources) == 1, 'every solid reads the same immutable snapshot'
        assert fingerprint(obj) == before
    print('PASS blender_cad_auto_parallel')
finally:
    addon.unregister()
