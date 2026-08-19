from __future__ import annotations

import sys
import traceback

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon
from LC_workflow_addon.quad_reconstruction import operators
from LC_workflow_addon.quad_reconstruction.reconstruction import SOURCE_NAME_PROPERTY
from LC_workflow_addon.quad_reconstruction.topology_snapshot import snapshot_object


def create_square(collection, name):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        [],
        [(0, 1, 2), (2, 1, 3)],
    )
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def topology_signature(obj):
    return (
        tuple(tuple(edge.vertices) for edge in obj.data.edges),
        tuple(tuple(face.vertices) for face in obj.data.polygons),
    )


try:
    addon.register()
    source = bpy.data.collections.new("AIQ_Phase2_Safety_Source")
    output_parent = bpy.data.collections.new("AIQ_Phase2_Safety_Output")
    bpy.context.scene.collection.children.link(source)
    bpy.context.scene.collection.children.link(output_parent)
    good = create_square(source, "Good")
    fail_after_copy = create_square(source, "FailAfterCopy")
    fingerprints = {
        obj.name: snapshot_object(obj, obj.name).fingerprint
        for obj in (good, fail_after_copy)
    }
    original_object_count = len(bpy.data.objects)
    original_mesh_count = len(bpy.data.meshes)

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source
    state.output_collection = output_parent
    state.profile = "STRICT"
    state.solver_backend = "SEED_AUGMENT"

    original_diagnostics = operators.create_diagnostic_attributes

    def fail_one_output(mesh, candidates, matching):
        if mesh.name.startswith("FailAfterCopyMesh_AIQ"):
            raise RuntimeError("Intentional post-copy rollback fixture.")
        return original_diagnostics(mesh, candidates, matching)

    operators.create_diagnostic_attributes = fail_one_output
    first_result = bpy.ops.lcw.quad_reconstruction_reconstruct()
    operators.create_diagnostic_attributes = original_diagnostics
    assert first_result == {"FINISHED"}
    first_run = state.last_run_collection
    first_outputs = {
        obj.get(SOURCE_NAME_PROPERTY): obj
        for obj in first_run.all_objects
        if obj.get(SOURCE_NAME_PROPERTY)
    }
    assert set(first_outputs) == {"Good"}
    assert len(bpy.data.objects) == original_object_count + 1
    assert len(bpy.data.meshes) == original_mesh_count + 1
    first_signature = topology_signature(first_outputs["Good"])

    second_result = bpy.ops.lcw.quad_reconstruction_reconstruct()
    assert second_result == {"FINISHED"}
    second_outputs = {
        obj.get(SOURCE_NAME_PROPERTY): obj
        for obj in state.last_run_collection.all_objects
        if obj.get(SOURCE_NAME_PROPERTY)
    }
    assert set(second_outputs) == {"Good", "FailAfterCopy"}
    assert topology_signature(second_outputs["Good"]) == first_signature
    for obj in (good, fail_after_copy):
        assert snapshot_object(obj, obj.name).fingerprint == fingerprints[obj.name]
    print("LCW_PHASE2_SAFETY_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    operators.create_diagnostic_attributes = globals().get(
        "original_diagnostics",
        operators.create_diagnostic_attributes,
    )
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
