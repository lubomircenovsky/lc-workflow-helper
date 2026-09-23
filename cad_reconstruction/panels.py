from __future__ import annotations

import bpy

from . import jobs, status_overlay


def _section(layout, state, property_name, label, icon):
    box = layout.box()
    row = box.row(align=True)
    opened = getattr(state, property_name)
    row.prop(
        state, property_name, text="", emboss=False,
        icon="TRIA_DOWN" if opened else "TRIA_RIGHT",
    )
    row.label(text=label, icon=icon)
    return box if opened else None


class LCW_PT_cad_reconstruction(bpy.types.Panel):
    bl_idname = "LCW_PT_cad_reconstruction"
    bl_label = "CAD Mesh Reconstruction"
    bl_parent_id = "LCW_PT_root"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LC Workflow"

    def draw(self, context):
        layout = self.layout
        state = context.scene.lcw_cad_reconstruction
        running = jobs.ACTIVE_JOB is not None

        box = _section(layout, state, "input_section_open", "Input", "OUTLINER_COLLECTION")
        if box is not None:
            controls = box.column(align=True)
            controls.enabled = not running
            controls.prop(state, "mode", expand=True)
            if state.mode == "COLLECTION":
                controls.prop(state, "input_collection")
                controls.prop(state, "output_collection")
            else:
                count = sum(obj.type == "MESH" for obj in context.selected_objects)
                controls.label(text=f"Selected mesh objects: {count}", icon="OUTLINER_OB_MESH")
            controls.prop(state, "run_root")

        box = _section(layout, state, "options_section_open", "Reconstruction Options", "MOD_REMESH")
        if box is not None:
            controls = box.column(align=True)
            controls.enabled = not running
            controls.prop(state, "epsilon_mm")
            controls.prop(state, "circular_holes")
            controls.prop(state, "perimeter_loops")
            controls.prop(state, "arcs")
            controls.prop(state, "outer_cylinders")
            controls.prop(state, "background_cleanup")
            controls.prop(state, "straight_walls")
            advanced = _section(
                controls, state, "normal_section_open", "Advanced Normal Validation", "ERROR"
            )
            if advanced is not None:
                advanced.prop(state, "normal_override")
                if state.normal_override:
                    advanced.prop(state, "normal_limit_deg")
                    advanced.label(text="Above 0.05 degrees may change shading.", icon="ERROR")
                    advanced.label(text="Other geometry checks still apply.", icon="INFO")
                    advanced.prop(state, "normal_risk_ack")

        box = _section(layout, state, "run_section_open", "Run", "PLAY")
        if box is not None:
            row = box.row(align=True)
            row.enabled = not running
            row.operator("lcw.cad_analyze", text="Analyze", icon="VIEWZOOM")
            row.operator("lcw.cad_reconstruct", text="Reconstruct Selected Operations", icon="MOD_REMESH")
            if running:
                box.operator("lcw.cad_cancel", icon="CANCEL")
            box.label(text=state.analysis_summary[:80], icon="INFO")
            box.label(text=state.progress[:80])

        box = layout.box()
        box.label(text="Result Status Overlay", icon="SHADING_WIRE")
        row = box.row(align=True)
        row.operator("lcw.cad_object_colors", text="Show", icon="HIDE_OFF", depress=status_overlay.is_enabled(context.space_data))
        row.operator("lcw.cad_hide_object_colors", text="Hide", icon="HIDE_ON", depress=not status_overlay.is_enabled(context.space_data))
        box.label(text="CAD results only; viewport shading unchanged.", icon="INFO")

        box = _section(layout, state, "results_section_open", "Results", "OUTLINER_OB_MESH")
        if box is None:
            return
        box.label(text=f"{len(state.results)} recorded result(s)")
        for index in range(len(state.results) - 1, max(-1, len(state.results) - 21), -1):
            item = state.results[index]
            result_box = box.box()
            icon = "CHECKMARK" if item.status == "PASS" else "ERROR" if item.status == "FAIL" else "INFO"
            display_status = "PARTIAL / REVIEW" if item.partial else item.status
            result_box.label(text=f"{item.source.name if item.source else 'Missing source'}: {display_status}", icon=icon)
            if item.partial:
                result_box.label(text="Geometry valid; review the incomplete optimization.")
                if item.summary:
                    result_box.label(text=item.summary[:80])
            elif item.status == "PASS":
                result_box.label(text="Geometry PASS / coverage requires review")
            elif item.reason:
                result_box.label(text=f"Stage: {item.stage}")
                for start in range(0, min(len(item.reason), 240), 80):
                    result_box.label(text=item.reason[start:start + 80])
            row = result_box.row(align=True)
            row.operator("lcw.cad_select_source", text="Source").result_index = index
            row.operator("lcw.cad_open_run", text="Run Files").result_index = index
            if item.status != "PASS":
                row.operator("lcw.cad_reconstruct", text="Retry").retry_index = index
