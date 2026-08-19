from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon
from LC_workflow_addon.quad_reconstruction.jobs import AnalysisJob, ReconstructionJob
from LC_workflow_addon.quad_reconstruction.operators import (
    _effective_protections,
    _settings_payload,
)
from LC_workflow_addon.quad_reconstruction.reconstruction import GENERATED_MARKER
from LC_workflow_addon.quad_reconstruction.topology_snapshot import snapshot_object


def create_square(collection, name, offset=0.0):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(
        [
            (offset + 0, 0, 0),
            (offset + 1, 0, 0),
            (offset + 0, 1, 0),
            (offset + 1, 1, 0),
        ],
        [],
        [(0, 1, 2), (2, 1, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


try:
    addon.register()
    source = bpy.data.collections.new("AIQ_Phase4_Source")
    output_parent = bpy.data.collections.new("AIQ_Phase4_Output")
    bpy.context.scene.collection.children.link(source)
    bpy.context.scene.collection.children.link(output_parent)
    clean = create_square(source, "Phase4Clean")
    seam = create_square(source, "Phase4Seam", 2.0)
    next(edge for edge in seam.data.edges if set(edge.vertices) == {1, 2}).use_seam = True
    fingerprints = {
        obj.name: snapshot_object(obj, obj.name).fingerprint for obj in (clean, seam)
    }
    base_object_count = len(bpy.data.objects)
    base_mesh_count = len(bpy.data.meshes)

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source
    state.output_collection = output_parent
    state.profile = "STRICT"
    state.solver_backend = "EXACT_BLOSSOM"

    assert bpy.ops.lcw.quad_reconstruction_analyze_modal() == {"FINISHED"}
    assert state.job_status == "ANALYZED"
    assert len(state.results) == 2
    assert all(item.status == "ANALYZED" for item in state.results)
    assert len(bpy.data.objects) == base_object_count
    assert len(bpy.data.meshes) == base_mesh_count

    analysis_job = AnalysisJob(
        state,
        settings_payload=_settings_payload(state),
        protections=_effective_protections(state),
    )
    analysis_job.start()
    analysis_job.step()
    assert bpy.ops.lcw.quad_reconstruction_cancel() == {"FINISHED"}
    assert analysis_job.step() == "CANCELLED"
    assert state.job_status == "CANCELLED"
    assert not state.active_run_id
    assert len(bpy.data.objects) == base_object_count
    assert len(bpy.data.meshes) == base_mesh_count

    job = ReconstructionJob(
        bpy.context.scene,
        state,
        settings_payload=_settings_payload(state),
        protections=_effective_protections(state),
    )
    job.start()
    observed_labels = []
    step_count = 0
    while job.stage not in {"DONE", "FAILED", "CANCELLED"}:
        job.step()
        observed_labels.append(state.progress_label)
        step_count += 1
        assert step_count < 100
    assert job.stage == "DONE"
    assert step_count > len((clean, seam))
    assert any("region" in label.lower() for label in observed_labels)
    assert state.job_status == "RECONSTRUCTED"
    assert state.progress == 1.0
    assert len(state.last_run_collection.all_objects) == 2
    assert bpy.ops.lcw.quad_reconstruction_validate_outputs() == {"FINISHED"}
    assert all(item.validation_passed for item in state.results if item.output_object)
    validation_payload = json.loads(
        bpy.data.texts[state.last_report_text_name].as_string()
    )
    assert validation_payload["mode"] == "VALIDATE_OUTPUTS"

    report_path = Path(__file__).with_name("_phase4-report.json")
    try:
        assert bpy.ops.lcw.quad_reconstruction_export_report(
            filepath=str(report_path)
        ) == {"FINISHED"}
        assert json.loads(report_path.read_text(encoding="utf-8"))["mode"] == "VALIDATE_OUTPUTS"
    finally:
        report_path.unlink(missing_ok=True)

    seam_index = next(
        index
        for index, item in enumerate(state.results)
        if item.source_object_name == "Phase4Seam"
    )
    state.active_result_index = seam_index
    assert bpy.ops.lcw.quad_reconstruction_focus_output() == {"FINISHED"}
    assert bpy.context.active_object == state.results[seam_index].output_object
    assert bpy.ops.lcw.quad_reconstruction_select_problem_faces() == {"FINISHED"}
    assert bpy.context.active_object.mode == "EDIT"
    assert sum(face.select for face in bpy.context.active_object.data.polygons) == 2
    bpy.ops.object.mode_set(mode="OBJECT")

    assert bpy.ops.lcw.quad_reconstruction_clear_results() == {"FINISHED"}
    assert state.last_run_collection is None
    assert not state.results
    assert len(bpy.data.objects) == base_object_count
    assert len(bpy.data.meshes) == base_mesh_count

    assert bpy.ops.lcw.quad_reconstruction_reconstruct_modal() == {"FINISHED"}
    assert state.job_status == "RECONSTRUCTED"
    assert len(state.last_run_collection.all_objects) == 2
    assert bpy.ops.lcw.quad_reconstruction_clear_results() == {"FINISHED"}

    cancel_job = ReconstructionJob(
        bpy.context.scene,
        state,
        settings_payload=_settings_payload(state),
        protections=_effective_protections(state),
    )
    cancel_job.start()
    cancel_job.step()  # prepare first object
    cancel_job.step()  # match its first region
    cancel_job.step()  # apply and link a partial output
    assert len(bpy.data.objects) > base_object_count
    assert bpy.ops.lcw.quad_reconstruction_cancel() == {"FINISHED"}
    assert cancel_job.step() == "CANCELLED"
    assert state.job_status == "CANCELLED"
    assert state.last_run_collection is None
    assert len(bpy.data.objects) == base_object_count
    assert len(bpy.data.meshes) == base_mesh_count
    assert not any(obj.get(GENERATED_MARKER) for obj in bpy.data.objects)
    for obj in (clean, seam):
        assert snapshot_object(obj, obj.name).fingerprint == fingerprints[obj.name]
    print("LCW_PHASE4_JOB_UI_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
