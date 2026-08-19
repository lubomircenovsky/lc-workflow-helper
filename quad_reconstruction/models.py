from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias


Vec2: TypeAlias = tuple[float, float]
Vec3: TypeAlias = tuple[float, float, float]
AttributeValue: TypeAlias = bool | int | float | str | tuple[object, ...]


class MeshClassification(StrEnum):
    CLEAN_TRIANGULATED = "CLEAN_TRIANGULATED"
    MIXED_TRI_QUAD = "MIXED_TRI_QUAD"
    OPEN_TRIANGULATED = "OPEN_TRIANGULATED"
    TRUE_NON_MANIFOLD = "TRUE_NON_MANIFOLD"
    IRREGULAR_OR_REMESHED = "IRREGULAR_OR_REMESHED"
    DEGENERATE = "DEGENERATE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class LoopSnapshot:
    vertex_index: int
    edge_index: int


@dataclass(frozen=True, slots=True)
class PolygonSnapshot:
    index: int
    vertices: tuple[int, ...]
    loop_indices: tuple[int, ...]
    normal: Vec3
    material_index: int
    area: float


@dataclass(frozen=True, slots=True)
class EdgeSnapshot:
    index: int
    vertices: tuple[int, int]
    face_indices: tuple[int, ...]
    seam: bool
    sharp: bool
    locked: bool

    @property
    def is_boundary(self) -> bool:
        return len(self.face_indices) == 1

    @property
    def is_wire(self) -> bool:
        return not self.face_indices

    @property
    def is_true_non_manifold(self) -> bool:
        return len(self.face_indices) >= 3


@dataclass(frozen=True, slots=True)
class UVLayerSnapshot:
    name: str
    values: tuple[Vec2, ...]


@dataclass(frozen=True, slots=True)
class AttributeSnapshot:
    name: str
    domain: str
    data_type: str
    values: tuple[AttributeValue, ...]


@dataclass(frozen=True, slots=True)
class MeshSnapshot:
    source_uuid: str
    source_object_name: str
    source_mesh_name: str
    vertices: tuple[Vec3, ...]
    edges: tuple[EdgeSnapshot, ...]
    loops: tuple[LoopSnapshot, ...]
    polygons: tuple[PolygonSnapshot, ...]
    vertex_to_edges: tuple[tuple[int, ...], ...]
    vertex_to_faces: tuple[tuple[int, ...], ...]
    uv_layers: tuple[UVLayerSnapshot, ...]
    attributes: tuple[AttributeSnapshot, ...]
    material_slots: tuple[str, ...]
    has_custom_normals: bool
    custom_normals: tuple[Vec3, ...]
    modifier_types: tuple[str, ...]
    matrix_world: tuple[float, ...]
    scale: Vec3
    parent_reference: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ConnectedComponent:
    index: int
    face_indices: tuple[int, ...]
    vertex_indices: tuple[int, ...]
    edge_indices: tuple[int, ...]
    euler_characteristic: int
    boundary_edge_count: int
    true_non_manifold_edge_count: int


@dataclass(frozen=True, slots=True)
class TriangleRegion:
    index: int
    face_indices: tuple[int, ...]
    candidate_edge_indices: tuple[int, ...]
    barrier_edge_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    planarity_error: float
    warp_error: float
    corner_error: float
    log_aspect_error: float
    opposite_edge_error: float
    diagonal_balance_error: float
    flow_alignment_error: float
    curvature_continuity_error: float
    valence_delta: float
    uv_discontinuity_penalty: float
    sharp_or_seam_penalty: float
    material_boundary_penalty: float
    attribute_violation_count: int


@dataclass(frozen=True, slots=True)
class CandidatePair:
    index: int
    region_index: int
    face_indices: tuple[int, int]
    dissolve_edge_index: int
    quad_vertices: tuple[int, int, int, int]
    metrics: CandidateMetrics
    cost: float
    hard_valid: bool
    rejection_reasons: tuple[str, ...]
    relaxation_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchingResult:
    backend: str
    selected_candidate_indices: tuple[int, ...]
    unmatched_face_indices: tuple[int, ...]
    cardinality: int
    total_cost: float
    exact: bool
    warnings: tuple[str, ...] = ()
    hypothesis_margin: float = 0.0


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    score: float
    label: str
    coverage: float
    mean_cost: float
    p95_warp: float
    max_warp: float
    relaxation_count: int
    solver_exact: bool
    hypothesis_margin: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceDeviationResult:
    sample_count: int
    maximum: float
    mean: float
    p50: float
    p95: float


@dataclass(frozen=True, slots=True)
class SubdivisionValidationResult:
    ran: bool
    passed: bool
    finite_coordinates: bool
    vertex_count: int
    face_count: int
    degenerate_face_count: int
    bbox_delta_max: float
    error: str = ""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    fingerprint_unchanged: bool
    vertex_positions_unchanged: bool
    boundary_preserved: bool
    true_non_manifold_preserved: bool
    expected_quad_count: int
    actual_quad_count: int
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    surface_deviation: SurfaceDeviationResult | None = None
    subdivision: SubdivisionValidationResult | None = None


@dataclass(frozen=True, slots=True)
class ObjectResult:
    source_uuid: str
    source_object_name: str
    output_object_name: str
    status: str
    candidate_count: int
    matching: MatchingResult | None
    validation: ValidationResult | None
    runtime_seconds: float
    confidence: ConfidenceResult | None = None
    relaxation_flags: tuple[str, ...] = ()
    error: str = ""
    phase_timings: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class NativeBaselineResult:
    name: str
    topology_influence: float
    joined_pairs: int
    remaining_triangles: int
    resulting_quads: int
    runtime_seconds: float
    error: str = ""


@dataclass(frozen=True, slots=True)
class MeshAudit:
    classification: MeshClassification
    vertex_count: int
    edge_count: int
    loop_count: int
    face_count: int
    triangle_count: int
    quad_count: int
    ngon_count: int
    boundary_edge_count: int
    true_non_manifold_edge_count: int
    wire_edge_count: int
    degenerate_face_indices: tuple[int, ...]
    duplicate_face_indices: tuple[int, ...]
    vertex_valences: tuple[int, ...]
    connected_components: tuple[ConnectedComponent, ...]
    uv_layer_names: tuple[str, ...]
    attribute_names: tuple[str, ...]
    has_custom_normals: bool
    modifier_types: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObjectAnalysis:
    source_uuid: str
    source_object_name: str
    source_mesh_name: str
    fingerprint_before: str
    fingerprint_after: str
    fingerprint_unchanged: bool
    audit: MeshAudit | None
    regions: tuple[TriangleRegion, ...]
    baselines: tuple[NativeBaselineResult, ...]
    runtime_seconds: float
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchReport:
    report_id: str
    settings_hash: str
    input_collection_name: str
    objects: tuple[ObjectAnalysis, ...]
    runtime_seconds: float
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)
