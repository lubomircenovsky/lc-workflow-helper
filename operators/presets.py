from __future__ import annotations

import bpy

from ..constants import ACTION_MAP
from ..utils.common import addon_preferences


ACTION_ARGUMENTS = {
    "shape_keys.set_value": {"value": "float_value"},
    "shape_keys.set_active_phrase": {"phrase": "text_value"},
    "shape_keys.add_prefix": {"prefix": "text_value"},
    "shape_keys.replace_words": {"search_text": "text_value", "replace_text": "text_value_2"},
    "shape_keys.reset_by_phrases": {"phrases": "list_value"},
    "shape_keys.deselect_phrase": {"phrase": "text_value"},
    "materials.assign_object": {"material_name": "text_value"},
    "materials.assign_faces": {"material_name": "text_value"},
    "colors.ensure_attribute": {
        "attribute_name": "text_value",
        "domain": "color_domain",
        "data_type": "color_type",
        "replace_existing": "bool_value",
        "color": "color_value",
    },
    "colors.apply": {
        "color": "color_value",
        "mask_type": "color_mask",
        "blend_mode": "color_blend",
        "attribute_name": "text_value",
    },
    "uv.add_uv1": {"channel_name": "text_value"},
    "uv.add_uv2": {"channel_name": "text_value"},
    "uv.add_uv3": {"channel_name": "text_value"},
    "uv.rename_uv1": {"new_name": "text_value"},
    "uv.rename_uv2": {"new_name": "text_value"},
    "uv.rename_uv3": {"new_name": "text_value"},
    "mesh.offset_y": {"base_offset": "float_value"},
    "mesh.rename_suffix": {"zfill_width": "int_value"},
    "kalibra.export_selection_csv": {"filepath": "filepath_value"},
    "kalibra.create_bbox": {"bbox_name": "text_value", "csv_path": "filepath_value"},
    "kalibra.create_glass_control": {
        "search_text": "text_value",
        "replace_text": "text_value_2",
        "angle_threshold": "float_value",
    },
    "kalibra.scale_loops_xz": {"scale_amount": "float_value"},
    "kalibra.scale_loops_x": {"scale_amount": "float_value"},
    "kalibra.space_vertices_axis": {"axis": "axis_value", "falloff_power": "float_value"},
}


def _active_preset(preferences):
    if not preferences.presets:
        return None
    index = max(0, min(preferences.active_preset_index, len(preferences.presets) - 1))
    preferences.active_preset_index = index
    return preferences.presets[index]


def _invoke_operator(operator_id: str, kwargs: dict) -> set[str]:
    namespace, operator_name = operator_id.split(".")
    operator_callable = getattr(getattr(bpy.ops, namespace), operator_name)
    return operator_callable("EXEC_DEFAULT", **kwargs)


def _build_action_kwargs(action) -> dict:
    mapping = ACTION_ARGUMENTS.get(action.action_id, {})
    return {target_name: getattr(action, source_name) for target_name, source_name in mapping.items()}


class LCW_UL_workflow_presets(bpy.types.UIList):
    bl_idname = "LCW_UL_workflow_presets"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        layout.prop(item, "name", text="", emboss=False, icon="PRESET")


class LCW_UL_workflow_actions(bpy.types.UIList):
    bl_idname = "LCW_UL_workflow_actions"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        action_definition = ACTION_MAP.get(item.action_id)
        label = item.label_override or (action_definition.label if action_definition else item.action_id)
        layout.label(text=label, icon="PLAY")


class LCW_OT_workflow_preset_add(bpy.types.Operator):
    bl_idname = "lcw.workflow_preset_add"
    bl_label = "Add Workflow Preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = preferences.presets.add()
        preset.name = f"Preset {len(preferences.presets)}"
        preferences.active_preset_index = len(preferences.presets) - 1
        self.report({"INFO"}, "Added workflow preset.")
        return {"FINISHED"}


class LCW_OT_workflow_preset_remove(bpy.types.Operator):
    bl_idname = "lcw.workflow_preset_remove"
    bl_label = "Remove Workflow Preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = _active_preset(preferences)
        if preset is None:
            self.report({"WARNING"}, "No preset to remove.")
            return {"CANCELLED"}
        preferences.presets.remove(preferences.active_preset_index)
        preferences.active_preset_index = max(0, preferences.active_preset_index - 1)
        self.report({"INFO"}, "Removed workflow preset.")
        return {"FINISHED"}


class LCW_OT_workflow_preset_move(bpy.types.Operator):
    bl_idname = "lcw.workflow_preset_move"
    bl_label = "Move Workflow Preset"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        index = preferences.active_preset_index
        new_index = index - 1 if self.direction == "UP" else index + 1
        if new_index < 0 or new_index >= len(preferences.presets):
            return {"CANCELLED"}
        preferences.presets.move(index, new_index)
        preferences.active_preset_index = new_index
        return {"FINISHED"}


class LCW_OT_workflow_action_add(bpy.types.Operator):
    bl_idname = "lcw.workflow_action_add"
    bl_label = "Add Workflow Action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = _active_preset(preferences)
        if preset is None:
            self.report({"WARNING"}, "Create a preset first.")
            return {"CANCELLED"}
        action = preset.actions.add()
        action.action_id = next(iter(ACTION_MAP))
        action.text_value = "Color" if action.action_id == "colors.ensure_attribute" else ""
        preset.active_action_index = len(preset.actions) - 1
        self.report({"INFO"}, "Added workflow action.")
        return {"FINISHED"}


class LCW_OT_workflow_action_remove(bpy.types.Operator):
    bl_idname = "lcw.workflow_action_remove"
    bl_label = "Remove Workflow Action"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = _active_preset(preferences)
        if preset is None or not preset.actions:
            self.report({"WARNING"}, "No action to remove.")
            return {"CANCELLED"}
        preset.actions.remove(preset.active_action_index)
        preset.active_action_index = max(0, preset.active_action_index - 1)
        self.report({"INFO"}, "Removed workflow action.")
        return {"FINISHED"}


class LCW_OT_workflow_action_move(bpy.types.Operator):
    bl_idname = "lcw.workflow_action_move"
    bl_label = "Move Workflow Action"
    bl_options = {"REGISTER", "UNDO"}

    direction: bpy.props.EnumProperty(items=(("UP", "Up", ""), ("DOWN", "Down", "")))

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = _active_preset(preferences)
        if preset is None or not preset.actions:
            return {"CANCELLED"}
        index = preset.active_action_index
        new_index = index - 1 if self.direction == "UP" else index + 1
        if new_index < 0 or new_index >= len(preset.actions):
            return {"CANCELLED"}
        preset.actions.move(index, new_index)
        preset.active_action_index = new_index
        return {"FINISHED"}


class LCW_OT_workflow_preset_run(bpy.types.Operator):
    bl_idname = "lcw.workflow_preset_run"
    bl_label = "Run Workflow Preset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        preferences = addon_preferences(context)
        preset = _active_preset(preferences)
        if preset is None:
            self.report({"WARNING"}, "Create a preset first.")
            return {"CANCELLED"}
        if not preset.actions:
            self.report({"WARNING"}, "Preset has no actions.")
            return {"CANCELLED"}

        for action in preset.actions:
            definition = ACTION_MAP.get(action.action_id)
            if definition is None:
                self.report({"ERROR"}, f"Unknown action '{action.action_id}'.")
                return {"CANCELLED"}
            result = _invoke_operator(definition.operator, _build_action_kwargs(action))
            if "FINISHED" not in result:
                self.report({"ERROR"}, f"Preset stopped on '{definition.label}'.")
                return {"CANCELLED"}

        self.report({"INFO"}, f"Ran preset '{preset.name}'.")
        return {"FINISHED"}


CLASSES = (
    LCW_UL_workflow_presets,
    LCW_UL_workflow_actions,
    LCW_OT_workflow_preset_add,
    LCW_OT_workflow_preset_remove,
    LCW_OT_workflow_preset_move,
    LCW_OT_workflow_action_add,
    LCW_OT_workflow_action_remove,
    LCW_OT_workflow_action_move,
    LCW_OT_workflow_preset_run,
)
