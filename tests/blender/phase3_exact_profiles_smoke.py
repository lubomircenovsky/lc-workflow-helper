from __future__ import annotations

import json
import sys
import traceback

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon
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


def shared_edge(mesh):
    return next(edge for edge in mesh.edges if set(edge.vertices) == {1, 2})


def outputs_for(state):
    return {
        obj.get(SOURCE_NAME_PROPERTY): obj
        for obj in state.last_run_collection.all_objects
        if obj.get(SOURCE_NAME_PROPERTY)
    }


try:
    addon.register()
    source = bpy.data.collections.new("AIQ_Phase3_Source")
    output_parent = bpy.data.collections.new("AIQ_Phase3_Output")
    bpy.context.scene.collection.children.link(source)
    bpy.context.scene.collection.children.link(output_parent)
    clean = create_square(source, "Clean")
    seam = create_square(source, "Seam")
    shared_edge(seam.data).use_seam = True
    material = create_square(source, "Material")
    material.data.materials.append(bpy.data.materials.new("Phase3MatA"))
    material.data.materials.append(bpy.data.materials.new("Phase3MatB"))
    material.data.polygons[0].material_index = 0
    material.data.polygons[1].material_index = 1
    sources = (clean, seam, material)
    fingerprints = {
        obj.name: snapshot_object(obj, obj.name).fingerprint for obj in sources
    }

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source
    state.output_collection = output_parent
    state.solver_backend = "EXACT_BLOSSOM"
    state.profile = "STRICT"
    assert state.protect_materials
    assert state.protect_uv
    assert state.protect_seams
    assert state.protect_sharp_edges
    # Strict invariants remain hard even if a file/script carries stale toggles.
    state.protect_materials = False
    state.protect_uv = False
    state.protect_seams = False
    state.protect_sharp_edges = False
    assert bpy.ops.lcw.quad_reconstruction_reconstruct() == {"FINISHED"}
    strict_outputs = outputs_for(state)
    assert len(strict_outputs["Clean"].data.polygons) == 1
    assert len(strict_outputs["Seam"].data.polygons) == 2
    assert len(strict_outputs["Material"].data.polygons) == 2
    clean_result = next(item for item in state.results if item.source_object_name == "Clean")
    assert clean_result.solver_exact
    assert clean_result.solver_backend == "EXACT_BLOSSOM"
    assert clean_result.confidence_label == "HIGH"
    assert clean_result.confidence_score >= 80.0
    assert strict_outputs["Clean"]["lcw_aiq_solver_exact"]
    assert strict_outputs["Clean"]["lcw_aiq_confidence_label"] == "HIGH"
    assert strict_outputs["Clean"].get("lcw_aiq_settings_hash")
    seam_strict_result = next(
        item for item in state.results if item.source_object_name == "Seam"
    )
    assert seam_strict_result.confidence_label == "LOW"
    assert all(
        item.value
        for item in strict_outputs["Seam"].data.attributes["AIQ_LowConfidence"].data
    )
    strict_report = json.loads(bpy.data.texts[state.last_report_text_name].as_string())
    assert all("confidence" in item for item in strict_report["objects"] if item["status"] == "RECONSTRUCTED")

    state.profile = "BALANCED"
    assert state.protect_materials
    assert not state.protect_uv
    assert not state.protect_seams
    assert not state.protect_sharp_edges
    assert bpy.ops.lcw.quad_reconstruction_reconstruct() == {"FINISHED"}
    balanced_outputs = outputs_for(state)
    assert len(balanced_outputs["Clean"].data.polygons) == 1
    assert len(balanced_outputs["Seam"].data.polygons) == 1
    assert len(balanced_outputs["Material"].data.polygons) == 2
    seam_relaxed = balanced_outputs["Seam"].data.attributes["AIQ_SeamRelaxed"]
    assert any(item.value for item in seam_relaxed.data)
    seam_result = next(item for item in state.results if item.source_object_name == "Seam")
    assert seam_result.relaxation_count >= 1
    assert seam_result.solver_exact

    state.profile = "AGGRESSIVE"
    assert not state.protect_materials
    assert bpy.ops.lcw.quad_reconstruction_reconstruct() == {"FINISHED"}
    aggressive_outputs = outputs_for(state)
    assert len(aggressive_outputs["Material"].data.polygons) == 1
    material_relaxed = aggressive_outputs["Material"].data.attributes[
        "AIQ_MaterialRelaxed"
    ]
    assert any(item.value for item in material_relaxed.data)
    assert aggressive_outputs["Material"]["lcw_aiq_relaxation_flags"] == "MATERIAL"
    aggressive_report = json.loads(
        bpy.data.texts[state.last_report_text_name].as_string()
    )
    material_report = next(
        item for item in aggressive_report["objects"] if item["source_object_name"] == "Material"
    )
    assert material_report["relaxation_flags"] == ["MATERIAL"]
    for obj in sources:
        assert snapshot_object(obj, obj.name).fingerprint == fingerprints[obj.name]
    print("LCW_PHASE3_EXACT_PROFILES_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
