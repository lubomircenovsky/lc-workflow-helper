from __future__ import annotations

import bpy

from ..constants import ACTION_MAP
from ..utils.common import scene_state, wm_state


def _operator_callable(operator_id: str):
    namespace, operator_name = operator_id.split(".")
    return getattr(getattr(bpy.ops, namespace), operator_name)


def favorite_action_available(action_id: str) -> bool:
    definition = ACTION_MAP.get(action_id)
    if definition is None or not definition.allow_favorite:
        return False
    try:
        return _operator_callable(definition.operator).poll()
    except (AttributeError, RuntimeError):
        return False


def _invoke_operator(operator_id: str, kwargs: dict) -> set[str]:
    operator_callable = _operator_callable(operator_id)
    return operator_callable("INVOKE_DEFAULT", **kwargs)


def _build_live_action_kwargs(context: bpy.types.Context, action_id: str) -> dict:
    state = wm_state(context)

    if action_id == "shape_keys.set_value":
        return {"value": state.shape_key_value}
    if action_id == "shape_keys.set_active_phrase":
        return {"phrase": state.shape_key_select_fragment}
    if action_id == "shape_keys.add_prefix":
        return {"prefix": state.shape_key_prefix}
    if action_id == "shape_keys.replace_words":
        return {"search_text": state.shape_key_search, "replace_text": state.shape_key_replace}
    if action_id == "shape_keys.reset_by_phrases":
        return {"phrases": state.shape_key_phrases}
    if action_id == "shape_keys.deselect_phrase":
        return {"phrase": state.shape_key_deselect_fragment}
    if action_id == "shape_keys.preview_partial":
        return {
            "partial_names": state.shape_key_animation_names,
            "start_frame": state.shape_key_animation_start,
            "end_frame": state.shape_key_animation_end,
            "min_value": state.shape_key_animation_min,
            "max_value": state.shape_key_animation_max,
        }
    if action_id == "materials.assign_object":
        return {"material_name": state.material_name}
    if action_id == "materials.assign_faces":
        return {"material_name": state.face_material_name}
    if action_id == "colors.ensure_attribute":
        return {
            "attribute_name": state.color_attribute_name,
            "domain": state.color_attribute_domain,
            "data_type": state.color_attribute_type,
            "replace_existing": state.replace_color_attribute,
            "color": state.color_initialize_value,
        }
    if action_id == "colors.apply":
        return {
            "color": state.color_value,
            "mask_type": state.color_mask_type,
            "blend_mode": state.color_blend_mode,
            "attribute_name": state.color_attribute_name,
        }
    if action_id in {"uv.add_uv1", "uv.add_uv2", "uv.add_uv3"}:
        return {"channel_name": state.uv_add_channel_name}
    if action_id == "uv.rename_uv1":
        return {"new_name": state.uv_rename_uv1}
    if action_id == "uv.rename_uv2":
        return {"new_name": state.uv_rename_uv2}
    if action_id == "uv.rename_uv3":
        return {"new_name": state.uv_rename_uv3}
    if action_id == "mesh.offset_y":
        return {
            "base_offset": state.object_offset_y,
            "use_axis_x": state.mesh_offset_axis_x,
            "use_axis_y": state.mesh_offset_axis_y,
            "use_axis_z": state.mesh_offset_axis_z,
        }
    if action_id == "mesh.rename_suffix":
        return {"zfill_width": state.rename_suffix_width}
    if action_id == "kalibra.export_selection_csv":
        return {"filepath": state.kalibra_export_csv}
    if action_id == "kalibra.create_bbox":
        return {"bbox_name": state.kalibra_bbox_name, "csv_path": state.kalibra_bbox_csv}
    if action_id == "kalibra.create_glass_control":
        return {
            "search_text": state.kalibra_glass_search,
            "replace_text": state.kalibra_glass_replace,
            "angle_threshold": state.kalibra_angle_threshold,
        }
    if action_id == "kalibra.scale_loops_xz":
        return {
            "scale_amount": state.kalibra_scale_amount,
            "space_mode": state.kalibra_scale_space,
            "use_axis_x": state.kalibra_scale_axis_x,
            "use_axis_y": state.kalibra_scale_axis_y,
            "use_axis_z": state.kalibra_scale_axis_z,
        }
    if action_id == "kalibra.scale_loops_x":
        return {"scale_amount": state.kalibra_scale_amount}
    if action_id == "kalibra.space_vertices_axis":
        return {"axis": state.kalibra_axis, "falloff_power": state.kalibra_falloff_power}
    return {}


class LCW_OT_favorite_toggle(bpy.types.Operator):
    bl_idname = "lcw.favorite_toggle"
    bl_label = "Toggle Favorite Action"
    bl_description = "Adds or removes this action from the Favorites panel"
    bl_options = {"REGISTER", "UNDO"}

    action_id: bpy.props.StringProperty(name="Action ID", default="")

    def execute(self, context: bpy.types.Context):
        definition = ACTION_MAP.get(self.action_id)
        if definition is None or not definition.allow_favorite:
            self.report({"WARNING"}, "This action cannot be added to favorites.")
            return {"CANCELLED"}

        state = scene_state(context)
        for index, favorite in enumerate(state.favorite_actions):
            if favorite.action_id == self.action_id:
                state.favorite_actions.remove(index)
                self.report({"INFO"}, f"Removed '{definition.label}' from favorites.")
                return {"FINISHED"}

        favorite = state.favorite_actions.add()
        favorite.action_id = self.action_id
        self.report({"INFO"}, f"Added '{definition.label}' to favorites.")
        return {"FINISHED"}


class LCW_OT_favorite_run_action(bpy.types.Operator):
    bl_idname = "lcw.favorite_run_action"
    bl_label = "Run Favorite Action"
    bl_description = "Runs the selected favorite action using the current values from the addon panels"
    bl_options = {"REGISTER", "UNDO"}

    action_id: bpy.props.StringProperty(name="Action ID", default="")

    def execute(self, context: bpy.types.Context):
        definition = ACTION_MAP.get(self.action_id)
        if definition is None or not definition.allow_favorite:
            self.report({"ERROR"}, "Favorite action is no longer available.")
            return {"CANCELLED"}

        if not favorite_action_available(self.action_id):
            self.report({"WARNING"}, f"Favorite '{definition.label}' is not available in the current context.")
            return {"CANCELLED"}

        try:
            result = _invoke_operator(definition.operator, _build_live_action_kwargs(context, self.action_id))
        except RuntimeError as exc:
            self.report({"WARNING"}, f"Could not run favorite '{definition.label}': {exc}")
            return {"CANCELLED"}

        if "CANCELLED" in result:
            self.report({"WARNING"}, f"Could not run favorite '{definition.label}'.")
            return {"CANCELLED"}
        return {"FINISHED"}


CLASSES = (
    LCW_OT_favorite_toggle,
    LCW_OT_favorite_run_action,
)
