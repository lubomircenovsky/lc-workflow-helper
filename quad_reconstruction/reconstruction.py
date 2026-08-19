from __future__ import annotations

from datetime import UTC, datetime

import bmesh
import bpy

from .attributes import DIAGNOSTIC_ATTRIBUTES
from .models import CandidatePair, ConfidenceResult, MatchingResult, MeshSnapshot


GENERATED_MARKER = "lcw_aiq_generated"
RUN_ID_PROPERTY = "lcw_aiq_run_id"
SOURCE_UUID_PROPERTY = "lcw_aiq_source_uuid"
SOURCE_NAME_PROPERTY = "lcw_aiq_source_name"
ADDON_VERSION = "0.4.0"

def _child_collections(collection: bpy.types.Collection):
    for child in collection.children:
        yield child
        yield from _child_collections(child)


def output_parent_for_scene(
    scene: bpy.types.Scene,
    requested: bpy.types.Collection | None,
) -> bpy.types.Collection:
    if requested is not None:
        return requested
    parent = bpy.data.collections.get("AIQ Reconstruction Output")
    if parent is None:
        parent = bpy.data.collections.new("AIQ Reconstruction Output")
    if parent.name not in scene.collection.children:
        scene.collection.children.link(parent)
    parent["lcw_aiq_output_parent"] = True
    return parent


def create_run_collection_tree(
    input_collection: bpy.types.Collection,
    output_parent: bpy.types.Collection,
    run_id: str,
) -> tuple[bpy.types.Collection, dict[int, bpy.types.Collection]]:
    run_collection = bpy.data.collections.new(
        f"AIQ Run {datetime.now(UTC).strftime('%Y-%m-%d %H-%M-%S')}"
    )
    run_collection[GENERATED_MARKER] = True
    run_collection[RUN_ID_PROPERTY] = run_id
    output_parent.children.link(run_collection)
    collection_map = {input_collection.as_pointer(): run_collection}

    def mirror_children(source_parent, target_parent):
        for source_child in source_parent.children:
            target_child = bpy.data.collections.new(source_child.name)
            target_child[GENERATED_MARKER] = True
            target_child[RUN_ID_PROPERTY] = run_id
            target_parent.children.link(target_child)
            collection_map[source_child.as_pointer()] = target_child
            mirror_children(source_child, target_child)

    mirror_children(input_collection, run_collection)
    return run_collection, collection_map


def link_output_object(
    output_obj: bpy.types.Object,
    source_obj: bpy.types.Object,
    collection_map: dict[int, bpy.types.Collection],
    run_collection: bpy.types.Collection,
) -> None:
    linked = False
    for source_collection in source_obj.users_collection:
        target = collection_map.get(source_collection.as_pointer())
        if target is not None:
            target.objects.link(output_obj)
            linked = True
    if not linked:
        run_collection.objects.link(output_obj)


def create_output_copy(
    source_obj: bpy.types.Object,
    source_uuid: str,
    run_id: str,
    collection_map: dict[int, bpy.types.Collection],
    run_collection: bpy.types.Collection,
) -> bpy.types.Object:
    output_obj = source_obj.copy()
    output_mesh = None
    try:
        output_obj[GENERATED_MARKER] = True
        output_obj[RUN_ID_PROPERTY] = run_id
        output_mesh = source_obj.data.copy()
        output_obj.data = output_mesh
        output_obj.name = f"{source_obj.name}_AIQ"
        output_mesh.name = f"{source_obj.data.name}_AIQ"
        output_obj[SOURCE_UUID_PROPERTY] = source_uuid
        output_obj[SOURCE_NAME_PROPERTY] = source_obj.name
        output_mesh[GENERATED_MARKER] = True
        output_mesh[RUN_ID_PROPERTY] = run_id
        output_mesh[SOURCE_UUID_PROPERTY] = source_uuid
        link_output_object(output_obj, source_obj, collection_map, run_collection)
        return output_obj
    except Exception:
        bpy.data.objects.remove(output_obj, do_unlink=True)
        if output_mesh is not None and output_mesh.users == 0:
            bpy.data.meshes.remove(output_mesh)
        raise


def apply_matching_to_mesh(
    mesh: bpy.types.Mesh,
    snapshot: MeshSnapshot,
    candidates: tuple[CandidatePair, ...],
    matching: MatchingResult,
) -> None:
    selected = tuple(candidates[index] for index in matching.selected_candidate_indices)
    if not selected:
        mesh.update()
        return
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.edges.index_update()
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        dissolve_edges = []
        for candidate in selected:
            edge = bm.edges[candidate.dissolve_edge_index]
            if (
                edge is None
                or not edge.is_valid
                or len(edge.link_faces) != 2
                or any(len(face.verts) != 3 for face in edge.link_faces)
            ):
                raise RuntimeError(
                    f"Candidate {candidate.index} is not safely dissolvable."
                )
            dissolve_edges.append(edge)
        bmesh.ops.dissolve_edges(
            bm,
            edges=dissolve_edges,
            use_verts=False,
            use_face_split=False,
        )
        expected_quads = {frozenset(candidate.quad_vertices) for candidate in selected}
        actual_quads = {
            frozenset(vertex.index for vertex in face.verts)
            for face in bm.faces
            if len(face.verts) == 4
        }
        missing = expected_quads.difference(actual_quads)
        if missing:
            unexpected = actual_quads.difference(expected_quads)
            raise RuntimeError(
                f"Dissolve did not create {len(missing)} expected quad(s); "
                f"expected sets {len(expected_quads)}, actual quads {len(actual_quads)}, "
                f"unexpected quad sets {len(unexpected)}."
            )
        for face in bm.faces:
            if len(face.verts) < 3 or len({vertex.index for vertex in face.verts}) != len(face.verts):
                raise RuntimeError("Dissolve created an invalid face.")
            if face.calc_area() <= 0.0:
                raise RuntimeError("Dissolve created a zero-area face.")
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def create_diagnostic_attributes(
    mesh: bpy.types.Mesh,
    candidates: tuple[CandidatePair, ...],
    matching: MatchingResult,
) -> None:
    selected_by_vertices = {
        frozenset(candidates[index].quad_vertices): candidates[index]
        for index in matching.selected_candidate_indices
    }
    for name in DIAGNOSTIC_ATTRIBUTES:
        existing = mesh.attributes.get(name)
        if existing is not None:
            mesh.attributes.remove(existing)
    for name in DIAGNOSTIC_ATTRIBUTES:
        mesh.attributes.new(name=name, type="BOOLEAN", domain="FACE")
    mesh.update()
    # Adding custom-data layers can invalidate previously returned RNA wrappers.
    layers = {name: mesh.attributes[name] for name in DIAGNOSTIC_ATTRIBUTES}
    for polygon in mesh.polygons:
        candidate = selected_by_vertices.get(frozenset(polygon.vertices))
        flags = set(candidate.relaxation_flags) if candidate else set()
        layers["AIQ_UnresolvedTriangle"].data[polygon.index].value = len(polygon.vertices) == 3
        layers["AIQ_LowConfidence"].data[polygon.index].value = False
        layers["AIQ_UVRelaxed"].data[polygon.index].value = "UV" in flags
        layers["AIQ_SeamRelaxed"].data[polygon.index].value = "SEAM" in flags
        layers["AIQ_SharpRelaxed"].data[polygon.index].value = "SHARP" in flags
        layers["AIQ_MaterialRelaxed"].data[polygon.index].value = "MATERIAL" in flags
        layers["AIQ_HighWarp"].data[polygon.index].value = bool(
            candidate and candidate.metrics.warp_error > 0.025
        )
        layers["AIQ_HighCost"].data[polygon.index].value = bool(candidate and candidate.cost > 2.0)
        layers["AIQ_AttributeRelaxed"].data[polygon.index].value = any(
            flag.startswith(("FACE_ATTRIBUTE:", "CORNER_ATTRIBUTE:", "EDGE_ATTRIBUTE:"))
            or flag == "CUSTOM_NORMAL"
            for flag in flags
        )


def update_confidence_diagnostic(
    mesh: bpy.types.Mesh,
    confidence: ConfidenceResult,
) -> None:
    layer = mesh.attributes.get("AIQ_LowConfidence")
    if layer is None or layer.domain != "FACE" or layer.data_type != "BOOLEAN":
        return
    is_low = confidence.label in {"LOW", "FAILED"}
    for item in layer.data:
        item.value = is_low


def set_result_metadata(
    output_obj: bpy.types.Object,
    *,
    profile: str,
    settings_hash: str,
    source_fingerprint: str,
    report_id: str,
    matching: MatchingResult,
    confidence: ConfidenceResult,
    candidates: tuple[CandidatePair, ...],
    runtime_seconds: float,
) -> None:
    selected = tuple(candidates[index] for index in matching.selected_candidate_indices)
    relaxed_pairs = sum(bool(candidate.relaxation_flags) for candidate in selected)
    output_obj["lcw_aiq_addon_version"] = ADDON_VERSION
    output_obj["lcw_aiq_profile"] = profile
    output_obj["lcw_aiq_settings_hash"] = settings_hash
    output_obj["lcw_aiq_solver_backend"] = matching.backend
    output_obj["lcw_aiq_solver_exact"] = matching.exact
    output_obj["lcw_aiq_candidate_count"] = len(candidates)
    output_obj["lcw_aiq_matching_pairs"] = matching.cardinality
    output_obj["lcw_aiq_unresolved_triangles"] = len(matching.unmatched_face_indices)
    output_obj["lcw_aiq_relaxed_pairs"] = relaxed_pairs
    output_obj["lcw_aiq_relaxation_flags"] = ",".join(
        sorted({flag for candidate in selected for flag in candidate.relaxation_flags})
    )
    output_obj["lcw_aiq_confidence"] = confidence.score
    output_obj["lcw_aiq_confidence_label"] = confidence.label
    output_obj["lcw_aiq_runtime_seconds"] = runtime_seconds
    output_obj["lcw_aiq_source_fingerprint"] = source_fingerprint
    output_obj["lcw_aiq_report_id"] = report_id
    output_obj["lcw_aiq_timestamp"] = datetime.now(UTC).isoformat()


def remove_output_object(output_obj: bpy.types.Object) -> None:
    if not output_obj.get(GENERATED_MARKER):
        raise RuntimeError("Refusing to remove an object without the AIQ generated marker.")
    mesh = output_obj.data if output_obj.type == "MESH" else None
    if mesh is not None and not mesh.get(GENERATED_MARKER):
        raise RuntimeError("Refusing to remove a mesh without the AIQ generated marker.")
    bpy.data.objects.remove(output_obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def remove_empty_run_collection(run_collection: bpy.types.Collection, run_id: str) -> None:
    if not run_collection.get(GENERATED_MARKER) or run_collection.get(RUN_ID_PROPERTY) != run_id:
        raise RuntimeError("Refusing to remove an unrecognized run collection.")
    for child in tuple(_child_collections(run_collection)):
        if child.objects:
            return
    if run_collection.objects:
        return
    for child in reversed(tuple(_child_collections(run_collection))):
        if child.get(GENERATED_MARKER) and child.get(RUN_ID_PROPERTY) == run_id:
            bpy.data.collections.remove(child)
    bpy.data.collections.remove(run_collection)


def remove_run_collection(run_collection: bpy.types.Collection, run_id: str) -> None:
    if not run_collection.get(GENERATED_MARKER) or run_collection.get(RUN_ID_PROPERTY) != run_id:
        raise RuntimeError("Refusing to clear an unrecognized run collection.")
    objects = tuple(run_collection.all_objects)
    collections = (*tuple(_child_collections(run_collection)), run_collection)
    for collection in collections:
        if (
            not collection.get(GENERATED_MARKER)
            or collection.get(RUN_ID_PROPERTY) != run_id
        ):
            raise RuntimeError(
                f"Refusing to clear collection '{collection.name}' without matching run ID."
            )
    for obj in objects:
        if not obj.get(GENERATED_MARKER) or obj.get(RUN_ID_PROPERTY) != run_id:
            raise RuntimeError(
                f"Refusing to clear object '{obj.name}' without matching run ID."
            )
        if obj.type == "MESH" and (
            not obj.data.get(GENERATED_MARKER)
            or obj.data.get(RUN_ID_PROPERTY) != run_id
        ):
            raise RuntimeError(
                f"Refusing to clear mesh '{obj.data.name}' without matching run ID."
            )
    for obj in objects:
        remove_output_object(obj)
    for collection in reversed(collections):
        bpy.data.collections.remove(collection)
