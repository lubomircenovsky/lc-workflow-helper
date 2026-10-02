from __future__ import annotations

import bpy

from . import jobs, status_overlay, ui_text


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
        running = jobs.ACTIVE_JOB is not None or state.analysis_running
        busy = running or state.cleanup_running
        auto = state.workflow_mode == "AUTO"
        switch = layout.row(align=True)
        switch.enabled = not busy
        switch.prop(state, "workflow_mode", expand=True)

        box = _section(layout, state, "input_section_open", "Input", "OUTLINER_COLLECTION")
        if box is not None:
            controls = box.column(align=True)
            controls.enabled = not busy
            controls.prop(state, "mode", expand=True)
            if state.mode == "COLLECTION":
                controls.prop(state, "input_collection")
                if not auto:controls.prop(state, "output_collection")
            else:
                count = sum(obj.type == "MESH" for obj in context.selected_objects)
                controls.label(text=f"Selected mesh objects: {count}", icon="OUTLINER_OB_MESH")
            if not auto:controls.prop(state, "run_root")

        if auto:
            box = layout.box()
            controls = box.column(align=True)
            controls.enabled = not busy
            controls.prop(state, "auto_hole_detail_factor", slider=True)
            controls.prop(state, "auto_perimeter_clearance_mm")
            controls.prop(state, "auto_epsilon_mm")
            controls.prop(state, "auto_hole_epsilon_mm")
            for line in ui_text.lines("Auto chooses fewer polygons; support loops may be omitted."):
                box.label(text=line, icon="INFO")
        else:
            box = _section(layout, state, "options_section_open", "Reconstruction Options", "MOD_REMESH")
            if box is not None:
                controls = box.column(align=True)
                controls.enabled = not busy
                controls.prop(state, "epsilon_mm")
                holes = controls.split(factor=0.5, align=True)
                holes.prop(state, "circular_holes", text="Circular Holes", toggle=True)
                field = holes.row(align=True)
                field.enabled = state.circular_holes and not state.preserve_curve_segmentation
                field.prop(state, "hole_detail_factor", text="Detail", slider=True)
                deviation = controls.row(align=True)
                deviation.enabled = state.circular_holes and not state.preserve_curve_segmentation
                deviation.prop(state, "hole_epsilon_mm")
                perimeter = controls.split(factor=0.5, align=True)
                perimeter.prop(state, "perimeter_loops", text="Perimeter Loops", toggle=True)
                field = perimeter.row(align=True)
                field.enabled = state.perimeter_loops
                field.prop(state, "perimeter_clearance_mm", text="Clearance (mm)")
                for left, left_label, right, right_label in (
                        ("arcs", "Arcs", "outer_cylinders", "Outer Cylinders"),
                        ("background_cleanup", "Planar Cleanup", "straight_walls", "Straight Walls")):
                    row = controls.row(align=True)
                    row.prop(state, left, text=left_label, toggle=True)
                    row.prop(state, right, text=right_label, toggle=True)
                controls.prop(state, "preserve_curve_segmentation", text="Keep Curve Segments", toggle=True)
                controls.prop(state, "separate_solids", toggle=True)
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
            if auto:
                advanced = _section(box, state, "auto_run_settings_open", "Run Settings", "PREFERENCES")
                if advanced is not None:
                    controls = advanced.column(align=True)
                    controls.enabled = not busy
                    controls.prop(state, "run_root")
                    controls.prop(state, "concurrent_workers")
                    controls.prop(state, "worker_timeout_minutes")
                action = box.row()
                action.enabled = not busy
                action.operator("lcw.cad_reconstruct", text="Analyze & Reconstruct", icon="MOD_REMESH")
                if running:box.operator("lcw.cad_cancel", icon="CANCEL")
            else:
                worker_row = box.column(align=True)
                worker_row.enabled = not busy
                worker_row.prop(state, "concurrent_workers")
                worker_row.prop(state, "worker_timeout_minutes")
                if state.concurrent_workers >= 8:
                    box.label(text="8+ Blender processes can exhaust RAM.", icon="ERROR")
                row = box.row(align=True)
                row.enabled = not busy
                row.operator("lcw.cad_analyze", text="Analyze", icon="VIEWZOOM")
                row.operator("lcw.cad_reconstruct", text="Reconstruct", icon="MOD_REMESH")
                box.label(text="Non-manifold junctions: automatic guarded mode.", icon="INFO")
                if running:
                    box.operator("lcw.cad_cancel", icon="CANCEL")
                analysis = box.box()
                analysis.label(text="Last Analysis", icon="VIEWZOOM")
                if state.analysis_running:
                    analysis.label(text="Checking geometry and screening profiles...", icon="TIME")
                elif not state.analysis_ready:
                    analysis.label(text="Not checked yet. Select input, then Analyze.")
                else:
                    mesh_label = "mesh" if state.analysis_meshes == 1 else "meshes"
                    analysis.label(text=f"{state.analysis_meshes} {mesh_label} | {state.analysis_blockers} blocked | "
                                        f"{state.analysis_notes} notes",
                                   icon="ERROR" if state.analysis_blockers else "CHECKMARK")
                    count = len(state.analysis_lines)
                    visible = count if state.analysis_details_open else min(count, 3)
                    for index in range(visible):
                        item = state.analysis_lines[index]
                        for line in ui_text.lines(item.message):
                            analysis.label(text=line, icon="ERROR" if item.severity == "BLOCKER" else "INFO")
                        if item.recommendation:
                            action = analysis.row()
                            action.enabled = not busy
                            action.operator("lcw.cad_apply_recommendation", text="Use Suggested Settings").analysis_index = index
                        if item.run_dir and state.analysis_details_open:
                            analysis.operator("lcw.cad_open_analysis", text="Analysis Files", icon="FILE_FOLDER").analysis_index = index
                    if count > 3:
                        analysis.prop(state, "analysis_details_open", text="Show all notes" if not state.analysis_details_open
                                      else "Hide extra notes", toggle=True)
            progress = box.box()
            progress.label(text="Progress", icon="TIME")
            for part in state.progress.split(" | "):
                for line in ui_text.lines(part):
                    progress.label(text=line)
            if state.cleanup_running or state.cleanup_progress:
                box.label(text=state.cleanup_progress, icon="FILE_FOLDER")

        box = _section(layout, state, "uv_prep_section_open", "UV Preparation", "GROUP_UVS")
        if box is not None:
            box.label(text="Selected meshes; no CAD run required.", icon="INFO")
            settings = box.column(align=True)
            settings.enabled = not busy
            settings.prop(state, "uv_prep_map_name")
            settings.prop(state, "uv_prep_margin")
            settings.prop(state, "uv_prep_angle_degrees")
            actions = settings.row(align=True)
            actions.operator("lcw.cad_analyze_uv", text="Analyze", icon="VIEWZOOM")
            actions.operator("lcw.cad_prepare_uv", text="Generate UV", icon="GROUP_UVS")
            box.label(text="Old UV maps and mesh seams stay unchanged.", icon="INFO")
            for line in ui_text.lines(state.uv_prep_summary):
                box.label(text=line)

        box = layout.box()
        box.label(text="Result Status Colors", icon="SHADING_SOLID")
        row = box.row(align=True)
        row.operator("lcw.cad_object_colors", text="Show", icon="HIDE_OFF", depress=status_overlay.is_enabled(context.space_data))
        row.operator("lcw.cad_hide_object_colors", text="Hide", icon="HIDE_ON", depress=not status_overlay.any_enabled())
        box.label(text="Hide restores your prior viewport colors.", icon="INFO")

        box = _section(layout, state, "results_section_open", "Results", "OUTLINER_OB_MESH")
        if box is None:
            return
        box.label(text=f"{len(state.results)} result(s) saved in this .blend")
        actions = box.row(align=True)
        actions.enabled = not running and not state.cleanup_running and bool(state.results)
        actions.operator("lcw.cad_archive_results", text="Archive & Clear", icon="TEXT")
        actions.operator("lcw.cad_clear_results", text="Clear Results", icon="X")
        delete_row = box.row(align=True)
        delete_row.enabled = not running and not state.cleanup_running
        delete_row.operator("lcw.cad_delete_run_files", text="Delete Run Files", icon="TRASH")
        box.label(text="Run files: current Run Folder only. Meshes stay.", icon="INFO")
        for index in range(len(state.results) - 1,
                           max(-1, len(state.results) - state.results_visible - 1), -1):
            item = state.results[index]
            result_box = box.box()
            icon = "CHECKMARK" if item.status == "PASS" else "ERROR" if item.status == "FAIL" else "INFO"
            display_status = "PARTIAL / REVIEW" if item.partial and item.status == "REVIEW" else item.status
            header = result_box.row(align=True)
            header.prop(item, "details_open", text="", emboss=False,
                        icon="TRIA_DOWN" if item.details_open else "TRIA_RIGHT")
            header.label(text=f"{item.source_label or (item.source.name if item.source else 'Missing source')}: {display_status}", icon=icon)
            for line in ui_text.lines(ui_text.result_brief(item)):
                result_box.label(text=line)
            if item.metrics_summary and item.status in {"PASS", "REVIEW"}:
                for line in ui_text.lines(item.metrics_summary):
                    result_box.label(text=line)
            if item.strategy_summary:
                for line in ui_text.lines(item.strategy_summary):
                    result_box.label(text=line)
            if not item.details_open:
                continue
            if item.status == "RUNNING":
                result_box.label(text=item.stage or "Working")
            for detail in (item.perimeter_summary, item.planar_summary):
                if detail:
                    for line in ui_text.lines(detail):
                        result_box.label(text=line)
            if item.status == "REVIEW" and item.reason:
                for line in ui_text.lines(item.reason):
                    result_box.label(text=line)
            if item.status == "FAIL":
                result_box.label(text=f"Stage: {item.stage or 'worker'}")
                detail = item.technical_reason or item.reason
                if detail:
                    for line in ui_text.lines(detail):
                        result_box.label(text=line)
            if item.files_deleted:
                result_box.label(text="Run files deleted.", icon="INFO")
            row = result_box.row(align=True)
            row.enabled = item.status not in {"PENDING", "RUNNING"}
            row.operator("lcw.cad_select_source", text="Source").result_index = index
            files = row.row(align=True)
            files.enabled = not item.files_deleted
            files.operator("lcw.cad_open_run", text="Run Files").result_index = index
            if item.status in {"FAIL", "REVIEW"}:
                row.operator("lcw.cad_reconstruct", text="Retry").retry_index = index
        if len(state.results) > state.results_visible:
            box.operator("lcw.cad_more_results", text="Show 5 More", icon="ADD")
