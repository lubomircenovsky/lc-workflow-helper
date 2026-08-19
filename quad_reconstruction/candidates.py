from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .models import CandidateMetrics, CandidatePair, MeshSnapshot, TriangleRegion
from .scoring import (
    ScoringWeights,
    candidate_cost,
    normalized_candidate_cost,
    robust_metric_scales,
)


BUILTIN_EDGE_ATTRIBUTES = {".edge_verts", "sharp_edge", "AIQ_Locked", "lcw_aiq_locked"}


@dataclass(frozen=True, slots=True)
class CandidateSettings:
    profile: str = "STRICT"
    protect_materials: bool = True
    protect_uv: bool = True
    protect_seams: bool = True
    protect_sharp_edges: bool = True
    geometry_tolerance: float = 1e-12
    uv_tolerance: float = 1e-6
    max_warp: float = 0.05
    weights: ScoringWeights = ScoringWeights()


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(vector):
    return math.sqrt(max(0.0, _dot(vector, vector)))


def _normalized(vector):
    length = _length(vector)
    if length == 0.0:
        return (0.0, 0.0, 0.0)
    return tuple(component / length for component in vector)


def cyclic_quad_vertices(
    snapshot: MeshSnapshot,
    face_indices: tuple[int, int],
    shared_edge_vertices: tuple[int, int],
) -> tuple[tuple[int, int, int, int] | None, str]:
    shared_key = tuple(sorted(shared_edge_vertices))
    directed_boundary = []
    for face_index in face_indices:
        vertices = snapshot.polygons[face_index].vertices
        if len(vertices) != 3:
            return None, "NON_TRIANGLE_FACE"
        for offset, vertex in enumerate(vertices):
            next_vertex = vertices[(offset + 1) % 3]
            if tuple(sorted((vertex, next_vertex))) != shared_key:
                directed_boundary.append((vertex, next_vertex))
    if len(directed_boundary) != 4:
        return None, "INVALID_BOUNDARY"
    next_by_vertex: dict[int, int] = {}
    for start, end in directed_boundary:
        if start in next_by_vertex:
            return None, "INCONSISTENT_WINDING"
        next_by_vertex[start] = end
    if len(next_by_vertex) != 4:
        return None, "INCONSISTENT_WINDING"
    start = min(next_by_vertex)
    cycle = [start]
    for _index in range(3):
        next_vertex = next_by_vertex.get(cycle[-1])
        if next_vertex is None or next_vertex in cycle:
            return None, "INCONSISTENT_WINDING"
        cycle.append(next_vertex)
    if next_by_vertex.get(cycle[-1]) != start:
        return None, "INCONSISTENT_WINDING"
    return tuple(cycle), ""


def _project_to_2d(points, normal):
    axis = max(range(3), key=lambda index: abs(normal[index]))
    if axis == 0:
        return tuple((point[1], point[2]) for point in points)
    if axis == 1:
        return tuple((point[0], point[2]) for point in points)
    return tuple((point[0], point[1]) for point in points)


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a, b, c, d, tolerance):
    ab_c = _orientation(a, b, c)
    ab_d = _orientation(a, b, d)
    cd_a = _orientation(c, d, a)
    cd_b = _orientation(c, d, b)
    return ab_c * ab_d < -tolerance and cd_a * cd_b < -tolerance


def _geometry_metrics(snapshot, quad_vertices, edge_index, settings):
    points = tuple(snapshot.vertices[index] for index in quad_vertices)
    edge_vectors = tuple(_sub(points[(index + 1) % 4], points[index]) for index in range(4))
    edge_lengths = tuple(_length(vector) for vector in edge_vectors)
    reasons = []
    if min(edge_lengths) <= settings.geometry_tolerance:
        reasons.append("ZERO_LENGTH_EDGE")

    newell = (0.0, 0.0, 0.0)
    for index, point in enumerate(points):
        next_point = points[(index + 1) % 4]
        newell = (
            newell[0] + (point[1] - next_point[1]) * (point[2] + next_point[2]),
            newell[1] + (point[2] - next_point[2]) * (point[0] + next_point[0]),
            newell[2] + (point[0] - next_point[0]) * (point[1] + next_point[1]),
        )
    newell_length = _length(newell)
    normal = _normalized(newell)
    if newell_length <= settings.geometry_tolerance:
        reasons.append("DEGENERATE_QUAD")
        incident_faces = snapshot.edges[edge_index].face_indices
        fallback_normal = tuple(
            sum(snapshot.polygons[face_index].normal[axis] for face_index in incident_faces)
            for axis in range(3)
        )
        normal = _normalized(fallback_normal)
        if _length(normal) == 0.0:
            normal = _normalized(_cross(_sub(points[1], points[0]), _sub(points[2], points[0])))
    projected = _project_to_2d(points, normal)
    turns = tuple(
        _orientation(projected[index], projected[(index + 1) % 4], projected[(index + 2) % 4])
        for index in range(4)
    )
    nonzero_turns = tuple(turn for turn in turns if abs(turn) > settings.geometry_tolerance)
    if not nonzero_turns or any(turn * nonzero_turns[0] < 0.0 for turn in nonzero_turns[1:]):
        reasons.append("NON_CONVEX_QUAD")
    if _segments_cross(*projected, settings.geometry_tolerance) or _segments_cross(
        projected[1], projected[2], projected[3], projected[0], settings.geometry_tolerance
    ):
        reasons.append("SELF_INTERSECTION")

    centroid = tuple(sum(point[axis] for point in points) / 4.0 for axis in range(3))
    scale = max(sum(edge_lengths) / 4.0, settings.geometry_tolerance)
    plane_distances = tuple(abs(_dot(_sub(point, centroid), normal)) / scale for point in points)
    planarity_error = max(plane_distances)
    if planarity_error > settings.max_warp:
        reasons.append("HIGH_WARP")

    corner_errors = []
    for index in range(4):
        incoming = _normalized(_sub(points[index - 1], points[index]))
        outgoing = _normalized(_sub(points[(index + 1) % 4], points[index]))
        corner_errors.append(abs(_dot(incoming, outgoing)))
    aspect_ratio = max(edge_lengths) / max(min(edge_lengths), settings.geometry_tolerance)
    opposite_error = 0.5 * (
        abs(edge_lengths[0] - edge_lengths[2]) / max(edge_lengths[0], edge_lengths[2], settings.geometry_tolerance)
        + abs(edge_lengths[1] - edge_lengths[3]) / max(edge_lengths[1], edge_lengths[3], settings.geometry_tolerance)
    )
    alternate_diagonal = _length(_sub(points[2], points[0]))
    dissolved_diagonal = _length(
        _sub(
            snapshot.vertices[snapshot.edges[edge_index].vertices[1]],
            snapshot.vertices[snapshot.edges[edge_index].vertices[0]],
        )
    )
    diagonal_balance = abs(alternate_diagonal - dissolved_diagonal) / max(
        alternate_diagonal,
        dissolved_diagonal,
        settings.geometry_tolerance,
    )
    return {
        "planarity": planarity_error,
        "corner": sum(corner_errors) / 4.0,
        "aspect": abs(math.log(max(aspect_ratio, 1.0))),
        "opposite": opposite_error,
        "diagonal": diagonal_balance,
        "reasons": reasons,
    }


def _face_loop_index(snapshot, face_index, vertex_index):
    face = snapshot.polygons[face_index]
    for loop_index in face.loop_indices:
        if snapshot.loops[loop_index].vertex_index == vertex_index:
            return loop_index
    return -1


def _face_uv(snapshot, layer, face_index, vertex_index):
    loop_index = _face_loop_index(snapshot, face_index, vertex_index)
    if loop_index >= 0:
        return layer.values[loop_index], loop_index
    return None, -1


def _values_equal(first, second, tolerance=1e-9):
    if isinstance(first, float) and isinstance(second, float):
        return abs(first - second) <= tolerance
    if isinstance(first, tuple) and isinstance(second, tuple) and len(first) == len(second):
        return all(_values_equal(a, b, tolerance) for a, b in zip(first, second, strict=True))
    return first == second


def _attribute_violations(
    snapshot,
    face_indices,
    edge_index,
    uv_tolerance,
    uv_layer_names,
):
    violations = []
    face_a, face_b = face_indices
    edge = snapshot.edges[edge_index]
    uv_discontinuous = False
    for layer in snapshot.uv_layers:
        for vertex_index in edge.vertices:
            uv_a, _loop_a = _face_uv(snapshot, layer, face_a, vertex_index)
            uv_b, _loop_b = _face_uv(snapshot, layer, face_b, vertex_index)
            if uv_a is None or uv_b is None:
                uv_discontinuous = True
                continue
            if math.dist(uv_a, uv_b) > uv_tolerance:
                uv_discontinuous = True

    for attribute in snapshot.attributes:
        if attribute.name in uv_layer_names:
            continue
        # Blender exposes transient topology/selection state as hidden attributes.
        # These are not user-authored data and must not block strict reconstruction.
        if attribute.name.startswith("."):
            continue
        if attribute.name == "material_index":
            continue
        if attribute.domain == "FACE" and not _values_equal(
            attribute.values[face_a], attribute.values[face_b]
        ):
            violations.append(f"FACE_ATTRIBUTE:{attribute.name}")
        elif attribute.domain == "CORNER":
            for vertex_index in edge.vertices:
                loop_a = _face_loop_index(snapshot, face_a, vertex_index)
                loop_b = _face_loop_index(snapshot, face_b, vertex_index)
                if loop_a >= 0 and loop_b >= 0 and not _values_equal(
                    attribute.values[loop_a], attribute.values[loop_b]
                ):
                    violations.append(f"CORNER_ATTRIBUTE:{attribute.name}")
                    break
        elif attribute.domain == "EDGE" and attribute.name not in BUILTIN_EDGE_ATTRIBUTES:
            value = attribute.values[edge_index]
            if value not in (False, 0, 0.0, "", (), None):
                violations.append(f"EDGE_ATTRIBUTE:{attribute.name}")

    if snapshot.custom_normals:
        for vertex_index in edge.vertices:
            loops = []
            for face_index in face_indices:
                face = snapshot.polygons[face_index]
                loops.extend(
                    loop_index
                    for loop_index in face.loop_indices
                    if snapshot.loops[loop_index].vertex_index == vertex_index
                )
            if len(loops) == 2 and not _values_equal(
                snapshot.custom_normals[loops[0]], snapshot.custom_normals[loops[1]], 1e-6
            ):
                violations.append("CUSTOM_NORMAL")
    return uv_discontinuous, tuple(sorted(set(violations)))


def _valence_delta(snapshot, edge_index, boundary_vertices):
    edge = snapshot.edges[edge_index]
    penalties = []
    for vertex_index in edge.vertices:
        current = len(snapshot.vertex_to_edges[vertex_index])
        target = 3 if vertex_index in boundary_vertices else 4
        penalties.append(abs((current - 1) - target) / max(target, 1))
    return sum(penalties) / len(penalties)


def generate_candidates(
    snapshot: MeshSnapshot,
    regions: tuple[TriangleRegion, ...],
    settings: CandidateSettings,
) -> tuple[CandidatePair, ...]:
    candidates = []
    boundary_vertices = {
        vertex
        for edge in snapshot.edges
        if edge.is_boundary
        for vertex in edge.vertices
    }
    uv_layer_names = frozenset(layer.name for layer in snapshot.uv_layers)
    for region in regions:
        region_indices = []
        for edge_index in region.candidate_edge_indices:
            edge = snapshot.edges[edge_index]
            face_indices = tuple(edge.face_indices)
            reasons = []
            relaxations = []
            quad_vertices, ordering_error = cyclic_quad_vertices(
                snapshot,
                face_indices,
                edge.vertices,
            )
            if quad_vertices is None:
                reasons.append(ordering_error)
                quad_vertices = tuple(sorted(set(
                    snapshot.polygons[face_indices[0]].vertices
                    + snapshot.polygons[face_indices[1]].vertices
                )))
            geometry = _geometry_metrics(snapshot, quad_vertices, edge_index, settings)
            reasons.extend(geometry["reasons"])
            face_a, face_b = (snapshot.polygons[index] for index in face_indices)
            material_violation = face_a.material_index != face_b.material_index
            seam_violation = edge.seam
            sharp_violation = edge.sharp
            uv_violation, attribute_violations = _attribute_violations(
                snapshot,
                face_indices,
                edge_index,
                settings.uv_tolerance,
                uv_layer_names,
            )
            if material_violation:
                relaxations.append("MATERIAL")
                if settings.protect_materials:
                    reasons.append("MATERIAL_BOUNDARY")
            if seam_violation:
                relaxations.append("SEAM")
                if settings.protect_seams:
                    reasons.append("SEAM_BOUNDARY")
            if sharp_violation:
                relaxations.append("SHARP")
                if settings.protect_sharp_edges:
                    reasons.append("SHARP_BOUNDARY")
            if uv_violation:
                relaxations.append("UV")
                if settings.protect_uv:
                    reasons.append("UV_DISCONTINUITY")
            if attribute_violations:
                relaxations.extend(attribute_violations)
                if settings.profile == "STRICT":
                    reasons.append("ATTRIBUTE_CONFLICT")

            normal_a = _normalized(face_a.normal)
            normal_b = _normalized(face_b.normal)
            curvature = math.acos(max(-1.0, min(1.0, _dot(normal_a, normal_b)))) / math.pi
            metrics = CandidateMetrics(
                planarity_error=geometry["planarity"],
                warp_error=geometry["planarity"],
                corner_error=geometry["corner"],
                log_aspect_error=geometry["aspect"],
                opposite_edge_error=geometry["opposite"],
                diagonal_balance_error=geometry["diagonal"],
                flow_alignment_error=0.0,
                curvature_continuity_error=curvature,
                valence_delta=_valence_delta(snapshot, edge_index, boundary_vertices),
                uv_discontinuity_penalty=1.0 if uv_violation else 0.0,
                sharp_or_seam_penalty=float(seam_violation or sharp_violation),
                material_boundary_penalty=float(material_violation),
                attribute_violation_count=len(attribute_violations),
            )
            candidates.append(
                CandidatePair(
                    index=len(candidates),
                    region_index=region.index,
                    face_indices=face_indices,
                    dissolve_edge_index=edge_index,
                    quad_vertices=quad_vertices,
                    metrics=metrics,
                    cost=candidate_cost(metrics, settings.weights),
                    hard_valid=not reasons,
                    rejection_reasons=tuple(sorted(set(reasons))),
                    relaxation_flags=tuple(sorted(set(relaxations))),
                )
            )
            region_indices.append(len(candidates) - 1)
        scales = robust_metric_scales(
            tuple(candidates[index].metrics for index in region_indices)
        )
        for index in region_indices:
            candidate = candidates[index]
            candidates[index] = replace(
                candidate,
                cost=normalized_candidate_cost(candidate.metrics, settings.weights, scales),
            )
    return tuple(candidates)
