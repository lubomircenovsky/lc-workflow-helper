from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import bpy

from ..constants import ADDON_PACKAGE
from ..utils.substance_designer_baker import (
    apply_profile_to_bake_state,
    build_ao_plan,
    build_preview_data,
    default_workspace_root,
    ensure_directory,
    execute_ao_plan,
    export_collection_for_baker,
    get_baker_profile,
    get_export_source,
    parse_baker_info,
    probe_baker_executable,
    run_baker_command,
    timestamp_job_id,
    validate_baker_setup,
    write_json_file,
)


ACTIVE_JOBS: dict[str, dict[str, object]] = {}


def _preferences(context: bpy.types.Context):
    return context.preferences.addons[ADDON_PACKAGE].preferences


def _bake_state(context: bpy.types.Context):
    return context.scene.lcw_scene_state.substance_designer_baker


def _workspace_root(context: bpy.types.Context) -> Path:
    preferences = _preferences(context)
    if preferences.substance_baker_workspace_root.strip():
        return ensure_directory(bpy.path.abspath(preferences.substance_baker_workspace_root))
    return ensure_directory(default_workspace_root(ADDON_PACKAGE))


def _output_root(context: bpy.types.Context) -> Path:
    state = _bake_state(context)
    if state.output_root.strip():
        return ensure_directory(bpy.path.abspath(state.output_root))
    return ensure_directory(_workspace_root(context) / "outputs")


def _selected_collection_scene_name(collection: bpy.types.Collection | None) -> str:
    return collection.name if collection else "scene"


def _sanitize_scene_name(scene_name: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in scene_name).strip("_") or "scene"


def _job_paths(context: bpy.types.Context, job_id: str) -> dict[str, Path]:
    workspace_root = _workspace_root(context)
    job_root = ensure_directory(workspace_root / "jobs" / job_id)
    export_root = ensure_directory(job_root / "export")
    scene_name = _selected_collection_scene_name(_bake_state(context).target_collection)
    export_path = export_root / f"{_sanitize_scene_name(scene_name)}.fbx"
    output_root = ensure_directory(_output_root(context) / _sanitize_scene_name(scene_name))
    log_path = job_root / "bake.log"
    plan_path = job_root / "execution_plan.json"
    return {
        "job_root": job_root,
        "export_path": export_path,
        "output_dir": output_root,
        "log_path": log_path,
        "plan_path": plan_path,
    }


def _active_baker_profile(preferences):
    if not preferences.baker_profiles:
        return None
    index = max(0, min(preferences.active_baker_profile_index, len(preferences.baker_profiles) - 1))
    preferences.active_baker_profile_index = index
    return preferences.baker_profiles[index]


def _sync_profile_selection(state, profile) -> None:
    state.profile_id = profile.name if profile is not None else ""


def _copy_state_to_profile(state, profile) -> None:
    for field_name in (
        "selection_mode",
        "excluded_material_pattern",
        "material_name_contains",
        "excluded_material_exact",
        "output_size_x",
        "output_size_y",
        "output_size_locked",
        "output_format",
        "uv_set",
        "padding_radius",
        "enable_mip_diffusion",
        "anti_aliasing",
        "average_normals",
        "use_lowdef_as_highdef",
        "projection_max_height",
        "projection_max_depth",
        "projection_normalized_distance",
        "projection_cull_backfaces",
        "projection_match_mode",
        "projection_hit_strategy",
        "skew_correction",
        "skew_map_path",
        "projection_skew_map_invert",
        "projection_offset_map_path",
        "secondary_sample_count",
        "secondary_min_distance",
        "secondary_max_distance",
        "secondary_normalized_distance",
        "secondary_spread_angle",
        "secondary_sample_distribution",
        "culling_mode",
        "secondary_mesh_match_mode",
        "normal_map_path",
        "normal_map_space",
        "normal_map_orientation",
        "attenuation",
        "enable_ground_plane",
        "ground_offset",
    ):
        setattr(profile, field_name, getattr(state, field_name))


def _update_export_source_state(state, export_source: dict[str, object]) -> None:
    state.export_source_kind = export_source["kind"]
    state.export_source_name = str(export_source["name"])
    state.export_source_path = str(export_source["path"])
    state.export_source_label = str(export_source["label"])


def _current_export_source(context: bpy.types.Context) -> dict[str, object]:
    state = _bake_state(context)
    collection = state.target_collection
    paths = _job_paths(context, "inspect")
    return get_export_source(collection, paths["export_path"])


def _set_preview_items(state, preview: dict[str, object]) -> None:
    state.preview_items.clear()
    for item in preview["preview_items"]:
        preview_item = state.preview_items.add()
        preview_item.label = item["label"]
        preview_item.detail = item["detail"]
        preview_item.item_kind = item["item_kind"]
        preview_item.included = item["included"]
    state.preview_target_count = int(preview["target_count"])
    state.preview_group_count = int(preview["group_count"])
    state.preview_skipped_count = int(preview["skipped_count"])
    state.preview_message = str(preview["message"])


def _export_and_collect_preview(context: bpy.types.Context) -> tuple[Path, dict[str, object], list[dict[str, str]], dict[str, object]]:
    state = _bake_state(context)
    collection = state.target_collection
    preferences = _preferences(context)
    paths = _job_paths(context, f"preview-{timestamp_job_id()}")

    export_source = export_collection_for_baker(context, collection, paths["export_path"])
    info_result = run_baker_command(
        preferences.substance_baker_executable,
        ["info", "--inputs", str(export_source["path"])],
        cwd=str(paths["job_root"]),
    )
    if info_result.returncode != 0:
        raise RuntimeError(info_result.stderr.strip() or info_result.stdout.strip() or "Failed to inspect the exported FBX.")

    meshes = parse_baker_info(info_result.stdout)
    preview = build_preview_data(meshes, state)
    state.last_export_path = str(export_source["path"])
    _update_export_source_state(state, export_source)
    return Path(export_source["path"]), export_source, meshes, preview


class LCW_UL_baker_profiles(bpy.types.UIList):
    bl_idname = "LCW_UL_baker_profiles"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        layout.prop(item, "name", text="", emboss=False, icon="PRESET")


class LCW_OT_baker_profile_add(bpy.types.Operator):
    bl_idname = "lcw.baker_profile_add"
    bl_label = "Add Baker Profile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = _preferences(context)
        state = _bake_state(context)
        profile = preferences.baker_profiles.add()
        profile.profile_id = uuid.uuid4().hex
        profile.name = f"Baker Profile {len(preferences.baker_profiles)}"
        _copy_state_to_profile(state, profile)
        preferences.active_baker_profile_index = len(preferences.baker_profiles) - 1
        _sync_profile_selection(state, profile)
        self.report({"INFO"}, "Added baker profile from the current baker settings.")
        return {"FINISHED"}


class LCW_OT_baker_profile_remove(bpy.types.Operator):
    bl_idname = "lcw.baker_profile_remove"
    bl_label = "Remove Baker Profile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = _preferences(context)
        state = _bake_state(context)
        profile = _active_baker_profile(preferences)
        if profile is None:
            self.report({"WARNING"}, "No baker profile to remove.")
            return {"CANCELLED"}

        removed_profile_name = profile.name
        preferences.baker_profiles.remove(preferences.active_baker_profile_index)
        preferences.active_baker_profile_index = max(0, preferences.active_baker_profile_index - 1)
        if state.profile_id == removed_profile_name:
            _sync_profile_selection(state, None)
        self.report({"INFO"}, "Removed baker profile.")
        return {"FINISHED"}


class LCW_OT_baker_profile_move(bpy.types.Operator):
    bl_idname = "lcw.baker_profile_move"
    bl_label = "Move Baker Profile"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    def execute(self, context: bpy.types.Context):
        preferences = _preferences(context)
        index = preferences.active_baker_profile_index
        new_index = index - 1 if self.direction == "UP" else index + 1
        if new_index < 0 or new_index >= len(preferences.baker_profiles):
            return {"CANCELLED"}
        preferences.baker_profiles.move(index, new_index)
        preferences.active_baker_profile_index = new_index
        return {"FINISHED"}


class LCW_OT_baker_profile_apply(bpy.types.Operator):
    bl_idname = "lcw.baker_profile_apply"
    bl_label = "Apply Baker Profile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = _preferences(context)
        state = _bake_state(context)
        profile = get_baker_profile(preferences, state.profile_id)
        if profile is None:
            self.report({"WARNING"}, "Select a baker profile first.")
            return {"CANCELLED"}

        apply_profile_to_bake_state(profile, state)
        _sync_profile_selection(state, profile)
        self.report({"INFO"}, f"Applied baker profile '{profile.name}'.")
        return {"FINISHED"}


class LCW_OT_baker_profile_capture(bpy.types.Operator):
    bl_idname = "lcw.baker_profile_capture"
    bl_label = "Save Current Settings To Profile"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = _preferences(context)
        state = _bake_state(context)
        profile = get_baker_profile(preferences, state.profile_id)
        if profile is None:
            self.report({"WARNING"}, "Select a baker profile first.")
            return {"CANCELLED"}

        _copy_state_to_profile(state, profile)
        _sync_profile_selection(state, profile)
        self.report({"INFO"}, f"Updated baker profile '{profile.name}' from the current settings.")
        return {"FINISHED"}


class LCW_OT_sdb_validate(bpy.types.Operator):
    bl_idname = "lcw.sdb_validate"
    bl_label = "Validate"
    bl_description = "Validate the current Substance Designer baker setup"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context):
        state = _bake_state(context)
        preferences = _preferences(context)
        export_source = _current_export_source(context)
        _update_export_source_state(state, export_source)
        errors, warnings = validate_baker_setup(preferences.substance_baker_executable, state.target_collection, preferences)
        probe_ok, probe_message = probe_baker_executable(preferences.substance_baker_executable)
        if not probe_ok:
            errors.append(probe_message)
        if warnings:
            state.job_message = " | ".join(warnings)
        if errors:
            state.job_status = "FAILED"
            self.report({"ERROR"}, " | ".join(errors[:3]))
            return {"CANCELLED"}

        state.job_status = "VALID"
        state.job_message = f"Validation succeeded. {state.export_source_label}"
        self.report({"INFO"}, "Substance Designer baker setup is valid.")
        return {"FINISHED"}


class LCW_OT_sdb_preview_targets(bpy.types.Operator):
    bl_idname = "lcw.sdb_preview_targets"
    bl_label = "Preview Targets"
    bl_description = "Export the selected collection, inspect it with the Substance baker, and preview bake targets"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context):
        state = _bake_state(context)
        preferences = _preferences(context)
        errors, _warnings = validate_baker_setup(preferences.substance_baker_executable, state.target_collection, preferences)
        if errors:
            state.job_status = "FAILED"
            state.job_message = " | ".join(errors)
            self.report({"ERROR"}, state.job_message)
            return {"CANCELLED"}

        try:
            _export_path, _export_source, _meshes, preview = _export_and_collect_preview(context)
        except Exception as exc:
            state.job_status = "FAILED"
            state.job_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        _set_preview_items(state, preview)
        state.job_status = "PREVIEW_READY"
        state.job_message = f"{state.preview_message} {state.export_source_label}"
        self.report({"INFO"}, state.preview_message)
        return {"FINISHED"}


class LCW_OT_sdb_bake_ao(bpy.types.Operator):
    bl_idname = "lcw.sdb_bake_ao"
    bl_label = "Export + Bake AO"
    bl_description = "Export the selected collection and bake ambient occlusion through Substance Designer baker"
    bl_options = {"REGISTER"}

    _timer = None
    _job_id = ""

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        job_data = ACTIVE_JOBS.get(self._job_id)
        if not job_data:
            return {"CANCELLED"}

        thread = job_data["thread"]
        if thread.is_alive():
            return {"PASS_THROUGH"}

        context.window_manager.event_timer_remove(self._timer)
        state = _bake_state(context)
        result = job_data["result"]
        state.last_log_path = str(result["log_path"])
        state.last_output_dir = str(result["output_dir"])
        state.last_summary = str(result["message"])
        state.job_status = "SUCCEEDED" if result["success"] else "FAILED"
        state.job_message = str(result["message"])
        ACTIVE_JOBS.pop(self._job_id, None)

        if result["success"]:
            self.report({"INFO"}, result["message"])
            return {"FINISHED"}

        self.report({"ERROR"}, result["message"])
        return {"CANCELLED"}

    def execute(self, context: bpy.types.Context):
        state = _bake_state(context)
        preferences = _preferences(context)
        errors, _warnings = validate_baker_setup(preferences.substance_baker_executable, state.target_collection, preferences)
        if errors:
            state.job_status = "FAILED"
            state.job_message = " | ".join(errors)
            self.report({"ERROR"}, state.job_message)
            return {"CANCELLED"}

        try:
            export_path, _export_source, _meshes, preview = _export_and_collect_preview(context)
        except Exception as exc:
            state.job_status = "FAILED"
            state.job_message = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        _set_preview_items(state, preview)
        if preview["group_count"] == 0:
            state.job_status = "FAILED"
            state.job_message = preview["message"]
            self.report({"ERROR"}, preview["message"])
            return {"CANCELLED"}

        job_id = f"ao-{timestamp_job_id()}-{uuid.uuid4().hex[:8]}"
        paths = _job_paths(context, job_id)
        plan = build_ao_plan(
            scene_name=export_path.stem,
            fbx_path=export_path,
            output_dir=paths["output_dir"],
            preferences=preferences,
            state=state,
            groups=preview["groups"],
        )
        write_json_file(paths["plan_path"], plan)

        result_holder = {
            "success": False,
            "message": "Bake did not start.",
            "baked_files": [],
            "log_path": str(paths["log_path"]),
            "output_dir": str(paths["output_dir"]),
        }

        def _run_job():
            result_holder.update(execute_ao_plan(plan, preferences.substance_baker_executable, paths["log_path"]))

        thread = threading.Thread(target=_run_job, daemon=True)
        thread.start()

        state.last_job_id = job_id
        state.last_plan_path = str(paths["plan_path"])
        state.last_export_path = str(export_path)
        state.last_output_dir = str(paths["output_dir"])
        state.last_log_path = str(paths["log_path"])
        state.job_status = "RUNNING"
        state.job_message = "AO bake is running..."

        ACTIVE_JOBS[job_id] = {"thread": thread, "result": result_holder}
        self._job_id = job_id
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}


class LCW_OT_sdb_open_output_folder(bpy.types.Operator):
    bl_idname = "lcw.sdb_open_output_folder"
    bl_label = "Open Output Folder"
    bl_description = "Open the last AO output folder"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context):
        state = _bake_state(context)
        if not state.last_output_dir or not Path(state.last_output_dir).exists():
            self.report({"WARNING"}, "No output folder is available yet.")
            return {"CANCELLED"}
        os.startfile(state.last_output_dir)
        return {"FINISHED"}


class LCW_OT_sdb_show_last_log(bpy.types.Operator):
    bl_idname = "lcw.sdb_show_last_log"
    bl_label = "Show Last Log"
    bl_description = "Open the last bake log"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context):
        state = _bake_state(context)
        if not state.last_log_path or not Path(state.last_log_path).exists():
            self.report({"WARNING"}, "No bake log is available yet.")
            return {"CANCELLED"}
        os.startfile(state.last_log_path)
        return {"FINISHED"}


CLASSES = (
    LCW_UL_baker_profiles,
    LCW_OT_baker_profile_add,
    LCW_OT_baker_profile_remove,
    LCW_OT_baker_profile_move,
    LCW_OT_baker_profile_apply,
    LCW_OT_baker_profile_capture,
    LCW_OT_sdb_validate,
    LCW_OT_sdb_preview_targets,
    LCW_OT_sdb_bake_ao,
    LCW_OT_sdb_open_output_folder,
    LCW_OT_sdb_show_last_log,
)
