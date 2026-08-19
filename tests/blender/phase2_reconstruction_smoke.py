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


def shared_edge(mesh, vertices):
    return next(edge for edge in mesh.edges if set(edge.vertices) == set(vertices))


try:
    addon.register()
    source = bpy.data.collections.new("AIQ_Phase2_Source")
    output_parent = bpy.data.collections.new("AIQ_Phase2_Output")
    bpy.context.scene.collection.children.link(source)
    bpy.context.scene.collection.children.link(output_parent)
    nested = bpy.data.collections.new("Nested")
    source.children.link(nested)

    square_vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]
    square_faces = [(0, 1, 2), (2, 1, 3)]
    grid = create_object(source, "Grid", square_vertices, square_faces)
    uv_seam = create_object(source, "UVSeam", square_vertices, square_faces)
    shared_edge(uv_seam.data, (1, 2)).use_seam = True
    material_boundary = create_object(source, "MaterialBoundary", square_vertices, square_faces)
    material_boundary.data.materials.append(bpy.data.materials.new("MatA"))
    material_boundary.data.materials.append(bpy.data.materials.new("MatB"))
    material_boundary.data.polygons[0].material_index = 0
    material_boundary.data.polygons[1].material_index = 1
    mixed = create_object(
        nested,
        "MixedOutput",
        [
            (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
            (2, 0, 0), (3, 0, 0), (2, 1, 0), (3, 1, 0),
        ],
        [(0, 1, 2, 3), (4, 5, 6), (6, 5, 7)],
    )
    non_manifold = create_object(
        source,
        "NonManifoldOutput",
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)],
        [(0, 1, 2), (1, 0, 3), (0, 1, 4)],
    )
    degenerate = create_object(
        source,
        "DegenerateOutput",
        [(0, 0, 0), (1, 0, 0), (2, 0, 0)],
        [(0, 1, 2)],
    )
    mixed.parent = grid
    mixed.matrix_world.translation = (2.0, 3.0, 4.0)
    color = grid.data.color_attributes.new(
        name="ProductionColor",
        type="BYTE_COLOR",
        domain="CORNER",
    )
    for item in color.data:
        item.color_srgb = (0.2, 0.4, 0.6, 1.0)

    source_objects = (grid, uv_seam, material_boundary, mixed, non_manifold, degenerate)
    before = {
        obj.name: snapshot_object(obj, f"test-{index}").fingerprint
        for index, obj in enumerate(source_objects)
    }
    source_object_count = len(bpy.data.objects)
    source_mesh_count = len(bpy.data.meshes)

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source
    state.output_collection = output_parent
    state.profile = "STRICT"
    state.solver_backend = "SEED_AUGMENT"
    state.debug_logging = False
    result = bpy.ops.lcw.quad_reconstruction_reconstruct()
    assert result == {"FINISHED"}
    if state.job_status != "RECONSTRUCTED":
        print("PHASE2_FAILURES", [(item.source_object_name, item.details) for item in state.results])
    assert state.job_status == "RECONSTRUCTED"
    assert state.last_run_collection is not None
    outputs = {
        obj.get(SOURCE_NAME_PROPERTY): obj
        for obj in state.last_run_collection.all_objects
        if obj.get(SOURCE_NAME_PROPERTY)
    }
    if "DegenerateOutput" not in outputs:
        print(
            "PHASE2_DEGENERATE_FAILURE",
            [(item.source_object_name, item.status, item.details) for item in state.results],
        )
    assert set(outputs) == {
        "Grid",
        "UVSeam",
        "MaterialBoundary",
        "MixedOutput",
        "NonManifoldOutput",
        "DegenerateOutput",
    }
    assert outputs["Grid"].data != grid.data
    assert [len(face.vertices) for face in outputs["Grid"].data.polygons] == [4]
    assert {
        tuple(sorted(edge.vertices)) for edge in outputs["Grid"].data.edges
    } == {(0, 1), (0, 2), (1, 3), (2, 3)}
    assert sum(len(face.vertices) == 3 for face in outputs["UVSeam"].data.polygons) == 2
    assert all(
        item.value
        for item in outputs["UVSeam"].data.attributes["AIQ_UnresolvedTriangle"].data
    )
    assert sum(len(face.vertices) == 3 for face in outputs["MaterialBoundary"].data.polygons) == 2
    assert sum(len(face.vertices) == 4 for face in outputs["MixedOutput"].data.polygons) == 2
    nm_edge = shared_edge(outputs["NonManifoldOutput"].data, (0, 1))
    incident_faces = sum(
        1
        for polygon in outputs["NonManifoldOutput"].data.polygons
        if set(nm_edge.vertices).issubset(polygon.vertices)
    )
    assert incident_faces == 3
    assert len(outputs["DegenerateOutput"].data.polygons) == 1
    assert outputs["DegenerateOutput"].data.polygons[0].area == 0.0
    assert outputs["DegenerateOutput"].data.attributes[
        "AIQ_UnresolvedTriangle"
    ].data[0].value
    assert outputs["MixedOutput"].parent == outputs["Grid"]
    assert tuple(outputs["MixedOutput"].matrix_world.translation) == (2.0, 3.0, 4.0)
    assert outputs["Grid"].data.color_attributes.get("ProductionColor") is not None
    assert outputs["Grid"].data.uv_layers.get("UVMap") is not None
    for name in (
        "AIQ_UnresolvedTriangle",
        "AIQ_LowConfidence",
        "AIQ_UVRelaxed",
        "AIQ_SeamRelaxed",
        "AIQ_SharpRelaxed",
        "AIQ_MaterialRelaxed",
        "AIQ_HighWarp",
        "AIQ_HighCost",
        "AIQ_AttributeRelaxed",
    ):
        assert outputs["Grid"].data.attributes.get(name) is not None
    assert len(bpy.data.objects) == source_object_count + 6
    assert len(bpy.data.meshes) == source_mesh_count + 6
    for index, obj in enumerate(source_objects):
        assert snapshot_object(obj, f"test-{index}").fingerprint == before[obj.name]
    report = json.loads(bpy.data.texts[state.last_report_text_name].as_string())
    assert report["mode"] == "RECONSTRUCT"
    assert len(report["objects"]) == 6
    assert sum(item["status"] == "RECONSTRUCTED" for item in report["objects"]) == 6
    assert sum(item["status"] == "FAILED" for item in report["objects"]) == 0
    print("LCW_PHASE2_RECONSTRUCTION_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
