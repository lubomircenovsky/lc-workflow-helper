from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .models import EdgeSnapshot, MeshSnapshot, TriangleRegion
from .audit import unsafe_face_indices


@dataclass(frozen=True, slots=True)
class RegionSettings:
    protect_materials: bool = True
    protect_uv: bool = True
    protect_seams: bool = True
    protect_sharp_edges: bool = True
    process_open_meshes: bool = True
    process_true_non_manifold_regions: bool = True
    uv_tolerance: float = 1e-6
    area_tolerance: float = 1e-12


def _face_uv(snapshot: MeshSnapshot, layer_index: int, face_index: int, vertex_index: int):
    face = snapshot.polygons[face_index]
    layer = snapshot.uv_layers[layer_index]
    for loop_index in face.loop_indices:
        if snapshot.loops[loop_index].vertex_index == vertex_index:
            return layer.values[loop_index]
    return None


def _uv_is_continuous(
    snapshot: MeshSnapshot,
    edge: EdgeSnapshot,
    tolerance: float,
) -> bool:
    face_a, face_b = edge.face_indices
    tolerance_squared = tolerance * tolerance
    for layer_index in range(len(snapshot.uv_layers)):
        for vertex_index in edge.vertices:
            uv_a = _face_uv(snapshot, layer_index, face_a, vertex_index)
            uv_b = _face_uv(snapshot, layer_index, face_b, vertex_index)
            if uv_a is None or uv_b is None:
                return False
            delta_u = uv_a[0] - uv_b[0]
            delta_v = uv_a[1] - uv_b[1]
            if delta_u * delta_u + delta_v * delta_v > tolerance_squared:
                return False
    return True


def edge_is_candidate_barrier(
    snapshot: MeshSnapshot,
    edge: EdgeSnapshot,
    settings: RegionSettings,
) -> bool:
    if len(edge.face_indices) != 2:
        return True
    face_a = snapshot.polygons[edge.face_indices[0]]
    face_b = snapshot.polygons[edge.face_indices[1]]
    if len(face_a.vertices) != 3 or len(face_b.vertices) != 3:
        return True
    if len(set(face_a.vertices).union(face_b.vertices)) != 4:
        return True
    if edge.locked:
        return True
    if settings.protect_materials and face_a.material_index != face_b.material_index:
        return True
    if settings.protect_seams and edge.seam:
        return True
    if settings.protect_sharp_edges and edge.sharp:
        return True
    return settings.protect_uv and not _uv_is_continuous(
        snapshot,
        edge,
        settings.uv_tolerance,
    )


def build_triangle_regions(
    snapshot: MeshSnapshot,
    settings: RegionSettings,
) -> tuple[TriangleRegion, ...]:
    excluded_faces: set[int] = set()
    unsafe_faces = unsafe_face_indices(
        snapshot,
        area_tolerance=settings.area_tolerance,
    )
    if not settings.process_open_meshes:
        excluded_faces.update(
            face_index
            for edge in snapshot.edges
            if edge.is_boundary
            for face_index in edge.face_indices
        )
    if not settings.process_true_non_manifold_regions:
        excluded_faces.update(
            face_index
            for edge in snapshot.edges
            if edge.is_true_non_manifold
            for face_index in edge.face_indices
        )

    triangle_faces = {
        face.index
        for face in snapshot.polygons
        if len(face.vertices) == 3 and face.index not in excluded_faces
    }
    candidate_edges = {
        edge.index
        for edge in snapshot.edges
        if not unsafe_faces.intersection(edge.face_indices)
        and not edge_is_candidate_barrier(snapshot, edge, settings)
    }
    neighbors: dict[int, list[tuple[int, int]]] = {face: [] for face in triangle_faces}
    for edge_index in sorted(candidate_edges):
        edge = snapshot.edges[edge_index]
        face_a, face_b = edge.face_indices
        if face_a in triangle_faces and face_b in triangle_faces:
            neighbors[face_a].append((face_b, edge_index))
            neighbors[face_b].append((face_a, edge_index))

    regions = []
    pending = set(triangle_faces)
    while pending:
        seed = min(pending)
        pending.remove(seed)
        queue = deque([seed])
        faces = []
        region_candidate_edges: set[int] = set()
        while queue:
            face_index = queue.popleft()
            faces.append(face_index)
            for neighbor, edge_index in sorted(neighbors[face_index]):
                region_candidate_edges.add(edge_index)
                if neighbor in pending:
                    pending.remove(neighbor)
                    queue.append(neighbor)

        incident_edges = {
            snapshot.loops[loop_index].edge_index
            for face_index in faces
            for loop_index in snapshot.polygons[face_index].loop_indices
        }
        barriers = sorted(incident_edges.difference(region_candidate_edges))
        regions.append(
            TriangleRegion(
                index=len(regions),
                face_indices=tuple(sorted(faces)),
                candidate_edge_indices=tuple(sorted(region_candidate_edges)),
                barrier_edge_indices=tuple(barriers),
            )
        )
    return tuple(regions)
