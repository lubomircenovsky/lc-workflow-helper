"""Headless selected-operation and standalone-perimeter CAD regression."""

import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.api import apply_result, prepare_selected
from cad_mesh_tool.mesh_io import capture, make_mesh
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.rebuild import reconstruct, tessellation
from cad_mesh_tool.recovery import decisions
from cad_mesh_tool.validate import validate
from cad_mesh_tool.worker import main as run_worker


outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
angles = np.arange(32) * math.tau / 32
hole = .0065 * np.column_stack((np.cos(angles), np.sin(angles)))
points, triangles = tessellation([outer, hole])
count = len(points)
vertices = [(x, y, z) for z in (0., .01) for x, y in points]
faces = [list(reversed(face)) for face in triangles]
faces += [[count + i for i in face] for face in triangles]
for ring, reverse in ((range(4), False), (range(4, count), True)):
    ids = list(ring)
    for a, b in zip(ids, ids[1:] + ids[:1]):
        faces.append([b, a, a + count, b + count] if reverse else [a, b, b + count, a + count])
mesh = bpy.data.meshes.new('CAD Operations Source')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('CAD Operations Source', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
plan = discover(source['vertices'], source['faces'])
assert any(f['category'] == 'circular_hole' for f in plan['features'])

for only_perimeter in (False, True):
    if only_perimeter:
        processed = bpy.data.objects.new('CAD Hole Reduction Output', result)
        processed.location = tuple(origin)
        bpy.context.scene.collection.objects.link(processed)
        source = capture(processed)
        plan = discover(source['vertices'], source['faces'])
    options = {name: False for name in DEFAULTS}
    options['perimeter_loops'] = only_perimeter
    options['circular_holes'] = not only_perimeter
    selected = decisions(plan['features'], options)
    candidate = reconstruct(source, selected, options)
    disabled_faces = {fi for feature in selected if feature['decision'] == 'DISABLED'
                      for fi in feature['faces']}
    mapping = candidate['source_to_candidate']
    candidate_faces = {tuple(face) for face in candidate['faces']}
    assert all(tuple(mapping[vi] for vi in source['faces'][fi]) in candidate_faces
               for fi in disabled_faces)
    result, origin = make_mesh(candidate, 'CAD Selected Operation')
    report = validate(source, result, origin, candidate['roles'], candidate['perimeters'], .0004, 500,
                      require_reduction=not only_perimeter)
    assert all(report['checks'].values()), (only_perimeter, report['checks'])
    if only_perimeter:
        assert any(p['layout'] != 'direct_join' for p in candidate['perimeters'])
        protected = {fi for f in selected if f['decision'] == 'PERIMETER_ONLY' for fi in f['faces']}
        mapped = candidate['source_to_candidate']
        generated = {tuple(f) for f in candidate['faces']}
        assert all(tuple(mapped[v] for v in source['faces'][fi]) in generated for fi in protected)
    else:
        assert any(p['layout'] == 'direct_join' for p in candidate['perimeters'])
    print('CAD_OPERATION_OK', 'perimeter_only' if only_perimeter else 'holes_only',
          len(candidate['faces']), report['checks'])

    with tempfile.TemporaryDirectory() as directory:
        run_dir = Path(directory) / 'cad_run'
        source_object = processed if only_perimeter else obj
        source_hash = capture(source_object)['source_hash']
        prepare_selected(run_dir, obj=source_object, operations=options)
        run_worker(run_dir)
        names = apply_result(run_dir, include_checkpoint=False)
        assert len(names) == 1
        imported = bpy.data.objects[names[0]]
        assert imported.data is not source_object.data
        assert capture(source_object)['source_hash'] == source_hash
        assert imported.get('cad_geometry_status') == 'PASS'
        print('CAD_OPERATION_IMPORT_OK', 'perimeter_only' if only_perimeter else 'holes_only')
