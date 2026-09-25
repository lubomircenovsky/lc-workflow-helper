"""Headless selected-operation and standalone-perimeter CAD regression."""

import math
import json
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
from cad_mesh_tool.rebuild import reconstruct, tessellation, choose_perimeter
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
mesh.normals_split_custom_set([(0.3, 0.0, 0.9539392014)] * len(mesh.loops))
next(edge for edge in mesh.edges if set(edge.vertices) == {0, 1}).use_edge_sharp = True
obj = bpy.data.objects.new('CAD Operations Source', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
assert source['sharp_edges'] == [[0, 1]]
assert mesh.has_custom_normals
assert any(abs(normal[0]) > 0.1 for normal in (n.vector for n in mesh.corner_normals))
assert all(np.dot(source['normals'][li], mesh.polygons[p.index].normal) > .99
           for p in mesh.polygons for li in p.loop_indices)
plan = discover(source['vertices'], source['faces'])
assert any(f['category'] == 'circular_hole' for f in plan['features'])
hole_only = {name: name == 'circular_holes' for name in DEFAULTS}
sharp_candidate = reconstruct(dict(source, sharp_edges=[[4, 5]]),
                              decisions(plan['features'], hole_only), hole_only)
assert sharp_candidate['lost_sharp_edges'] == [[4, 5]]
preferred, attempts = choose_perimeter(hole, outer, [], radius=.0065,
                                       center=np.array([0., 0.]), preferred_clearance_m=.001)
assert preferred is not None and .0065 < attempts[-1]['size'] <= .0075
tight, attempts = choose_perimeter(hole, np.array([[-.01, -.01], [.01, -.01],
                                                   [.01, .01], [-.01, .01]]), [],
                                   radius=.0065, center=np.array([0., 0.]),
                                   preferred_clearance_m=.005)
assert tight is not None and attempts[-1]['size'] < .0115

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
    assert not result.has_custom_normals
    mapped_sharp = {tuple(sorted(edge.vertices)) for edge in result.edges if edge.use_edge_sharp}
    assert tuple(sorted(mapping[i] for i in (0, 1))) in mapped_sharp
    report = validate(source, result, origin, candidate['roles'], candidate['perimeters'], .0004, 500,
                      require_reduction=not only_perimeter, source_to_output=mapping)
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
        assert any(edge.use_edge_sharp for edge in imported.data.edges)
        assert imported.get('cad_geometry_status') == 'PASS'
        print('CAD_OPERATION_IMPORT_OK', 'perimeter_only' if only_perimeter else 'holes_only')

rim_mesh = mesh.copy()
next(edge for edge in rim_mesh.edges if set(edge.vertices) == {4, 5}).use_edge_sharp = True
rim_obj = bpy.data.objects.new('CAD Sharp Rim Source', rim_mesh)
bpy.context.scene.collection.objects.link(rim_obj)
rim_hash = capture(rim_obj)['source_hash']
with tempfile.TemporaryDirectory() as directory:
    run_dir = Path(directory) / 'cad_sharp_review'
    prepare_selected(run_dir, obj=rim_obj, operations=hole_only, perimeter_clearance_mm=1.0)
    run_worker(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['geometry_status'] == 'PASS' and manifest['partial']
    assert [4, 5] in manifest['lost_sharp_edges']
    assert manifest['summary'].startswith('Validated output needs shading review.')
    assert manifest['perimeter_clearance_mm'] == 1.0
    names = apply_result(run_dir, include_checkpoint=False)
    reviewed = bpy.data.objects[names[0]]
    assert reviewed.vertex_groups.get('CAD_Review_SharpEdges') is not None
    assert capture(rim_obj)['source_hash'] == rim_hash
    print('CAD_SHARP_REVIEW_OK', manifest['lost_sharp_edges'])

perimeter_only = {name: name == 'perimeter_loops' for name in DEFAULTS}
with tempfile.TemporaryDirectory() as directory:
    run_dir = Path(directory) / 'cad_clearance'
    prepare_selected(run_dir, obj=processed, operations=perimeter_only,
                     perimeter_clearance_mm=1.0)
    run_worker(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    clearances = manifest['circular_perimeter_clearances_mm']
    assert clearances and all(0 < value <= 1.000001 for value in clearances), clearances
    assert 'Selected circular perimeter clearance (nominal):' in (run_dir / 'REPORT.md').read_text(encoding='utf-8')
    print('CAD_CLEARANCE_OK', clearances)
