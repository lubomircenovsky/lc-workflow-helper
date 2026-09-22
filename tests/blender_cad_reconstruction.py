"""Run headless with: blender --background --factory-startup --python tests/blender_cad_reconstruction.py"""
from __future__ import annotations

import sys
import tempfile
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
try:
    from _bpy_restrict_state import RestrictBlend
except ImportError:
    from bpy_restrict_state import RestrictBlend

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs, status_overlay
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint
from LC_workflow_addon.cad_mesh_tool.api import code_hash
from LC_workflow_addon.cad_mesh_tool.straight_walls import normal_chord_limit, settings


def world_center(obj):
    local_center = sum((vertex.co for vertex in obj.data.vertices), Vector((0, 0, 0)))
    return obj.matrix_world @ (local_center / len(obj.data.vertices))


with RestrictBlend():
    addon.register()
try:
    bpy.ops.mesh.primitive_cube_add(location=(3.5, -2.0, 1.0))
    cube = bpy.context.object
    before = fingerprint(cube)
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = "SELECTED"
    space = next(
        area.spaces.active for screen in bpy.data.screens for area in screen.areas
        if area.type == "VIEW_3D"
    )
    shading_before = (space.shading.color_type, space.shading.wireframe_color_type)
    status_overlay.show(space)
    assert status_overlay.is_enabled(space)
    assert (space.shading.color_type, space.shading.wireframe_color_type) == shading_before
    status_overlay.hide(space)
    assert not status_overlay.is_enabled(space)
    assert (space.shading.color_type, space.shading.wireframe_color_type) == shading_before
    assert jobs.sources(bpy.context, state) == [cube]
    assert not jobs.preflight(bpy.context, state, [cube])
    assert bpy.ops.lcw.cad_analyze() == {"FINISHED"}
    assert "1 mesh" in state.analysis_summary
    assert settings({"normal_limit_deg": 1.0})["normal_limit_deg"] == 1.0
    assert normal_chord_limit(360.0) == normal_chord_limit(180.0) == 2.0
    for invalid in (float("nan"), float("inf"), 0.0, -1.0):
        try:
            settings({"normal_limit_deg": invalid})
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted invalid normal limit: {invalid}")
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
        state.run_root = root
        result = bpy.ops.lcw.cad_reconstruct()
        assert result == {"FINISHED"}, result
        assert len(state.results) == 1
        row = state.results[0]
        assert row.status in {"PASS", "REVIEW", "FAIL"}
        assert Path(row.run_dir, "worker.log").exists()
        assert fingerprint(cube) == before
        assert not any(obj.get("cad_checkpoint") for obj in bpy.data.objects)
        assert row.status == "FAIL" or row.output is not None
        assert row.status != "FAIL" or row.output is None
        if row.output:
            assert row.output.data is not cube.data
            assert row.output.name.endswith("_CAD_REVIEW") or row.output.name.endswith("_CAD_PASS")
            assert all(abs(a - b) < 1e-6 for a, b in zip(row.output.color, jobs.COLORS[row.status]))
            assert tuple(row.output.users_collection) == tuple(cube.users_collection)
            assert [obj for obj, _color in status_overlay._status_objects(state)] == [row.output]
            assert (world_center(cube) - world_center(row.output)).length < 0.1
        assert bpy.data.filepath == ""
        print("CAD_SELECTED_SMOKE", row.status, row.stage, row.reason[:100])

    input_collection = bpy.data.collections.new("CAD Input")
    bpy.context.scene.collection.children.link(input_collection)
    input_collection.objects.link(cube)
    output_collection = bpy.data.collections.new("CAD Output")
    bpy.context.scene.collection.children.link(output_collection)
    state.mode = "COLLECTION"
    state.input_collection = input_collection
    state.output_collection = output_collection
    child = bpy.data.collections.new("CAD Input Child")
    input_collection.children.link(child)
    child.objects.link(cube)
    assert jobs.sources(bpy.context, state) == [cube]
    assert not jobs.preflight(bpy.context, state, [cube])
    fail = jobs._destination(state, cube, "FAIL")[0]
    assert fail.name == "FAIL"
    assert fail in state.bindings[0].branch.children.values()
    assert fingerprint(cube) == before
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
        state.run_root = root
        assert bpy.ops.lcw.cad_reconstruct() == {"FINISHED"}
        collection_row = state.results[-1]
        assert collection_row.status in {"PASS", "REVIEW", "FAIL"}
        if collection_row.output:
            assert collection_row.output in state.bindings[0].branch.children[collection_row.status].objects.values()
            assert collection_row.output.data is not cube.data
        assert fingerprint(cube) == before
        assert not any(obj.get("cad_checkpoint") for obj in bpy.data.objects)
        print("CAD_COLLECTION_RESULT", collection_row.status)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
        run_dir = Path(root) / "synthetic_pass"
        run_dir.mkdir()
        parent = bpy.data.objects.new("CAD Test Parent", None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = (7.0, -4.0, 3.0)
        parent.rotation_euler.z = 0.35
        world = Matrix.Translation((3.0, 5.0, 1.0)) @ cube.matrix_world.copy()
        cube.parent = parent
        cube.matrix_world = world
        bpy.context.view_layer.update()
        before = fingerprint(cube)
        mesh = cube.data.copy()
        mock = bpy.data.objects.new("CAD_Optimized", mesh)
        mock["cad_checkpoint"] = False
        mock.matrix_world = cube.matrix_world.copy()
        mock_matrix = mock.matrix_world.copy()
        artifact = run_dir / "result.blend"
        bpy.data.libraries.write(str(artifact), {mock}, fake_user=True)
        bpy.data.objects.remove(mock, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        (run_dir / "profile.json").write_text(json.dumps({
            "code_hash": code_hash(), "source_name": cube.name,
            "source_hash": before, "unit_scale": bpy.context.scene.unit_settings.scale_length,
        }), encoding="utf-8")
        (run_dir / "manifest.json").write_text(json.dumps({
            "geometry_status": "PASS", "coverage_status": "REQUIRES_REVIEW",
            "objects": ["CAD_Optimized"],
            "result_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "result_matrix_world": [list(matrix_row) for matrix_row in mock_matrix],
        }), encoding="utf-8")
        output = jobs._import_result(state, cube, run_dir, "PASS")
        bpy.context.view_layer.update()
        assert output.name.endswith("_CAD_PASS")
        assert output in state.bindings[0].branch.children["PASS"].objects.values()
        assert output.data is not cube.data
        assert output.parent == parent
        assert all(abs(a - b) < 1e-6 for row_a, row_b in zip(output.matrix_world, cube.matrix_world) for a, b in zip(row_a, row_b))
        assert max(
            (output.matrix_world @ output_vertex.co - cube.matrix_world @ source_vertex.co).length
            for output_vertex, source_vertex in zip(output.data.vertices, cube.data.vertices)
        ) < 1e-5
        assert fingerprint(cube) == before
        assert not any(obj.get("cad_checkpoint") for obj in bpy.data.objects)
        print("CAD_PASS_IMPORT_OK")
    print("CAD_COLLECTION_SMOKE_OK")
    second_input = bpy.data.collections.new("CAD Input 2")
    bpy.context.scene.collection.children.link(second_input)
    second_input.objects.link(cube)
    state.input_collection = second_input
    assert jobs._destination(state, cube, "FAIL")[0] not in state.bindings[0].branch.children.values()
    assert len(state.bindings) == 2
    bpy.ops.mesh.primitive_cube_add(location=(4, 0, 0))
    singular = bpy.context.object
    bpy.context.view_layer.update()
    singular_before = fingerprint(singular)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    cube.select_set(True)
    singular.select_set(True)
    state.mode = "SELECTED"
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
        state.run_root = root
        count = len(state.results)
        original_prepare = jobs.prepare_selected

        def prepare_with_one_failure(*args, **kwargs):
            if kwargs.get("obj") == singular:
                raise ValueError("Synthetic per-object prepare failure")
            return original_prepare(*args, **kwargs)

        jobs.prepare_selected = prepare_with_one_failure
        try:
            assert bpy.ops.lcw.cad_reconstruct() == {"FINISHED"}
        finally:
            jobs.prepare_selected = original_prepare
        new_rows = list(state.results)[count:]
        assert len(new_rows) == 2
        failed = next(row for row in new_rows if row.source == singular)
        assert failed.status == "FAIL" and failed.output is None
        assert failed.stage == "prepare"
        assert next(row for row in new_rows if row.source == cube).status in {"PASS", "REVIEW"}
        assert fingerprint(singular) == singular_before
        assert fingerprint(cube) == before
        print("CAD_BATCH_FAILURE_ISOLATION_OK")
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as root:
        count = len(state.results)
        batch = jobs.CADBatch(bpy.context, [cube], Path(root))
        assert batch.step()
        batch.cancel()
        assert batch.cancelled
        assert batch.process.poll() is not None
        assert not batch.step()
        assert len(state.results) == count
        assert fingerprint(cube) == before
        print("CAD_CANCEL_OK")
finally:
    with RestrictBlend():
        addon.unregister()
    print("CAD_UNREGISTER_OK")
