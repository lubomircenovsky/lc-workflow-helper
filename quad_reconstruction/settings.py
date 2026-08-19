from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)

from .profiles import profile_defaults


PROFILE_ITEMS = (
    ("STRICT", "Strict", "Preserve protected data and leave ambiguous triangles unresolved"),
    ("BALANCED", "Balanced", "Prefer data preservation while allowing explicit soft constraints"),
    ("AGGRESSIVE", "Aggressive", "Maximize safe quad coverage and report every relaxation"),
    ("ANALYZE_ONLY", "Analyze Only", "Audit and compare hypotheses without creating mesh data"),
)


def _profile_updated(self, _context) -> None:
    profile = profile_defaults(self.profile)
    self.protect_materials = profile.protect_materials
    self.protect_uv = profile.protect_uv
    self.protect_seams = profile.protect_seams
    self.protect_sharp_edges = profile.protect_sharp_edges

SOLVER_ITEMS = (
    ("AUTO", "Auto", "Use exact blossom within the safe component limit and fallback above it"),
    ("EXACT_BLOSSOM", "Exact Blossom", "Use exact matching only within the configured safety limit"),
    ("SEED_AUGMENT", "Seed + Augment", "Use the deterministic dependency-free fallback"),
    ("NATIVE_BASELINE", "Native Baseline", "Analyze Blender join-triangles hypotheses only"),
)

JOB_STATUS_ITEMS = (
    ("IDLE", "Idle", "No quad reconstruction job is active"),
    ("ANALYZING", "Analyzing", "Collection analysis is running"),
    ("ANALYZED", "Analyzed", "Analysis completed without creating output meshes"),
    ("RECONSTRUCTING", "Reconstructing", "Quad reconstruction is running"),
    ("RECONSTRUCTED", "Reconstructed", "Quad reconstruction completed"),
    ("CANCELLED", "Cancelled", "The active job was cancelled and cleaned up"),
    ("FAILED", "Failed", "The latest analysis failed"),
)


class LCW_PG_QuadSourceIdentity(bpy.types.PropertyGroup):
    source_object: PointerProperty(type=bpy.types.Object)
    source_uuid: StringProperty(name="Source UUID")


class LCW_PG_QuadAnalysisResult(bpy.types.PropertyGroup):
    source_uuid: StringProperty(name="Source UUID")
    source_object_name: StringProperty(name="Object")
    source_mesh_name: StringProperty(name="Mesh")
    classification: StringProperty(name="Classification")
    status: StringProperty(name="Status")
    triangle_count: IntProperty(name="Triangles", min=0)
    quad_count: IntProperty(name="Quads", min=0)
    ngon_count: IntProperty(name="Ngons", min=0)
    region_count: IntProperty(name="Regions", min=0)
    warning_count: IntProperty(name="Warnings", min=0)
    fingerprint_unchanged: BoolProperty(name="Source Unchanged", default=False)
    runtime_seconds: FloatProperty(name="Runtime", min=0.0, subtype="TIME")
    details: StringProperty(name="Details")
    output_object: PointerProperty(type=bpy.types.Object)
    candidate_count: IntProperty(name="Candidates", min=0)
    matching_pair_count: IntProperty(name="Matching Pairs", min=0)
    unresolved_triangle_count: IntProperty(name="Unresolved Triangles", min=0)
    coverage: FloatProperty(name="Coverage", min=0.0, max=1.0, subtype="FACTOR")
    validation_passed: BoolProperty(name="Validation Passed", default=False)
    solver_backend: StringProperty(name="Solver Backend")
    solver_exact: BoolProperty(name="Exact Solver", default=False)
    confidence_score: FloatProperty(name="Confidence", min=0.0, max=100.0)
    confidence_label: StringProperty(name="Confidence Label")
    relaxation_count: IntProperty(name="Relaxations", min=0)


class LCW_PG_QuadReconstructionState(bpy.types.PropertyGroup):
    input_collection: PointerProperty(
        name="Input Collection",
        description="Collection whose mesh objects and child collections will be analyzed",
        type=bpy.types.Collection,
    )
    output_collection: PointerProperty(
        name="Output Collection",
        description="Parent for generated run collections; an AIQ output parent is created when empty",
        type=bpy.types.Collection,
    )
    profile: EnumProperty(
        name="Profile",
        items=PROFILE_ITEMS,
        default="STRICT",
        update=_profile_updated,
    )
    solver_backend: EnumProperty(name="Solver Backend", items=SOLVER_ITEMS, default="AUTO")
    protect_materials: BoolProperty(name="Protect Materials", default=True)
    protect_uv: BoolProperty(name="Protect UV", default=True)
    protect_seams: BoolProperty(name="Protect Seams", default=True)
    protect_sharp_edges: BoolProperty(name="Protect Sharp Edges", default=True)
    process_open_meshes: BoolProperty(name="Process Open Meshes", default=True)
    process_true_non_manifold_regions: BoolProperty(
        name="Process True Non-Manifold Regions",
        description="Analyze safe regions around true non-manifold barriers without dissolving those barriers",
        default=True,
    )
    run_subdivision_validation: BoolProperty(name="Run Subdivision Validation", default=True)
    create_face_diagnostics: BoolProperty(name="Create Face Diagnostics", default=True)
    preserve_existing_quads: BoolProperty(name="Preserve Existing Quads", default=True)
    uv_tolerance: FloatProperty(name="UV Tolerance", default=1e-6, min=0.0, precision=6)
    area_tolerance: FloatProperty(name="Area Tolerance", default=1e-12, min=0.0, precision=8)
    max_warp: FloatProperty(name="Maximum Warp", default=0.05, min=0.0, precision=4)
    exact_component_limit: IntProperty(
        name="Exact Component Limit",
        description="Maximum triangle count for exact blossom matching in one region",
        default=2000,
        min=16,
        max=20000,
    )
    maximum_iterations: IntProperty(
        name="Cycle Optimization Passes",
        description="Maximum deterministic alternating-cycle improvement passes",
        default=8,
        min=1,
        max=100,
    )
    parallel_core_processing: BoolProperty(
        name="Parallel Core Processing",
        description=(
            "Generate candidates in isolated Blender-Python worker processes; "
            "workers never access bpy or bmesh"
        ),
        default=True,
    )
    parallel_worker_count: IntProperty(
        name="Parallel Workers",
        description="Maximum candidate-generation worker processes",
        default=2,
        min=1,
        max=8,
    )
    parallel_triangle_threshold: IntProperty(
        name="Parallel Triangle Threshold",
        description=(
            "Minimum processable triangle count before external workers are used; "
            "higher values avoid process startup overhead on medium meshes"
        ),
        default=50000,
        min=1000,
        max=10000000,
    )
    topology_influence: FloatProperty(
        name="Topology Influence",
        default=0.5,
        min=0.0,
        max=1.0,
    )
    weight_planarity: FloatProperty(name="Planarity", default=3.0, min=0.0)
    weight_corner: FloatProperty(name="Corners", default=1.4, min=0.0)
    weight_aspect: FloatProperty(name="Aspect", default=0.12, min=0.0)
    weight_opposite_edge: FloatProperty(name="Opposite Edges", default=0.10, min=0.0)
    weight_diagonal_balance: FloatProperty(name="Diagonal Balance", default=0.04, min=0.0)
    weight_flow: FloatProperty(name="Flow", default=0.20, min=0.0)
    weight_curvature: FloatProperty(name="Curvature", default=0.35, min=0.0)
    weight_valence: FloatProperty(name="Valence", default=0.20, min=0.0)
    weight_uv: FloatProperty(name="UV Discontinuity", default=8.0, min=0.0)
    weight_seam_or_sharp: FloatProperty(name="Seam / Sharp", default=8.0, min=0.0)
    weight_material: FloatProperty(name="Material", default=12.0, min=0.0)
    weight_attribute: FloatProperty(name="Attributes", default=6.0, min=0.0)
    debug_logging: BoolProperty(name="Debug Logging", default=False)
    results: CollectionProperty(type=LCW_PG_QuadAnalysisResult)
    active_result_index: IntProperty(name="Active Result", default=0, min=0)
    source_identities: CollectionProperty(type=LCW_PG_QuadSourceIdentity)
    job_status: EnumProperty(name="Status", items=JOB_STATUS_ITEMS, default="IDLE")
    job_message: StringProperty(name="Message")
    progress: FloatProperty(name="Progress", default=0.0, min=0.0, max=1.0, subtype="FACTOR")
    progress_label: StringProperty(name="Progress Detail")
    cancel_requested: BoolProperty(name="Cancel Requested", default=False)
    active_run_id: StringProperty(name="Active Run ID")
    last_report_id: StringProperty(name="Report ID")
    last_report_text_name: StringProperty(name="Report Text")
    last_run_collection: PointerProperty(type=bpy.types.Collection)
    settings_section_open: BoolProperty(name="Settings", default=True)
    advanced_section_open: BoolProperty(name="Advanced", default=False)
    results_section_open: BoolProperty(name="Results", default=True)
    weights_section_open: BoolProperty(name="Scoring Weights", default=False)


CLASSES = (
    LCW_PG_QuadSourceIdentity,
    LCW_PG_QuadAnalysisResult,
    LCW_PG_QuadReconstructionState,
)


def register_properties() -> None:
    bpy.types.Scene.lcw_quad_reconstruction = PointerProperty(type=LCW_PG_QuadReconstructionState)


def unregister_properties() -> None:
    if hasattr(bpy.types.Scene, "lcw_quad_reconstruction"):
        delattr(bpy.types.Scene, "lcw_quad_reconstruction")
