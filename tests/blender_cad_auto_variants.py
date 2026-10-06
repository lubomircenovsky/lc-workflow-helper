"""Parallel Auto variants (child processes) give the same trials and winner.

blender --background --factory-startup --python tests/blender_cad_auto_variants.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool import auto_worker
from cad_mesh_tool.api import code_hash
from cad_mesh_tool.mesh_io import capture
from cad_mesh_tool.rebuild import tessellation

outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
theta = np.arange(32) * math.tau / 32
holes = [.0065 * np.column_stack((np.cos(theta), np.sin(theta))) + c for c in ((-.02, 0), (.02, 0))]
points, triangles = tessellation([outer, *holes])
n = len(points)
vertices = [(x, y, z) for z in (0, .01) for x, y in points]
faces = [f[::-1] for f in triangles] + [[n + i for i in f] for f in triangles]
rings = [(list(range(4)), False), (list(range(4, 36)), True), (list(range(36, 68)), True)]
for ring, reverse in rings:
    for a, b in zip(ring, ring[1:] + ring[:1]):
        faces.append([b, a, a + n, b + n] if reverse else [a, b, b + n, a + n])
mesh = bpy.data.meshes.new('Variant plate')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Variant plate', mesh)
bpy.context.scene.collection.objects.link(obj)
snapshot = capture(obj)


def run(parallel):
    root = Path(tempfile.mkdtemp(prefix='cad_variants_')) / 'run'
    root.mkdir()
    (root / 'source.json').write_text(json.dumps(snapshot))
    profile = dict(epsilon_m=.0015, hole_detail_factor=.5, hole_epsilon_mm=1.5, perimeter_clearance_mm=1.5,
                   method='CAD_AUTO', delivery='CAD_AUTO_VARIANTS', source_name=obj.name,
                   source_hash=snapshot['source_hash'], code_hash=code_hash(), tool_version='0.4.1',
                   sample_count=20000, unit_scale=1.0, retry_component=None)
    if parallel:
        slots = root.parent / 'slots'
        slots.mkdir()
        (slots / 'capacity.txt').write_text('3')
        profile.update(variant_slot_dir=str(slots), parallel_variant_triangles=0)
    (root / 'profile.json').write_text(json.dumps(profile))
    auto_worker.main(root)
    report = json.loads((root / 'auto_manifest.json').read_text())
    body = report['bodies'][0]
    trials = [(t['variant'], t['status'], t.get('triangles'), t.get('accepted')) for t in body['trials']]
    candidates = [(root / t['path'] / 'candidate.json').read_bytes() for t in body['trials'] if t['status'] != 'FAIL']
    logs = [(root / t['path'] / 'worker.log').exists() for t in body['trials']]
    return body['selected_variant'], trials, candidates, logs


sequential = run(False)
parallel = run(True)
assert sequential[:3] == parallel[:3], (sequential[:2], parallel[:2])
assert len(sequential[1]) >= 2
assert all(parallel[3]) and not any(sequential[3]), 'parallel variants run in child processes'
print('PASS blender_cad_auto_variants', parallel[0], len(parallel[1]))
