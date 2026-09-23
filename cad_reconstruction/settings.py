from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty


class LCW_PG_CADResult(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Object)
    output: PointerProperty(type=bpy.types.Object)
    status: StringProperty()
    geometry_status: StringProperty()
    coverage_status: StringProperty()
    partial: BoolProperty(default=False)
    summary: StringProperty()
    reason: StringProperty()
    stage: StringProperty()
    run_dir: StringProperty(subtype="DIR_PATH")
    normal_limit_deg: FloatProperty()


class LCW_PG_CADCollectionBinding(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Collection)
    output_parent: PointerProperty(type=bpy.types.Collection)
    branch: PointerProperty(type=bpy.types.Collection)


class LCW_PG_CADState(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Input", items=(("COLLECTION", "Collection", "Process a collection and its children"), ("SELECTED", "Selected Objects", "Process selected mesh objects")), default="COLLECTION")
    input_collection: PointerProperty(name="Input Collection", type=bpy.types.Collection)
    output_collection: PointerProperty(name="Output Collection", type=bpy.types.Collection)
    run_root: StringProperty(name="Run Folder", description="Where immutable worker inputs, results and reports are kept; // is relative to the .blend", subtype="DIR_PATH", default="//cad_mesh_runs")
    epsilon_mm: FloatProperty(name="Deviation Limit (mm)", description="Maximum sampled shape deviation; not a guarantee of complete feature coverage", default=0.4, min=0.000001)
    straight_walls: BoolProperty(name="Merge Straight Walls", default=True)
    circular_holes: BoolProperty(name="Circular Holes", description="Detect and reduce segments around circular sheet-metal holes", default=True)
    perimeter_loops: BoolProperty(name="Perimeter Loops", description="Build support loops around circular holes; can be run alone on an existing mesh", default=True)
    arcs: BoolProperty(name="Arcs", description="Detect and reduce concave and convex open arcs", default=True)
    outer_cylinders: BoolProperty(name="Outer Cylinders", description="Reconstruct closed outer cylindrical surfaces", default=True)
    background_cleanup: BoolProperty(name="Background Cleanup", description="Dissolve only validated background-plane edges", default=True)
    normal_override: BoolProperty(name="Manual Normal Limit", description="Override the calibrated corner-normal limit at your own risk", default=False)
    normal_limit_deg: FloatProperty(name="Normal Limit (degrees)", description="Positive finite angular tolerance; values over 0.05 degrees can visibly change shading", default=0.01, min=0.0, soft_max=0.05)
    normal_risk_ack: BoolProperty(name="I Accept Shading Risk", description="Required when manually overriding the normal limit", default=False)
    results: CollectionProperty(type=LCW_PG_CADResult)
    active_result: IntProperty(default=0, min=0)
    bindings: CollectionProperty(type=LCW_PG_CADCollectionBinding)
    running: BoolProperty(default=False)
    progress: StringProperty(default="Idle")
    analysis_summary: StringProperty(default="Run Analyze before a long batch.")
    input_section_open: BoolProperty(name="Input", default=True)
    options_section_open: BoolProperty(name="Reconstruction Options", default=True)
    normal_section_open: BoolProperty(name="Advanced Normal Validation", default=False)
    run_section_open: BoolProperty(name="Run", default=True)
    results_section_open: BoolProperty(name="Results", default=True)


CLASSES = (LCW_PG_CADResult, LCW_PG_CADCollectionBinding, LCW_PG_CADState)


def register_properties():
    bpy.types.Scene.lcw_cad_reconstruction = PointerProperty(type=LCW_PG_CADState)


def unregister_properties():
    from . import jobs

    if jobs.ACTIVE_JOB is not None:
        jobs.ACTIVE_JOB.cancel()
        jobs.ACTIVE_JOB = None
    if hasattr(bpy.types.Scene, "lcw_cad_reconstruction"):
        del bpy.types.Scene.lcw_cad_reconstruction
