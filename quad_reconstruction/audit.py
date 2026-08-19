from __future__ import annotations

from collections import deque

from .models import ConnectedComponent, MeshAudit, MeshClassification, MeshSnapshot


def unsafe_face_indices(
    snapshot: MeshSnapshot,
    *,
    area_tolerance: float = 1e-12,
) -> frozenset[int]:
    """Return faces that must be preserved but never used by reconstruction."""
    unsafe = {
        face.index
        for face in snapshot.polygons
        if face.area <= area_tolerance or len(set(face.vertices)) != len(face.vertices)
    }
    faces_by_vertices: dict[tuple[int, ...], list[int]] = {}
    for face in snapshot.polygons:
        faces_by_vertices.setdefault(tuple(sorted(face.vertices)), []).append(face.index)
    for face_indices in faces_by_vertices.values():
        if len(face_indices) > 1:
            unsafe.update(face_indices)
    return frozenset(unsafe)


def _connected_components(snapshot: MeshSnapshot) -> tuple[ConnectedComponent, ...]:
    face_neighbors: list[set[int]] = [set() for _polygon in snapshot.polygons]
    for edge in snapshot.edges:
        for face_index in edge.face_indices:
            face_neighbors[face_index].update(
                neighbor for neighbor in edge.face_indices if neighbor != face_index
            )

    components = []
    pending = set(range(len(snapshot.polygons)))
    while pending:
        seed = min(pending)
        queue = deque([seed])
        pending.remove(seed)
        face_indices = []
        while queue:
            face_index = queue.popleft()
            face_indices.append(face_index)
            for neighbor in sorted(face_neighbors[face_index]):
                if neighbor in pending:
                    pending.remove(neighbor)
                    queue.append(neighbor)

        face_set = set(face_indices)
        vertex_indices = sorted(
            {vertex for face in face_indices for vertex in snapshot.polygons[face].vertices}
        )
        edge_indices = sorted(
            edge.index for edge in snapshot.edges if face_set.intersection(edge.face_indices)
        )
        component_edges = tuple(snapshot.edges[index] for index in edge_indices)
        components.append(
            ConnectedComponent(
                index=len(components),
                face_indices=tuple(sorted(face_indices)),
                vertex_indices=tuple(vertex_indices),
                edge_indices=tuple(edge_indices),
                euler_characteristic=len(vertex_indices) - len(edge_indices) + len(face_indices),
                boundary_edge_count=sum(edge.is_boundary for edge in component_edges),
                true_non_manifold_edge_count=sum(
                    edge.is_true_non_manifold for edge in component_edges
                ),
            )
        )
    return tuple(components)


def _classification(
    *,
    triangle_count: int,
    quad_count: int,
    ngon_count: int,
    boundary_count: int,
    non_manifold_count: int,
    degenerate_count: int,
    duplicate_count: int,
    face_count: int,
) -> MeshClassification:
    if face_count == 0:
        return MeshClassification.UNSUPPORTED
    if degenerate_count or duplicate_count:
        return MeshClassification.DEGENERATE
    if non_manifold_count:
        return MeshClassification.TRUE_NON_MANIFOLD
    if triangle_count and (quad_count or ngon_count):
        return MeshClassification.MIXED_TRI_QUAD
    if triangle_count == face_count and boundary_count:
        return MeshClassification.OPEN_TRIANGULATED
    if triangle_count == face_count:
        return MeshClassification.CLEAN_TRIANGULATED
    return MeshClassification.IRREGULAR_OR_REMESHED


def audit_snapshot(snapshot: MeshSnapshot, *, area_tolerance: float = 1e-12) -> MeshAudit:
    triangle_count = sum(len(face.vertices) == 3 for face in snapshot.polygons)
    quad_count = sum(len(face.vertices) == 4 for face in snapshot.polygons)
    ngon_count = sum(len(face.vertices) > 4 for face in snapshot.polygons)
    degenerate = tuple(
        face.index
        for face in snapshot.polygons
        if face.area <= area_tolerance or len(set(face.vertices)) != len(face.vertices)
    )
    duplicate = []
    seen_faces: dict[tuple[int, ...], int] = {}
    for face in snapshot.polygons:
        key = tuple(sorted(face.vertices))
        if key in seen_faces:
            duplicate.append(face.index)
        else:
            seen_faces[key] = face.index

    boundary_count = sum(edge.is_boundary for edge in snapshot.edges)
    non_manifold_count = sum(edge.is_true_non_manifold for edge in snapshot.edges)
    wire_count = sum(edge.is_wire for edge in snapshot.edges)
    warnings = []
    if ngon_count:
        warnings.append(f"Preserved {ngon_count} ngon face(s).")
    if wire_count:
        warnings.append(f"Found {wire_count} wire edge(s).")
    if non_manifold_count:
        warnings.append(
            f"Found {non_manifold_count} true non-manifold edge(s); they remain barriers."
        )
    if degenerate:
        warnings.append(
            f"Preserved {len(degenerate)} degenerate face(s) as reconstruction barriers."
        )
    if duplicate:
        warnings.append(
            f"Preserved {len(duplicate)} duplicate face occurrence(s) as reconstruction barriers."
        )
    if snapshot.modifier_types:
        warnings.append("Source modifiers are reported but never applied.")

    return MeshAudit(
        classification=_classification(
            triangle_count=triangle_count,
            quad_count=quad_count,
            ngon_count=ngon_count,
            boundary_count=boundary_count,
            non_manifold_count=non_manifold_count,
            degenerate_count=len(degenerate),
            duplicate_count=len(duplicate),
            face_count=len(snapshot.polygons),
        ),
        vertex_count=len(snapshot.vertices),
        edge_count=len(snapshot.edges),
        loop_count=len(snapshot.loops),
        face_count=len(snapshot.polygons),
        triangle_count=triangle_count,
        quad_count=quad_count,
        ngon_count=ngon_count,
        boundary_edge_count=boundary_count,
        true_non_manifold_edge_count=non_manifold_count,
        wire_edge_count=wire_count,
        degenerate_face_indices=degenerate,
        duplicate_face_indices=tuple(duplicate),
        vertex_valences=tuple(len(edges) for edges in snapshot.vertex_to_edges),
        connected_components=_connected_components(snapshot),
        uv_layer_names=tuple(layer.name for layer in snapshot.uv_layers),
        attribute_names=tuple(layer.name for layer in snapshot.attributes),
        has_custom_normals=snapshot.has_custom_normals,
        modifier_types=snapshot.modifier_types,
        warnings=tuple(warnings),
    )
