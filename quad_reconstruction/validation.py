from __future__ import annotations

import math
from collections import Counter

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .audit import audit_snapshot
from .models import (
    CandidatePair,
    MatchingResult,
    MeshSnapshot,
    SubdivisionValidationResult,
    SurfaceDeviationResult,
    ValidationResult,
)
from .topology_snapshot import snapshot_object


def _edge_keys(snapshot: MeshSnapshot, predicate) -> set[tuple[int, int]]:
    return {tuple(sorted(edge.vertices)) for edge in snapshot.edges if predicate(edge)}


def _unsafe_face_signature(
    snapshot: MeshSnapshot,
    area_tolerance: float,
) -> Counter[tuple[int, ...]]:
    keys = [tuple(sorted(face.vertices)) for face in snapshot.polygons]
    counts = Counter(keys)
    return Counter(
        key
        for face, key in zip(snapshot.polygons, keys, strict=True)
        if face.area <= area_tolerance
        or len(set(face.vertices)) != len(face.vertices)
        or counts[key] > 1
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _sample_points(snapshot: MeshSnapshot) -> tuple[Vector, ...]:
    used_vertices = sorted(
        {vertex for polygon in snapshot.polygons for vertex in polygon.vertices}
    )
    points = [Vector(snapshot.vertices[index]) for index in used_vertices]
    for edge in snapshot.edges:
        if edge.is_wire:
            continue
        first, second = (Vector(snapshot.vertices[index]) for index in edge.vertices)
        points.append((first + second) * 0.5)
    for polygon in snapshot.polygons:
        center = Vector((0.0, 0.0, 0.0))
        for vertex_index in polygon.vertices:
            center += Vector(snapshot.vertices[vertex_index])
        points.append(center / len(polygon.vertices))
    return tuple(points)


def _snapshot_bvh(snapshot: MeshSnapshot) -> BVHTree:
    return BVHTree.FromPolygons(
        [Vector(co) for co in snapshot.vertices],
        [polygon.vertices for polygon in snapshot.polygons],
        all_triangles=False,
    )


def measure_surface_deviation(
    source_snapshot: MeshSnapshot,
    output_snapshot: MeshSnapshot,
) -> SurfaceDeviationResult:
    """Measure deterministic bidirectional sampled distance in object-local space."""
    source_bvh = _snapshot_bvh(source_snapshot)
    output_bvh = _snapshot_bvh(output_snapshot)
    distances = []
    for point in _sample_points(source_snapshot):
        nearest = output_bvh.find_nearest(point)
        if nearest is not None and nearest[3] is not None:
            distances.append(float(nearest[3]))
    for point in _sample_points(output_snapshot):
        nearest = source_bvh.find_nearest(point)
        if nearest is not None and nearest[3] is not None:
            distances.append(float(nearest[3]))
    if not distances:
        return SurfaceDeviationResult(0, math.inf, math.inf, math.inf, math.inf)
    return SurfaceDeviationResult(
        sample_count=len(distances),
        maximum=max(distances),
        mean=sum(distances) / len(distances),
        p50=_percentile(distances, 0.50),
        p95=_percentile(distances, 0.95),
    )


def _bbox_extents(vertices) -> Vector:
    if not vertices:
        return Vector((0.0, 0.0, 0.0))
    minimum = Vector(vertices[0])
    maximum = Vector(vertices[0])
    for coordinate in vertices[1:]:
        value = Vector(coordinate)
        minimum.x = min(minimum.x, value.x)
        minimum.y = min(minimum.y, value.y)
        minimum.z = min(minimum.z, value.z)
        maximum.x = max(maximum.x, value.x)
        maximum.y = max(maximum.y, value.y)
        maximum.z = max(maximum.z, value.z)
    return maximum - minimum


def run_subdivision_validation(
    scene: bpy.types.Scene,
    output_obj: bpy.types.Object,
) -> SubdivisionValidationResult:
    """Evaluate one Catmull-Clark level on disposable Blender data."""
    temp_obj = output_obj.copy()
    temp_mesh = output_obj.data.copy()
    evaluated_mesh = None
    try:
        temp_obj.data = temp_mesh
        temp_obj.name = "LCW_AIQ_SubdivisionValidation"
        while temp_obj.modifiers:
            temp_obj.modifiers.remove(temp_obj.modifiers[0])
        scene.collection.objects.link(temp_obj)
        modifier = temp_obj.modifiers.new(name="LCW AIQ Validation", type="SUBSURF")
        modifier.subdivision_type = "CATMULL_CLARK"
        modifier.levels = 1
        modifier.render_levels = 1
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = temp_obj.evaluated_get(depsgraph)
        evaluated_mesh = bpy.data.meshes.new_from_object(
            evaluated,
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        coordinates = [tuple(vertex.co) for vertex in evaluated_mesh.vertices]
        finite = all(math.isfinite(value) for co in coordinates for value in co)
        degenerate = sum(
            polygon.area <= 1e-12 or len(set(polygon.vertices)) < 3
            for polygon in evaluated_mesh.polygons
        )
        source_extents = _bbox_extents([tuple(vertex.co) for vertex in output_obj.data.vertices])
        evaluated_extents = _bbox_extents(coordinates)
        bbox_delta = max(abs(a - b) for a, b in zip(source_extents, evaluated_extents))
        passed = finite and degenerate == 0 and bool(coordinates)
        return SubdivisionValidationResult(
            ran=True,
            passed=passed,
            finite_coordinates=finite,
            vertex_count=len(evaluated_mesh.vertices),
            face_count=len(evaluated_mesh.polygons),
            degenerate_face_count=degenerate,
            bbox_delta_max=bbox_delta,
        )
    except Exception as exc:
        return SubdivisionValidationResult(
            ran=True,
            passed=False,
            finite_coordinates=False,
            vertex_count=0,
            face_count=0,
            degenerate_face_count=0,
            bbox_delta_max=0.0,
            error=str(exc),
        )
    finally:
        if evaluated_mesh is not None and evaluated_mesh.users == 0:
            bpy.data.meshes.remove(evaluated_mesh)
        bpy.data.objects.remove(temp_obj, do_unlink=True)
        if temp_mesh.users == 0:
            bpy.data.meshes.remove(temp_mesh)


def validate_reconstruction(
    source_obj: bpy.types.Object,
    source_snapshot: MeshSnapshot,
    output_obj: bpy.types.Object,
    candidates: tuple[CandidatePair, ...],
    matching: MatchingResult,
    *,
    measure_surface: bool = True,
    run_subdivision: bool = False,
    area_tolerance: float = 1e-12,
) -> ValidationResult:
    errors = []
    warnings = []
    output_snapshot = snapshot_object(output_obj, source_snapshot.source_uuid)
    source_after = snapshot_object(source_obj, source_snapshot.source_uuid)
    fingerprint_unchanged = source_after.fingerprint == source_snapshot.fingerprint
    if not fingerprint_unchanged:
        errors.append("Source fingerprint changed during reconstruction.")
    positions_unchanged = output_snapshot.vertices == source_snapshot.vertices
    if not positions_unchanged:
        errors.append("Output vertex positions differ from the source.")
    boundary_preserved = _edge_keys(source_snapshot, lambda edge: edge.is_boundary) == _edge_keys(
        output_snapshot, lambda edge: edge.is_boundary
    )
    if not boundary_preserved:
        errors.append("Boundary edge set changed.")
    non_manifold_preserved = _edge_keys(
        source_snapshot, lambda edge: edge.is_true_non_manifold
    ) == _edge_keys(output_snapshot, lambda edge: edge.is_true_non_manifold)
    if not non_manifold_preserved:
        errors.append("True non-manifold edge set changed.")
    output_audit = audit_snapshot(output_snapshot, area_tolerance=area_tolerance)
    source_unsafe = _unsafe_face_signature(source_snapshot, area_tolerance)
    output_unsafe = _unsafe_face_signature(output_snapshot, area_tolerance)
    if output_unsafe != source_unsafe:
        errors.append("Degenerate or duplicate source faces were not preserved exactly.")
    elif source_unsafe:
        warnings.append(
            f"Preserved {sum(source_unsafe.values())} pre-existing unsafe face(s)."
        )
    expected_quads = sum(len(face.vertices) == 4 for face in source_snapshot.polygons) + matching.cardinality
    actual_quads = output_audit.quad_count
    if actual_quads != expected_quads:
        errors.append(f"Expected {expected_quads} quads but found {actual_quads}.")
    if tuple(layer.name for layer in source_snapshot.uv_layers) != tuple(
        layer.name for layer in output_snapshot.uv_layers
    ):
        errors.append("UV layer names changed.")
    source_attributes = {
        layer.name for layer in source_snapshot.attributes if not layer.name.startswith(".")
    }
    output_attributes = {layer.name for layer in output_snapshot.attributes}
    selected_relaxations = {
        flag
        for candidate_index in matching.selected_candidate_indices
        for flag in candidates[candidate_index].relaxation_flags
    }
    allowed_missing = set()
    if "SEAM" in selected_relaxations:
        allowed_missing.add("uv_seam")
    if "SHARP" in selected_relaxations:
        allowed_missing.add("sharp_edge")
    for flag in selected_relaxations:
        prefix, separator, name = flag.partition(":")
        if separator and prefix in {
            "FACE_ATTRIBUTE",
            "CORNER_ATTRIBUTE",
            "EDGE_ATTRIBUTE",
        }:
            allowed_missing.add(name)
    missing_attributes = source_attributes.difference(output_attributes)
    unexpected_missing = missing_attributes.difference(allowed_missing)
    if unexpected_missing:
        errors.append(
            "Source attribute layers are missing: " + ", ".join(sorted(unexpected_missing))
        )
    if missing_attributes.intersection(allowed_missing):
        warnings.append(
            "Explicitly relaxed built-in layers changed: "
            + ", ".join(sorted(missing_attributes.intersection(allowed_missing)))
        )
    if source_snapshot.material_slots != output_snapshot.material_slots:
        errors.append("Material slots changed.")
    if source_snapshot.matrix_world != output_snapshot.matrix_world:
        errors.append("Object world transform changed.")
    if matching.unmatched_face_indices:
        warnings.append(f"{len(matching.unmatched_face_indices)} triangle face(s) remain unresolved.")
    surface = measure_surface_deviation(source_snapshot, output_snapshot) if measure_surface else None
    if surface is not None:
        source_extents = _bbox_extents(source_snapshot.vertices)
        tolerance = max(1e-7, source_extents.length * 1e-6)
        if not math.isfinite(surface.maximum):
            errors.append("Surface deviation could not be measured.")
        elif surface.maximum > tolerance:
            warnings.append(
                f"Surface deviation maximum {surface.maximum:.6g} exceeds "
                f"the diagnostic tolerance {tolerance:.6g}."
            )
    subdivision = (
        run_subdivision_validation(bpy.context.scene, output_obj)
        if run_subdivision
        else None
    )
    if subdivision is not None and not subdivision.passed:
        message = "Catmull-Clark validation failed" + (
            f": {subdivision.error}" if subdivision.error else "."
        )
        if source_unsafe:
            warnings.append(
                message + " Pre-existing unsafe source faces were preserved exactly."
            )
        else:
            errors.append(message)
    return ValidationResult(
        valid=not errors,
        fingerprint_unchanged=fingerprint_unchanged,
        vertex_positions_unchanged=positions_unchanged,
        boundary_preserved=boundary_preserved,
        true_non_manifold_preserved=non_manifold_preserved,
        expected_quad_count=expected_quads,
        actual_quad_count=actual_quads,
        errors=tuple(errors),
        warnings=tuple(warnings),
        surface_deviation=surface,
        subdivision=subdivision,
    )


def validate_existing_output(
    source_obj: bpy.types.Object,
    output_obj: bpy.types.Object,
    *,
    measure_surface: bool = True,
    run_subdivision: bool = False,
) -> ValidationResult:
    source_uuid = str(output_obj.get("lcw_aiq_source_uuid", ""))
    source_snapshot = snapshot_object(source_obj, source_uuid)
    output_snapshot = snapshot_object(output_obj, source_uuid)
    errors = []
    warnings = []
    expected_fingerprint = str(output_obj.get("lcw_aiq_source_fingerprint", ""))
    fingerprint_unchanged = bool(expected_fingerprint) and (
        source_snapshot.fingerprint == expected_fingerprint
    )
    if not fingerprint_unchanged:
        errors.append("Source fingerprint no longer matches the reconstruction source.")
    positions_unchanged = output_snapshot.vertices == source_snapshot.vertices
    if not positions_unchanged:
        errors.append("Output vertex positions differ from the source.")
    boundary_preserved = _edge_keys(source_snapshot, lambda edge: edge.is_boundary) == _edge_keys(
        output_snapshot,
        lambda edge: edge.is_boundary,
    )
    if not boundary_preserved:
        errors.append("Boundary edge set changed.")
    non_manifold_preserved = _edge_keys(
        source_snapshot,
        lambda edge: edge.is_true_non_manifold,
    ) == _edge_keys(output_snapshot, lambda edge: edge.is_true_non_manifold)
    if not non_manifold_preserved:
        errors.append("True non-manifold edge set changed.")
    output_audit = audit_snapshot(output_snapshot)
    source_unsafe = _unsafe_face_signature(source_snapshot, 1e-12)
    output_unsafe = _unsafe_face_signature(output_snapshot, 1e-12)
    if output_unsafe != source_unsafe:
        errors.append("Degenerate or duplicate source faces were not preserved exactly.")
    elif source_unsafe:
        warnings.append(
            f"Preserved {sum(source_unsafe.values())} pre-existing unsafe face(s)."
        )
    matching_pairs = int(output_obj.get("lcw_aiq_matching_pairs", 0))
    expected_quads = (
        sum(len(face.vertices) == 4 for face in source_snapshot.polygons)
        + matching_pairs
    )
    actual_quads = output_audit.quad_count
    if expected_quads != actual_quads:
        errors.append(f"Expected {expected_quads} quads but found {actual_quads}.")
    if output_obj.data == source_obj.data:
        errors.append("Output unexpectedly shares the source mesh datablock.")
    if source_snapshot.material_slots != output_snapshot.material_slots:
        errors.append("Material slots changed.")
    if source_snapshot.matrix_world != output_snapshot.matrix_world:
        errors.append("Object world transform changed.")
    unresolved = int(output_obj.get("lcw_aiq_unresolved_triangles", 0))
    if unresolved:
        warnings.append(f"{unresolved} triangle face(s) remain unresolved.")
    surface = measure_surface_deviation(source_snapshot, output_snapshot) if measure_surface else None
    if surface is not None and not math.isfinite(surface.maximum):
        errors.append("Surface deviation could not be measured.")
    subdivision = (
        run_subdivision_validation(bpy.context.scene, output_obj)
        if run_subdivision
        else None
    )
    if subdivision is not None and not subdivision.passed:
        message = "Catmull-Clark validation failed" + (
            f": {subdivision.error}" if subdivision.error else "."
        )
        if source_unsafe:
            warnings.append(
                message + " Pre-existing unsafe source faces were preserved exactly."
            )
        else:
            errors.append(message)
    return ValidationResult(
        valid=not errors,
        fingerprint_unchanged=fingerprint_unchanged,
        vertex_positions_unchanged=positions_unchanged,
        boundary_preserved=boundary_preserved,
        true_non_manifold_preserved=non_manifold_preserved,
        expected_quad_count=expected_quads,
        actual_quad_count=actual_quads,
        errors=tuple(errors),
        warnings=tuple(warnings),
        surface_deviation=surface,
        subdivision=subdivision,
    )
