from __future__ import annotations

import bpy


def _section(layout, state, property_name: str, label: str, icon: str):
    row = layout.row(align=True)
    is_open = getattr(state, property_name)
    row.prop(
        state,
        property_name,
        text="",
        emboss=False,
        icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
    )
    row.label(text=label, icon=icon)
    return layout.box() if is_open else None


class LCW_UL_quad_analysis_results(bpy.types.UIList):
    bl_idname = "LCW_UL_quad_analysis_results"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index=0,
        flt_flag=0,
    ):
        row = layout.row(align=True)
        status_icon = "CHECKMARK" if item.fingerprint_unchanged else "ERROR"
        row.label(text=item.source_object_name, icon=status_icon)
        row.label(text=item.classification.replace("_", " ").title())
        row.label(text=f"T {item.triangle_count} / Q {item.quad_count}")
        if item.status == "RECONSTRUCTED":
            row.label(text=f"{item.confidence_label} {item.confidence_score:.0f}")
        else:
            row.label(text=f"R {item.region_count}")


class LCW_PT_quad_reconstruction(bpy.types.Panel):
    bl_idname = "LCW_PT_quad_reconstruction"
    bl_label = "Quad Reconstruction"
    bl_parent_id = "LCW_PT_root"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LC Workflow"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = context.scene.lcw_quad_reconstruction

        settings = _section(layout, state, "settings_section_open", "Settings", "MOD_TRIANGULATE")
        if settings:
            settings.prop(state, "input_collection")
            settings.prop(state, "output_collection")
            settings.prop(state, "profile")
            settings.prop(state, "solver_backend")
            if state.profile == "STRICT":
                settings.label(text="Strict: protected data are hard constraints.", icon="LOCKED")
            elif state.profile == "BALANCED":
                settings.label(
                    text="Balanced: materials stay hard; UV/seam/sharp relaxations are reported.",
                    icon="INFO",
                )
            elif state.profile == "AGGRESSIVE":
                settings.label(
                    text="Aggressive: maximize hard-valid coverage and mark relaxations.",
                    icon="ERROR",
                )
            protection = settings.box()
            protection.label(text="Protected Boundaries", icon="LOCKED")
            row = protection.row(align=True)
            material_control = row.row(align=True)
            material_control.enabled = state.profile == "AGGRESSIVE"
            material_control.prop(state, "protect_materials")
            uv_control = row.row(align=True)
            uv_control.enabled = state.profile not in {"STRICT", "ANALYZE_ONLY"}
            uv_control.prop(state, "protect_uv")
            row = protection.row(align=True)
            seam_control = row.row(align=True)
            seam_control.enabled = state.profile not in {"STRICT", "ANALYZE_ONLY"}
            seam_control.prop(state, "protect_seams")
            sharp_control = row.row(align=True)
            sharp_control.enabled = state.profile not in {"STRICT", "ANALYZE_ONLY"}
            sharp_control.prop(state, "protect_sharp_edges")
            settings.prop(state, "process_open_meshes")
            settings.prop(state, "process_true_non_manifold_regions")
            settings.prop(state, "preserve_existing_quads")
            settings.prop(state, "run_subdivision_validation")
            settings.prop(state, "create_face_diagnostics")

        advanced = _section(layout, state, "advanced_section_open", "Advanced", "PREFERENCES")
        if advanced:
            advanced.prop(state, "uv_tolerance")
            advanced.prop(state, "area_tolerance")
            advanced.prop(state, "max_warp")
            advanced.prop(state, "exact_component_limit")
            advanced.prop(state, "maximum_iterations")
            advanced.prop(state, "parallel_core_processing")
            parallel = advanced.column(align=True)
            parallel.enabled = state.parallel_core_processing
            parallel.prop(state, "parallel_worker_count")
            parallel.prop(state, "parallel_triangle_threshold")
            advanced.prop(state, "topology_influence")
            weights = _section(
                advanced,
                state,
                "weights_section_open",
                "Scoring Weights",
                "DRIVER_DISTANCE",
            )
            if weights:
                grid = weights.grid_flow(columns=2, align=True)
                for property_name in (
                    "weight_planarity",
                    "weight_corner",
                    "weight_aspect",
                    "weight_opposite_edge",
                    "weight_diagonal_balance",
                    "weight_flow",
                    "weight_curvature",
                    "weight_valence",
                    "weight_uv",
                    "weight_seam_or_sharp",
                    "weight_material",
                    "weight_attribute",
                ):
                    grid.prop(state, property_name)
            advanced.prop(state, "debug_logging")

        action_box = layout.box()
        row = action_box.row(align=True)
        if state.active_run_id:
            row.operator(
                "lcw.quad_reconstruction_cancel",
                text="Cancel Active Run",
                icon="CANCEL",
            )
        else:
            row.operator(
                "lcw.quad_reconstruction_analyze_modal",
                text="Analyze",
                icon="VIEWZOOM",
            )
            reconstruct = row.row(align=True)
            reconstruct.enabled = state.profile != "ANALYZE_ONLY"
            reconstruct.operator(
                "lcw.quad_reconstruction_reconstruct_modal",
                text="Reconstruct",
                icon="MOD_TRIANGULATE",
            )
        action_box.prop(state, "progress", text="Progress", slider=True)
        if state.progress_label:
            action_box.label(text=state.progress_label, icon="TIME")
        action_box.label(text=f"Status: {state.job_status.replace('_', ' ').title()}")
        if state.job_message:
            action_box.label(text=state.job_message, icon="INFO")
        if state.last_report_text_name:
            action_box.label(text=f"Text Report: {state.last_report_text_name}", icon="TEXT")
            action_box.operator(
                "lcw.quad_reconstruction_export_report",
                text="Export Report JSON",
                icon="EXPORT",
            )

        results = _section(layout, state, "results_section_open", "Results", "PRESET")
        if results:
            if not state.results:
                results.label(text="Run Analyze to inspect the input collection.", icon="INFO")
                return
            results.template_list(
                "LCW_UL_quad_analysis_results",
                "",
                state,
                "results",
                state,
                "active_result_index",
                rows=min(10, max(4, len(state.results))),
            )
            index = min(state.active_result_index, len(state.results) - 1)
            item = state.results[index]
            details = results.box()
            details.label(text=item.source_mesh_name, icon="MESH_DATA")
            details.label(text=item.details)
            details.label(
                text="Source fingerprint unchanged"
                if item.fingerprint_unchanged
                else "Source fingerprint verification failed",
                icon="CHECKMARK" if item.fingerprint_unchanged else "ERROR",
            )
            details.label(text=f"Runtime: {item.runtime_seconds:.4f} s")
            if item.output_object is not None:
                details.label(text=f"Output: {item.output_object.name}", icon="OBJECT_DATA")
                details.label(text=f"Coverage: {item.coverage:.1%}")
                solver_icon = "CHECKMARK" if item.solver_exact else "INFO"
                details.label(
                    text=f"Solver: {item.solver_backend} ({'exact' if item.solver_exact else 'fallback'})",
                    icon=solver_icon,
                )
                details.label(
                    text=f"Confidence: {item.confidence_label} ({item.confidence_score:.1f}/100)",
                    icon="SOLO_ON" if item.confidence_label == "HIGH" else "INFO",
                )
                details.label(text=f"Relaxations: {item.relaxation_count}")
                row = details.row(align=True)
                row.operator(
                    "lcw.quad_reconstruction_focus_output",
                    text="Focus Output",
                    icon="VIEWZOOM",
                )
                row.operator(
                    "lcw.quad_reconstruction_select_problem_faces",
                    text="Select Problem Faces",
                    icon="FACESEL",
                )
            actions = results.row(align=True)
            actions.operator(
                "lcw.quad_reconstruction_validate_outputs",
                text="Validate Outputs",
                icon="CHECKMARK",
            )
            actions.operator(
                "lcw.quad_reconstruction_clear_results",
                text="Clear Generated Results",
                icon="TRASH",
            )


CLASSES = (
    LCW_UL_quad_analysis_results,
    LCW_PT_quad_reconstruction,
)
