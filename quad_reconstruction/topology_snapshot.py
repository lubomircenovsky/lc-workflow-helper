from __future__ import annotations

from collections.abc import Iterable

import bpy

from .models import (
    AttributeSnapshot,
    AttributeValue,
    EdgeSnapshot,
    LoopSnapshot,
    MeshSnapshot,
    PolygonSnapshot,
    UVLayerSnapshot,
)
from .fingerprint import fingerprint_snapshot


LOCK_ATTRIBUTE_NAMES = ("AIQ_Locked", "lcw_aiq_locked")


def _tuple_value(value: object) -> tuple[object, ...]:
    if isinstance(value, str):
        return (value,)
    try:
        values = tuple(value)  # type: ignore[arg-type]
    except TypeError:
        return (str(value),)
    flattened: list[object] = []
    for item in values:
        if isinstance(item, str):
            flattened.append(item)
            continue
        try:
            flattened.extend(tuple(item))  # type: ignore[arg-type]
        except TypeError:
            flattened.append(item)
    return tuple(flattened)


def _attribute_value(item: object) -> AttributeValue:
    for property_name in (
        "value",
        "vector",
        "color",
        "byte_color",
        "quaternion",
        "matrix",
    ):
        if not hasattr(item, property_name):
            continue
        value = getattr(item, property_name)
        if isinstance(value, (bool, int, float, str)):
            return value
        return _tuple_value(value)
    return ""


def _snapshot_attributes(mesh: bpy.types.Mesh) -> tuple[AttributeSnapshot, ...]:
    layers = []
    for attribute in sorted(mesh.attributes, key=lambda item: (item.domain, item.name)):
        layers.append(
            AttributeSnapshot(
                name=attribute.name,
                domain=attribute.domain,
                data_type=attribute.data_type,
                values=tuple(_attribute_value(item) for item in attribute.data),
            )
        )
    return tuple(layers)


def _boolean_edge_attribute(mesh: bpy.types.Mesh, names: Iterable[str]) -> tuple[bool, ...]:
    for name in names:
        attribute = mesh.attributes.get(name)
        if attribute is None or attribute.domain != "EDGE" or attribute.data_type != "BOOLEAN":
            continue
        return tuple(bool(item.value) for item in attribute.data)
    return tuple(False for _edge in mesh.edges)


def _sharp_edges(mesh: bpy.types.Mesh) -> tuple[bool, ...]:
    attribute = mesh.attributes.get("sharp_edge")
    if attribute is not None and attribute.domain == "EDGE" and attribute.data_type == "BOOLEAN":
        return tuple(bool(item.value) for item in attribute.data)
    return tuple(bool(getattr(edge, "use_edge_sharp", False)) for edge in mesh.edges)


def snapshot_object(obj: bpy.types.Object, source_uuid: str) -> MeshSnapshot:
    if obj.type != "MESH" or obj.data is None:
        raise TypeError(f"Object '{obj.name}' is not a mesh object.")

    mesh = obj.data
    face_indices_by_edge: list[list[int]] = [[] for _edge in mesh.edges]
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            edge_index = mesh.loops[loop_index].edge_index
            if polygon.index not in face_indices_by_edge[edge_index]:
                face_indices_by_edge[edge_index].append(polygon.index)

    locked_edges = _boolean_edge_attribute(mesh, LOCK_ATTRIBUTE_NAMES)
    sharp_edges = _sharp_edges(mesh)
    edges = tuple(
        EdgeSnapshot(
            index=edge.index,
            vertices=tuple(edge.vertices),
            face_indices=tuple(sorted(face_indices_by_edge[edge.index])),
            seam=bool(edge.use_seam),
            sharp=sharp_edges[edge.index],
            locked=locked_edges[edge.index],
        )
        for edge in mesh.edges
    )
    loops = tuple(
        LoopSnapshot(vertex_index=loop.vertex_index, edge_index=loop.edge_index)
        for loop in mesh.loops
    )
    polygons = tuple(
        PolygonSnapshot(
            index=polygon.index,
            vertices=tuple(polygon.vertices),
            loop_indices=tuple(polygon.loop_indices),
            normal=tuple(polygon.normal),
            material_index=polygon.material_index,
            area=polygon.area,
        )
        for polygon in mesh.polygons
    )
    vertex_to_edges: list[list[int]] = [[] for _vertex in mesh.vertices]
    vertex_to_faces: list[list[int]] = [[] for _vertex in mesh.vertices]
    for edge in edges:
        for vertex_index in edge.vertices:
            vertex_to_edges[vertex_index].append(edge.index)
    for polygon in polygons:
        for vertex_index in polygon.vertices:
            vertex_to_faces[vertex_index].append(polygon.index)

    uv_layers = tuple(
        UVLayerSnapshot(
            name=layer.name,
            values=tuple(tuple(item.uv) for item in layer.data),
        )
        for layer in mesh.uv_layers
    )
    has_custom_normals = bool(getattr(mesh, "has_custom_normals", False))
    custom_normals = ()
    if has_custom_normals:
        custom_normals = tuple(tuple(item.vector) for item in mesh.corner_normals)
    parent_reference = ""
    if obj.parent is not None:
        parent_library = obj.parent.library.filepath if obj.parent.library else ""
        parent_reference = f"{parent_library}|{obj.parent.name_full}|{obj.parent_type}"

    snapshot = MeshSnapshot(
        source_uuid=source_uuid,
        source_object_name=obj.name,
        source_mesh_name=mesh.name,
        vertices=tuple(tuple(vertex.co) for vertex in mesh.vertices),
        edges=edges,
        loops=loops,
        polygons=polygons,
        vertex_to_edges=tuple(tuple(sorted(indices)) for indices in vertex_to_edges),
        vertex_to_faces=tuple(tuple(sorted(indices)) for indices in vertex_to_faces),
        uv_layers=uv_layers,
        attributes=_snapshot_attributes(mesh),
        material_slots=tuple(slot.material.name if slot.material else "" for slot in obj.material_slots),
        has_custom_normals=has_custom_normals,
        custom_normals=custom_normals,
        modifier_types=tuple(modifier.type for modifier in obj.modifiers),
        matrix_world=tuple(value for row in obj.matrix_world for value in row),
        scale=tuple(obj.scale),
        parent_reference=parent_reference,
        fingerprint="",
    )
    return MeshSnapshot(
        source_uuid=snapshot.source_uuid,
        source_object_name=snapshot.source_object_name,
        source_mesh_name=snapshot.source_mesh_name,
        vertices=snapshot.vertices,
        edges=snapshot.edges,
        loops=snapshot.loops,
        polygons=snapshot.polygons,
        vertex_to_edges=snapshot.vertex_to_edges,
        vertex_to_faces=snapshot.vertex_to_faces,
        uv_layers=snapshot.uv_layers,
        attributes=snapshot.attributes,
        material_slots=snapshot.material_slots,
        has_custom_normals=snapshot.has_custom_normals,
        custom_normals=snapshot.custom_normals,
        modifier_types=snapshot.modifier_types,
        matrix_world=snapshot.matrix_world,
        scale=snapshot.scale,
        parent_reference=snapshot.parent_reference,
        fingerprint=fingerprint_snapshot(snapshot),
    )
