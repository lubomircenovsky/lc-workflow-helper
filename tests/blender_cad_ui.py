"""Headless CAD UI state, archive and scoped deletion regression."""

import json
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs, run_files, status_overlay
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint


addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = "SELECTED"
    bpy.ops.mesh.primitive_cube_add()
    source = bpy.context.object
    before = fingerprint(source)
    source.color = (0.1, 0.2, 0.3, 1.0)
    output = source.copy()
    output.data = source.data.copy()
    bpy.context.scene.collection.objects.link(output)
    output.color = (0.3, 0.4, 0.5, 1.0)
    output["lcw_cad_run_id"] = "a" * 32
    output["lcw_cad_status"] = "PASS"
    row = state.results.add()
    row.source = source
    row.output = output
    row.status = "PASS"
    area = next(area for screen in bpy.data.screens for area in screen.areas if area.type == "VIEW_3D")
    space = area.spaces.active
    space.shading.type = "SOLID"
    space.shading.color_type = "RANDOM"
    space.shading.wireframe_color_type = "RANDOM"
    original_shading = (space.shading.type, space.shading.color_type,
                        space.shading.wireframe_color_type)
    original_output = tuple(output.color)
    original_source = tuple(source.color)
    status_overlay.show(space, state)
    assert (space.shading.color_type, space.shading.wireframe_color_type) == ("OBJECT", "OBJECT")
    assert all(abs(a - b) < 1e-6 for a, b in zip(output.color, jobs.COLORS["PASS"]))
    assert tuple(source.color) == original_source
    second_space = next(
        area.spaces.active for screen in bpy.data.screens for area in screen.areas
        if area.type == "VIEW_3D" and area.spaces.active.as_pointer() != space.as_pointer()
    )
    second_original = (second_space.shading.type, second_space.shading.color_type,
                       second_space.shading.wireframe_color_type)
    status_overlay.show(second_space, state)
    status_overlay.hide(space)
    assert (space.shading.type, space.shading.color_type,
            space.shading.wireframe_color_type) == original_shading
    assert (second_space.shading.type, second_space.shading.color_type,
            second_space.shading.wireframe_color_type) == second_original
    assert tuple(output.color) == original_output
    assert tuple(source.color) == original_source

    space.shading.type = "MATERIAL"
    status_overlay.show(space, state)
    assert space.shading.type == "SOLID"
    assert space.shading.color_type == "OBJECT"
    status_overlay.clear()
    assert space.shading.type == "MATERIAL"
    assert tuple(output.color) == original_output
    space.shading.type = original_shading[0]
    print("CAD_UI_OVERLAY_RESTORE_OK")

    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    assert bpy.ops.lcw.cad_analyze() == {"FINISHED"}
    assert state.analysis_ready and state.analysis_meshes == 1
    assert state.analysis_blockers == 0
    assert state.analysis_summary.startswith("1 mesh")
    print("CAD_UI_ANALYZE_OK", state.analysis_summary)

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
        root = Path(directory)
        state.run_root = str(root)
        owned = root / ("b" * 32)
        owned.mkdir()
        profile = {"method": "A", "delivery": "EDITABLE_NGONS",
                   "code_hash": "a" * 64, "source_hash": "b" * 64}
        (owned / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (owned / "source.json").write_text(json.dumps({"source_hash": "b" * 64}), encoding="utf-8")
        (owned / "worker.log").write_text("worker evidence", encoding="utf-8")
        foreign = root / ("c" * 32)
        foreign.mkdir()
        (foreign / "keep.txt").write_text("not CAD data", encoding="utf-8")
        assert run_files.find_owned_runs(root) == [owned]
        try:
            run_files.delete_owned_run(root, foreign)
        except ValueError:
            pass
        else:
            raise AssertionError("Foreign directory accepted for deletion")
        row.run_dir = str(owned)
        assert bpy.ops.lcw.cad_delete_run_files() == {"FINISHED"}
        assert not owned.exists() and foreign.is_dir()
        assert state.results[0].files_deleted
        assert output.name in bpy.data.objects and output.data.name in bpy.data.meshes
        assert fingerprint(source) == before
        print("CAD_UI_SCOPED_DELETE_OK")

        record = jobs._result_record(
            state, source, owned, "PASS", output=output, row_index=0,
            manifest={"operation_results": {"curves_reduced": 2,
                                             "perimeter_loops_created": 1,
                                             "planar_edges_removed": 3,
                                             "perimeter_direct_joins": 0,
                                             "perimeter_skipped": 0,
                                             "ngons_before": 0,
                                             "ngons_after": 1}},
        )
        assert record.metrics_summary == "2 curves reduced | 1 loops made | 3 flat edges removed"
        del output["lcw_cad_status"]
        status_overlay.show(space, state)
        assert bpy.ops.lcw.cad_archive_results() == {"FINISHED"}
        assert not status_overlay.is_enabled(space)
        assert (space.shading.type, space.shading.color_type,
                space.shading.wireframe_color_type) == original_shading
        assert tuple(output.color) == original_output
        assert not state.results
        archive = next(text for text in bpy.data.texts if text.name.startswith("CAD Results "))
        assert "Mesh ready" in archive.as_string()
        assert output.name in bpy.data.objects and foreign.is_dir()
        assert output["lcw_cad_status"] == "PASS"
        status_overlay.show(space, state)
        assert all(abs(a - b) < 1e-6 for a, b in zip(output.color, jobs.COLORS["PASS"]))
        status_overlay.hide(space)
        assert tuple(output.color) == original_output
        print("CAD_UI_ARCHIVE_OK")

        restored = state.results.add()
        restored.source = source
        restored.status = "FAIL"
        assert bpy.ops.lcw.cad_clear_results() == {"FINISHED"}
        assert not state.results
        assert output.name in bpy.data.objects
        print("CAD_UI_CLEAR_OK")
    status_overlay.show(space, state)
    assert status_overlay.is_enabled(space)
finally:
    addon.unregister()
    assert not status_overlay.is_enabled(space)
    assert (space.shading.type, space.shading.color_type,
            space.shading.wireframe_color_type) == original_shading
    print("CAD_UI_UNREGISTER_OK")
