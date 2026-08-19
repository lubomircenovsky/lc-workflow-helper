from __future__ import annotations

import sys
import traceback
import json

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon


def create_object(collection, name, vertices, faces):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            uv_layer.data[loop_index].uv = (vertex.co.x, vertex.co.y)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


try:
    addon.register()
    source = bpy.data.collections.new("AIQ_Phase1_Source")
    bpy.context.scene.collection.children.link(source)
    nested_source = bpy.data.collections.new("AIQ_Phase1_Nested")
    source.children.link(nested_source)
    open_grid = create_object(
        source,
        "OpenGrid",
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        [(0, 1, 2), (2, 1, 3)],
    )
    material = bpy.data.materials.new("Phase1Material")
    open_grid.data.materials.append(material)
    color = open_grid.data.color_attributes.new(
        name="Phase1Color",
        type="BYTE_COLOR",
        domain="CORNER",
    )
    for item in color.data:
        item.color_srgb = (0.25, 0.5, 0.75, 1.0)
    open_grid.modifiers.new(name="UnappliedMirror", type="MIRROR")
    mixed = create_object(
        source,
        "Mixed",
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (2, 0, 0), (3, 0, 0), (3, 1, 0), (2, 1, 0)],
        [(0, 1, 2), (3, 4, 5, 6)],
    )
    non_manifold = create_object(
        nested_source,
        "NonManifold",
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)],
        [(0, 1, 2), (1, 0, 3), (0, 1, 4)],
    )
    mixed.parent = open_grid
    source_objects = (open_grid, mixed, non_manifold)
    source_facts = {
        obj.name: (
            len(obj.data.vertices),
            len(obj.data.edges),
            len(obj.data.polygons),
            tuple(tuple(vertex.co) for vertex in obj.data.vertices),
        )
        for obj in source_objects
    }
    object_count = len(bpy.data.objects)
    mesh_count = len(bpy.data.meshes)

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source
    result = bpy.ops.lcw.quad_reconstruction_analyze()
    assert result == {"FINISHED"}
    assert len(state.results) == 3
    assert all(item.fingerprint_unchanged for item in state.results)
    classifications = {item.source_object_name: item.classification for item in state.results}
    assert classifications["OpenGrid"] == "OPEN_TRIANGULATED"
    assert classifications["Mixed"] == "MIXED_TRI_QUAD"
    assert classifications["NonManifold"] == "TRUE_NON_MANIFOLD"
    assert len(bpy.data.objects) == object_count
    assert len(bpy.data.meshes) == mesh_count
    report_text = bpy.data.texts.get(state.last_report_text_name)
    assert report_text is not None
    report = json.loads(report_text.as_string())
    assert report["metadata"]["mesh_outputs_created"] == "false"
    assert len(report["objects"]) == 3
    assert all(len(item["baselines"]) == 3 for item in report["objects"])
    open_grid_report = next(
        item for item in report["objects"] if item["source_object_name"] == "OpenGrid"
    )
    assert "Phase1Color" in open_grid_report["audit"]["attribute_names"]
    assert "MIRROR" in open_grid_report["audit"]["modifier_types"]
    for obj in source_objects:
        current = (
            len(obj.data.vertices),
            len(obj.data.edges),
            len(obj.data.polygons),
            tuple(tuple(vertex.co) for vertex in obj.data.vertices),
        )
        assert current == source_facts[obj.name]
    print("LCW_PHASE1_ANALYSIS_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
