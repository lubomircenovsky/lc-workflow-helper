"""Select Problem Areas: stored intersections and open topology in Edit Mode.

blender --background --factory-startup --python tests/blender_cad_problem_select.py
"""
import json
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_mesh_tool.mesh_io import capture, fingerprint
from cad_mesh_tool.worker import source_intersections_report


def joined_cubes():
    """Cubes A and B overlap (their faces cross); cube C is far away."""
    for location in ((0, 0, 0), (0.5, 0.5, 0.5), (10, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(location=location)
    for obj in bpy.context.scene.objects:
        obj.select_set(obj.type == 'MESH')
    bpy.ops.object.join()
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def selected_faces(obj):
    return sorted(face.index for face in bmesh.from_edit_mesh(obj.data).faces if face.select)


def add_result(state, source, stage, run_dir=''):
    row = state.results.add()
    row.source, row.status, row.stage, row.run_dir = source, 'FAIL', stage, run_dir
    return len(state.results) - 1


addon.register()
try:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    state = bpy.context.scene.lcw_cad_reconstruction
    obj = joined_cubes()
    source = capture(obj)
    report = source_intersections_report(source)
    assert report['intersections'], 'fixture must contain crossing faces'
    # Independent expectation: Blender's own triangle -> polygon map.
    obj.data.calc_loop_triangles()
    owner = [t.polygon_index for t in obj.data.loop_triangles]
    expected = sorted({owner[pair[key]] for pair in report['intersections'] for key in ('a', 'b')})
    far_cube = {polygon.index for polygon in obj.data.polygons if (obj.matrix_world @ polygon.center).x > 5}
    assert len(far_cube) == 6
    assert expected and not far_cube & set(expected)

    with tempfile.TemporaryDirectory() as directory:
        run = Path(directory)
        (run / 'source.json').write_text(json.dumps(source), encoding='utf-8')
        (run / 'validation_source.json').write_text(json.dumps(report), encoding='utf-8')
        index = add_result(state, obj, 'source_geometry', str(run))
        before = fingerprint(obj)
        assert bpy.ops.lcw.cad_select_problems(result_index=index) == {'FINISHED'}
        assert bpy.context.mode == 'EDIT_MESH'
        assert selected_faces(obj) == expected, (selected_faces(obj), expected)
        bpy.ops.object.mode_set(mode='OBJECT')
        assert fingerprint(obj) == before, 'selecting must not change the mesh'

        # A changed source no longer matches the stored indices.
        obj.data.vertices[0].co.x += 0.01
        assert bpy.ops.lcw.cad_select_problems(result_index=index) == {'CANCELLED'}
        obj.data.vertices[0].co.x -= 0.01
        (run / 'validation_source.json').unlink()
        assert bpy.ops.lcw.cad_select_problems(result_index=index) == {'CANCELLED'}

    # Open topology: a cube without one face has four boundary edges.
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cube_add(location=(0, 20, 0))
    open_cube = bpy.context.object
    bm = bmesh.new()
    bm.from_mesh(open_cube.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[0]], context='FACES_ONLY')
    bm.to_mesh(open_cube.data)
    bm.free()
    index = add_result(state, open_cube, 'preflight')
    assert bpy.ops.lcw.cad_select_problems(result_index=index) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(open_cube.data)
    assert sum(edge.select for edge in bm.edges) == 4
    bpy.ops.object.mode_set(mode='OBJECT')

    # Rows without a selectable cause are refused.
    index = add_result(state, open_cube, 'worker')
    assert bpy.ops.lcw.cad_select_problems(result_index=index) == {'CANCELLED'}
    print('PASS blender_cad_problem_select')
finally:
    addon.unregister()
