"""Headless regression for preserving non-manifold junctions in partial CAD output."""

import json
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import apply_result, prepare_selected
from cad_mesh_tool.mesh_io import fingerprint, topology_problem
from cad_mesh_tool.nonmanifold import preservation_errors, protection
from cad_mesh_tool.rebuild import tessellation
from cad_mesh_tool.worker import main


def source_mesh(defects):
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
            faces.append([b, a, a + count, b + count] if reverse else
                         [a, b, b + count, a + count])
    for index in range(defects):
        offset = len(vertices)
        x = .2 + .1 * index
        vertices += [(x, 0., 0.), (x, 0., .01), (x + .015, 0., 0.),
                     (x, .015, 0.), (x - .015, 0., 0.), (x, -.015, 0.)]
        faces += [[offset + vi for vi in face] for face in (
            (0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3),
            (0, 4, 1), (0, 1, 5), (0, 5, 4), (1, 4, 5),
        )]
    mesh = bpy.data.meshes.new(f'CAD NonManifold {defects}')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


operations = dict(circular_holes=True, perimeter_loops=False, arcs=False,
                  outer_cylinders=False, background_cleanup=False, straight_walls=False)
for defect_count in (1, 2):
    obj = source_mesh(defect_count)
    before = fingerprint(obj)
    assert f'nonmanifold={defect_count}' in topology_problem(obj)
    assert not topology_problem(obj, preserve_nonmanifold=True)
    with tempfile.TemporaryDirectory() as directory:
        run = Path(directory) / 'nonmanifold'
        try:
            prepare_selected(run, obj=obj, operations=operations)
        except ValueError as error:
            assert 'nonmanifold' in str(error)
        else:
            raise AssertionError('The ordinary button accepted non-manifold input')
        prepare_selected(run, obj=obj, operations=operations, preserve_nonmanifold=True)
        main(run)
        manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
        assert manifest['geometry_status'] == 'PASS' and manifest['partial']
        assert len(manifest['preserved_source_nonmanifold']['edges']) == defect_count
        assert manifest['final']['t'] < manifest['before']['t']
        for name in ('validation_checkpoint.json', 'validation_final.json'):
            report = json.loads((run / name).read_text(encoding='utf-8'))
            assert all(report['checks'].values()), (name, report['checks'])
            assert report['topology']['nonmanifold'] == defect_count
            assert not report['preservation_errors']
        source = json.loads((run / 'source.json').read_text(encoding='utf-8'))
        candidate = json.loads((run / 'candidate.json').read_text(encoding='utf-8'))
        policy = manifest['preserved_source_nonmanifold']
        assert not preservation_errors(source, candidate['faces'], candidate['vertices'],
                                       candidate['source_to_candidate'], policy)
        names = apply_result(run, include_checkpoint=False)
        output = bpy.data.objects[names[0]]
        assert output.data is not obj.data
        group = output.vertex_groups.get('CAD_Skipped')
        assert group is not None and any(
            any(item.group == group.index for item in vertex.groups)
            for vertex in output.data.vertices)
        assert output.vertex_groups.get('CAD_Review_InvalidBoundary') is None
        assert fingerprint(obj) == before
        print('CAD_NONMANIFOLD_OK', defect_count, manifest['before']['t'],
              manifest['final']['t'], policy['faces'])


only_bad = source_mesh(1)
# Remove the separately generated hole component from a new independent object.
bad_vertices = [tuple(vertex.co) for vertex in only_bad.data.vertices][-6:]
bad_faces = [[vi - (len(only_bad.data.vertices) - 6) for vi in face.vertices]
             for face in list(only_bad.data.polygons)[-8:]]
mesh = bpy.data.meshes.new('CAD NonManifold No Change')
mesh.from_pydata(bad_vertices, [], bad_faces)
mesh.update()
unchanged = bpy.data.objects.new(mesh.name, mesh)
bpy.context.scene.collection.objects.link(unchanged)
before = fingerprint(unchanged)
with tempfile.TemporaryDirectory() as directory:
    run = Path(directory) / 'no_change'
    prepare_selected(run, obj=unchanged, operations=operations, preserve_nonmanifold=True)
    try:
        main(run)
    except ValueError as error:
        assert 'No selected operation produced' in str(error), error
    else:
        raise AssertionError('An unchanged non-manifold mesh produced a false optimized output')
    assert not (run / 'result.blend').exists()
    assert fingerprint(unchanged) == before
    print('CAD_NONMANIFOLD_NO_CHANGE_OK')


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs
try:
    from _bpy_restrict_state import RestrictBlend
except ImportError:
    from bpy_restrict_state import RestrictBlend

with RestrictBlend():
    addon.register()
try:
    good = source_mesh(0)
    bad = source_mesh(1)
    source_hashes = {obj.name: fingerprint(obj) for obj in (good, bad)}
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = 'SELECTED'
    for name, enabled in operations.items():
        setattr(state, name, enabled)
    assert jobs.preflight(bpy.context, state, [good, bad])
    assert not jobs.preflight(bpy.context, state, [good, bad], preserve_nonmanifold=True)
    open_mesh = bpy.data.meshes.new('CAD Open Boundary')
    open_mesh.from_pydata([(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)], [], [[0, 1, 2]])
    open_obj = bpy.data.objects.new(open_mesh.name, open_mesh)
    bpy.context.scene.collection.objects.link(open_obj)
    assert jobs.preflight(bpy.context, state, [open_obj], preserve_nonmanifold=True)
    with tempfile.TemporaryDirectory() as directory:
        batch = jobs.CADBatch(bpy.context, [good, bad], Path(directory),
                              preserve_nonmanifold=True)
        while batch.step():
            time.sleep(.05)
        rows = list(state.results)[-2:]
        assert [row.status for row in rows] == ['PASS', 'REVIEW'], [row.status for row in rows]
        assert all(row.output is not None for row in rows)
        assert all(row.preserve_nonmanifold for row in rows)
        assert rows[1].output.vertex_groups.get('CAD_Skipped') is not None
        assert all(fingerprint(obj) == source_hashes[obj.name] for obj in (good, bad))
        print('CAD_NONMANIFOLD_MIXED_BATCH_OK', [row.status for row in rows])
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    bad.select_set(True)
    bpy.context.view_layer.objects.active = bad
    with tempfile.TemporaryDirectory() as directory:
        state.run_root = directory
        assert bpy.ops.lcw.cad_reconstruct() == {'FINISHED'}
        rejected = state.results[-1]
        assert rejected.status == 'FAIL' and rejected.stage == 'preflight'
        assert rejected.output is None and 'nonmanifold' in rejected.reason.lower()
        assert bpy.ops.lcw.cad_reconstruct(preserve_nonmanifold=True) == {'FINISHED'}
        row = state.results[-1]
        assert row.status == 'REVIEW' and row.preserve_nonmanifold
        assert row.output is not None and row.output.vertex_groups.get('CAD_Skipped')
        assert fingerprint(bad) == source_hashes[bad.name]
        print('CAD_NONMANIFOLD_OPERATOR_OK', row.status)
finally:
    with RestrictBlend():
        addon.unregister()
