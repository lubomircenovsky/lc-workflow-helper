from __future__ import annotations

import json
import sys
import traceback

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon
from LC_workflow_addon.quad_reconstruction.cache import PREPARATION_CACHE
from LC_workflow_addon.quad_reconstruction.topology_snapshot import snapshot_object
from LC_workflow_addon.quad_reconstruction.validation import (
    measure_surface_deviation,
    validate_existing_output,
)


def create_surface(collection, name, *, quad=False, warp=0.0):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, warp)]
    faces = [(0, 1, 3, 2)] if quad else [(0, 1, 2), (2, 1, 3)]
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


try:
    addon.register()
    source_collection = bpy.data.collections.new("AIQ_Phase5_Source")
    output_collection = bpy.data.collections.new("AIQ_Phase5_Output")
    bpy.context.scene.collection.children.link(source_collection)
    bpy.context.scene.collection.children.link(output_collection)
    source = create_surface(source_collection, "Phase5Source")
    source_fingerprint = snapshot_object(source, "phase5").fingerprint

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source_collection
    state.output_collection = output_collection
    state.profile = "STRICT"
    state.solver_backend = "EXACT_BLOSSOM"
    state.run_subdivision_validation = True
    PREPARATION_CACHE.clear()

    assert bpy.ops.lcw.quad_reconstruction_reconstruct_modal() == {"FINISHED"}
    assert state.job_status == "RECONSTRUCTED"
    result = state.results[0]
    output = result.output_object
    payload = json.loads(bpy.data.texts[state.last_report_text_name].as_string())
    validation_payload = payload["objects"][0]["validation"]
    assert validation_payload["surface_deviation"]["maximum"] <= 1e-7
    assert validation_payload["subdivision"]["ran"]
    assert validation_payload["subdivision"]["passed"]
    assert dict(payload["objects"][0]["phase_timings"])["validation"] >= 0.0

    object_count = len(bpy.data.objects)
    mesh_count = len(bpy.data.meshes)
    validation = validate_existing_output(source, output, run_subdivision=True)
    assert validation.valid
    assert validation.surface_deviation.maximum <= 1e-7
    assert validation.subdivision.passed
    assert len(bpy.data.objects) == object_count
    assert len(bpy.data.meshes) == mesh_count

    warped_tri = create_surface(source_collection, "WarpedTri", warp=0.05)
    warped_quad = create_surface(output_collection, "WarpedQuad", quad=True, warp=0.05)
    deviation = measure_surface_deviation(
        snapshot_object(warped_tri, "warped"),
        snapshot_object(warped_quad, "warped"),
    )
    assert deviation.sample_count > 0
    assert deviation.maximum > 1e-5
    bpy.data.objects.remove(warped_tri, do_unlink=True)
    bpy.data.objects.remove(warped_quad, do_unlink=True)

    first_hits = PREPARATION_CACHE.info()["hits"]
    assert bpy.ops.lcw.quad_reconstruction_clear_results() == {"FINISHED"}
    assert bpy.ops.lcw.quad_reconstruction_reconstruct_modal() == {"FINISHED"}
    assert PREPARATION_CACHE.info()["hits"] > first_hits
    assert snapshot_object(source, "phase5").fingerprint == source_fingerprint
    assert bpy.ops.lcw.quad_reconstruction_clear_results() == {"FINISHED"}
    print("LCW_PHASE5_VALIDATION_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
