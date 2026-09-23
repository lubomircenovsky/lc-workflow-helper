"""Headless regression: one bad feature must not discard a good component."""

import json
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import apply_result, prepare_selected
from cad_mesh_tool.detect import discover as real_discover
from cad_mesh_tool.mesh_io import capture, fingerprint
from cad_mesh_tool.rebuild import tessellation
import cad_mesh_tool.worker as worker


outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
angles = np.arange(32) * math.tau / 32
hole = .0065 * np.column_stack((np.cos(angles), np.sin(angles)))
points, triangles = tessellation([outer, hole])
count = len(points)
component_vertices = [(x, y, z) for z in (0., .01) for x, y in points]
component_faces = [list(reversed(face)) for face in triangles]
component_faces += [[count + i for i in face] for face in triangles]
for ring, reverse in ((range(4), False), (range(4, count), True)):
    ids = list(ring)
    for a, b in zip(ids, ids[1:] + ids[:1]):
        component_faces.append([b, a, a + count, b + count] if reverse else [a, b, b + count, a + count])
vertices = []
faces = []
for dx in (0., .12):
    offset = len(vertices)
    vertices.extend((x + dx, y, z) for x, y, z in component_vertices)
    faces.extend([offset + vi for vi in face] for face in component_faces)
mesh = bpy.data.meshes.new('CAD Partial Source')
mesh.from_pydata(vertices, [], faces)
mesh.update()
source_object = bpy.data.objects.new('CAD Partial Source', mesh)
bpy.context.scene.collection.objects.link(source_object)
before = fingerprint(source_object)


def one_bad_feature(*args, **kwargs):
    plan = real_discover(*args, **kwargs)
    holes = [feature for feature in plan['features'] if feature['category'] == 'circular_hole']
    assert len(holes) == 2, len(holes)
    holes.sort(key=lambda feature: min(feature['vertices']))
    holes[1]['segments'] = 1
    return plan


operations = dict(circular_holes=True, perimeter_loops=False, arcs=False,
                  outer_cylinders=False, background_cleanup=False, straight_walls=False)
with tempfile.TemporaryDirectory() as directory:
    run = Path(directory) / 'partial'
    prepare_selected(run, obj=source_object, operations=operations)
    worker.discover = one_bad_feature
    try:
        worker.main(run)
    finally:
        worker.discover = real_discover
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['partial'] and manifest['geometry_status'] == 'PASS'
    assert len(manifest['skipped_features']) == 1, manifest['skipped_features']
    assert manifest['review_groups'] and any(row['group'] == 'CAD_Skipped'
                                              for row in manifest['review_groups'])
    assert all(json.loads((run / name).read_text(encoding='utf-8'))['checks'].values()
               for name in ('validation_checkpoint.json', 'validation_final.json'))
    candidate = json.loads((run / 'candidate.json').read_text(encoding='utf-8'))
    source = capture(source_object)
    skipped_id = manifest['skipped_features'][0]['feature']
    feature = next(item for item in json.loads((run / 'plan.json').read_text(encoding='utf-8'))['features']
                   if item['id'] == skipped_id)
    mapped = candidate['source_to_candidate']
    result_faces = {tuple(face) for face in candidate['faces']}
    assert all(tuple(mapped[vi] for vi in source['faces'][fi]) in result_faces
               for fi in feature['faces'])
    names = apply_result(run, include_checkpoint=False)
    output = bpy.data.objects[names[0]]
    group = output.vertex_groups.get('CAD_Skipped')
    assert group is not None and any(any(weight.group == group.index for weight in vertex.groups)
                                     for vertex in output.data.vertices)
    assert fingerprint(source_object) == before
    assert output.data is not source_object.data
    print('CAD_PARTIAL_OK', manifest['recovery_attempts'], manifest['skipped_features'])
