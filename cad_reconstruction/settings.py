from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


class LCW_PG_CADResult(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Object)
    source_label: StringProperty()
    component_index: IntProperty(default=-1)
    output: PointerProperty(type=bpy.types.Object)
    status: StringProperty()
    geometry_status: StringProperty()
    coverage_status: StringProperty()
    partial: BoolProperty(default=False)
    preserve_nonmanifold: BoolProperty(default=False)
    summary: StringProperty()
    perimeter_summary: StringProperty()
    planar_summary: StringProperty()
    metrics_summary: StringProperty()
    reason: StringProperty()
    technical_reason: StringProperty()
    stage: StringProperty()
    run_dir: StringProperty(subtype="DIR_PATH")
    details_open: BoolProperty(default=False)
    files_deleted: BoolProperty(default=False)
    normal_limit_deg: FloatProperty()
    elapsed_seconds: FloatProperty()


class LCW_PG_CADCollectionBinding(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Collection)
    output_parent: PointerProperty(type=bpy.types.Collection)
    branch: PointerProperty(type=bpy.types.Collection)


class LCW_PG_CADAnalysisLine(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Object)
    severity: StringProperty()
    message: StringProperty()
    technical: StringProperty()
    recommendation: StringProperty()
    source_hash: StringProperty()
    run_dir: StringProperty(subtype="DIR_PATH")


class LCW_PG_CADState(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Input", items=(("COLLECTION", "Collection", "Process a collection and its children"), ("SELECTED", "Selected Objects", "Process selected mesh objects")), default="COLLECTION")
    input_collection: PointerProperty(name="Input Collection", type=bpy.types.Collection)
    output_collection: PointerProperty(name="Output Collection", type=bpy.types.Collection)
    run_root: StringProperty(name="Run Folder", description="Where immutable worker inputs, results and reports are kept; // is relative to the .blend", subtype="DIR_PATH", default="//cad_mesh_runs")
    concurrent_workers: IntProperty(name="Concurrent Workers", description="Maximum separate Blender processes used for CAD objects; high values require more memory", default=4, min=1, max=16)
    epsilon_mm: FloatProperty(name="Deviation Limit (mm)", description="Maximum sampled shape deviation; not a guarantee of complete feature coverage", default=0.4, min=0.000001)
    straight_walls: BoolProperty(name="Merge Straight Walls", description="Merge validated straight wall patches without changing curved walls", default=True)
    circular_holes: BoolProperty(name="Circular Holes", description="Detect and reduce circular sheet-metal holes unless Keep Curve Segments is active", default=True)
    hole_detail_factor: FloatProperty(name="Detail", description="Hole segment target multiplier: 1 keeps the previous target, lower is coarser, higher is finer; bounded by Hole Deviation and source segments", default=1.0, min=0.1, max=2.0, precision=2)
    hole_epsilon_mm: FloatProperty(name="Hole Deviation (mm)", description="Independent sampled deviation limit near reconstructed circular holes; 0 uses Deviation Limit. Other surfaces keep the general limit", default=0.0, min=0.0, precision=3)
    separate_solids: BoolProperty(name="Separate Solids", description="Reconstruct shells independently, including closed shells at many-face edges and unambiguous measured shared caps. Ambiguous open junction patches stay together. Assembly intersections are retained, not certified as one nonintersecting mesh", default=False)
    preserve_curve_segmentation: BoolProperty(name="Preserve Curve Segmentation", description="Keep existing hole and curved-surface contours unchanged while applying selected perimeter and planar cleanup operations", default=False)
    perimeter_loops: BoolProperty(name="Perimeter Loops", description="Build support loops around circular holes; can be run alone on an existing mesh", default=True)
    perimeter_clearance_mm: FloatProperty(name="Clearance (mm)", description="Preferred nominal gap from a circular hole to its square support loop in millimetres; 0 = Auto; smaller safe gaps may be used when space is tight", default=0.0, min=0.0, precision=2)
    arcs: BoolProperty(name="Arcs", description="Detect and reduce concave and convex open arcs", default=True)
    outer_cylinders: BoolProperty(name="Outer Cylinders", description="Reconstruct closed outer cylindrical surfaces", default=True)
    background_cleanup: BoolProperty(name="Background Cleanup", description="Dissolve only validated background-plane edges", default=True)
    normal_override: BoolProperty(name="Manual Normal Limit", description="Override the calibrated corner-normal limit at your own risk", default=False)
    normal_limit_deg: FloatProperty(name="Normal Limit (degrees)", description="Positive finite angular tolerance; values over 0.05 degrees can visibly change shading", default=0.01, min=0.0, soft_max=0.05)
    normal_risk_ack: BoolProperty(name="I Accept Shading Risk", description="Required when manually overriding the normal limit", default=False)
    uv_prep_map_name: StringProperty(name="New UV Map", description="Name for the new UV layer; an existing map is never overwritten", default="LCW_CAD_UV")
    uv_prep_angle_degrees: FloatProperty(name="Cut Angle (degrees)", description="Cut folds sharper than this angle; smoother bends stay in one UV island", default=45.0, min=1.0, max=179.0)
    uv_prep_margin: FloatProperty(name="Island Margin", description="UV-space margin between packed islands", default=0.005, min=0.0, max=0.1, precision=4)
    uv_prep_summary: StringProperty(default="No UV preparation run yet.", options={"SKIP_SAVE"})
    results: CollectionProperty(type=LCW_PG_CADResult)
    active_result: IntProperty(default=0, min=0)
    bindings: CollectionProperty(type=LCW_PG_CADCollectionBinding)
    running: BoolProperty(default=False)
    analysis_running: BoolProperty(default=False, options={"SKIP_SAVE"})
    progress: StringProperty(default="Idle")
    analysis_summary: StringProperty(default="Run Analyze before a long batch.")
    analysis_ready: BoolProperty(default=False)
    analysis_meshes: IntProperty(default=0)
    analysis_blockers: IntProperty(default=0)
    analysis_notes: IntProperty(default=0)
    analysis_lines: CollectionProperty(type=LCW_PG_CADAnalysisLine)
    analysis_details_open: BoolProperty(default=False)
    results_visible: IntProperty(default=5, min=5)
    cleanup_running: BoolProperty(default=False, options={"SKIP_SAVE"})
    cleanup_progress: StringProperty(default="", options={"SKIP_SAVE"})
    input_section_open: BoolProperty(name="Input", default=True)
    options_section_open: BoolProperty(name="Reconstruction Options", default=True)
    normal_section_open: BoolProperty(name="Advanced Normal Validation", default=False)
    run_section_open: BoolProperty(name="Run", default=True)
    results_section_open: BoolProperty(name="Results", default=True)
    uv_prep_section_open: BoolProperty(name="UV Preparation", default=False)


CLASSES = (LCW_PG_CADResult, LCW_PG_CADCollectionBinding,
           LCW_PG_CADAnalysisLine, LCW_PG_CADState)


def register_properties():
    bpy.types.Scene.lcw_cad_reconstruction = PointerProperty(type=LCW_PG_CADState)
    from . import analysis_jobs
    if analysis_jobs.cancel_active not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(analysis_jobs.cancel_active)


def unregister_properties():
    from . import jobs, analysis_jobs

    if jobs.ACTIVE_JOB is not None:
        jobs.ACTIVE_JOB.cancel()
        jobs.ACTIVE_JOB = None
    analysis_jobs.cancel_active()
    if analysis_jobs.cancel_active in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(analysis_jobs.cancel_active)
    if hasattr(bpy.types.Scene, "lcw_cad_reconstruction"):
        del bpy.types.Scene.lcw_cad_reconstruction
