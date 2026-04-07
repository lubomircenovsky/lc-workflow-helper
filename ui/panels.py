from __future__ import annotations

import bpy

from ..constants import ACTION_MAP
from ..utils.common import addon_preferences, wm_state


def _assign_operator_props(operator, values: dict) -> None:
    for name, value in values.items():
        setattr(operator, name, value)


def _tool_box(layout, title: str):
    box = layout.box()
    box.label(text=title)
    return box


def _simple_tool_box(layout: bpy.types.UILayout):
    return layout.box().column(align=False)


def _draw_collapsible_section(
    layout: bpy.types.UILayout,
    state,
    toggle_name: str,
    title: str,
    *,
    icon: str = "DISCLOSURE_TRI_RIGHT",
):
    box = layout.box()
    row = box.row(align=True)
    expanded = getattr(state, toggle_name)
    row.prop(state, toggle_name, text="", emboss=False, icon="TRIA_DOWN" if expanded else "TRIA_RIGHT")
    row.label(text=title, icon=icon)
    if not expanded:
        return None
    return box.column(align=False)


def _draw_collapsible_tool(
    layout: bpy.types.UILayout,
    state,
    toggle_name: str,
    title: str,
    *,
    icon: str = "TOOL_SETTINGS",
):
    box = layout.box()
    row = box.row(align=True)
    expanded = getattr(state, toggle_name)
    row.prop(state, toggle_name, text="", emboss=False, icon="TRIA_DOWN" if expanded else "TRIA_RIGHT")
    row.label(text=title, icon=icon)
    if not expanded:
        return None

    return box.column(align=False)


def _draw_preset_action_settings(layout: bpy.types.UILayout, action) -> None:
    definition = ACTION_MAP.get(action.action_id)
    if definition is None:
        layout.label(text="Unknown action", icon="ERROR")
        return

    layout.prop(action, "action_id", text="Action")
    for param_name in definition.params:
        if param_name == "text_value":
            layout.prop(action, "text_value", text="Text")
        elif param_name == "text_value_2":
            layout.prop(action, "text_value_2", text="Text 2")
        elif param_name == "text_value_3":
            layout.prop(action, "text_value_3", text="Text 3")
        elif param_name == "list_value":
            layout.prop(action, "list_value", text="Comma Separated")
        elif param_name == "float_value":
            layout.prop(action, "float_value")
        elif param_name == "float_value_2":
            layout.prop(action, "float_value_2")
        elif param_name == "int_value":
            layout.prop(action, "int_value")
        elif param_name == "int_value_2":
            layout.prop(action, "int_value_2")
        elif param_name == "bool_value":
            layout.prop(action, "bool_value")
        elif param_name == "filepath_value":
            layout.prop(action, "filepath_value")
        elif param_name == "color_value":
            layout.prop(action, "color_value")
        elif param_name == "color_domain":
            layout.prop(action, "color_domain", text="Color Domain")
        elif param_name == "color_type":
            layout.prop(action, "color_type", text="Color Type")
        elif param_name == "color_mask":
            layout.prop(action, "color_mask", text="Mask Type")
        elif param_name == "color_blend":
            layout.prop(action, "color_blend", text="Blend Mode")
        elif param_name == "axis_value":
            layout.prop(action, "axis_value", text="Axis")


class LCW_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LC Workflow"


class LCW_PT_root(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_root"
    bl_label = "LC Workflow helper"

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.label(text="Workflow tools for LC production scenes.")


class LCW_PT_shape_keys(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_shape_keys"
    bl_label = "Shape Keys"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        section = _draw_collapsible_section(layout, state, "shape_section_selection_open", "Selection", icon="RESTRICT_SELECT_OFF")
        if section:
            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_match_active")

            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_copy_names")

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_select_by_name_open",
                "Select Shape Key by Name Fragment",
                icon="VIEWZOOM",
            )
            if tool:
                tool.prop(state, "shape_key_select_fragment")
                op = tool.operator("lcw.shape_key_set_active_phrase")
                _assign_operator_props(op, {"phrase": state.shape_key_select_fragment})

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_set_value_open",
                "Set Active Shape Key Value Across Selection",
                icon="DRIVER",
            )
            if tool:
                tool.prop(state, "shape_key_value")
                op = tool.operator("lcw.shape_key_set_value")
                _assign_operator_props(op, {"value": state.shape_key_value})

        section = _draw_collapsible_section(layout, state, "shape_section_naming_open", "Naming", icon="SORTALPHA")
        if section:
            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_add_prefix_open",
                "Add Prefix to Non-Basis Shape Keys",
                icon="SORTALPHA",
            )
            if tool:
                tool.prop(state, "shape_key_prefix")
                op = tool.operator("lcw.shape_key_add_prefix")
                _assign_operator_props(op, {"prefix": state.shape_key_prefix})

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_replace_text_open",
                "Replace Text in Non-Basis Shape Key Names",
                icon="GREASEPENCIL",
            )
            if tool:
                tool.prop(state, "shape_key_search")
                tool.prop(state, "shape_key_replace")
                op = tool.operator("lcw.shape_key_replace_words")
                _assign_operator_props(op, {"search_text": state.shape_key_search, "replace_text": state.shape_key_replace})

        section = _draw_collapsible_section(layout, state, "shape_section_reset_open", "Reset", icon="FILE_REFRESH")
        if section:
            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_zero_all")

            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_reset_all")

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_reset_matching_open",
                "Reset Matching Shape Keys by Name",
                icon="FILTER",
            )
            if tool:
                tool.prop(state, "shape_key_phrases")
                op = tool.operator("lcw.shape_key_reset_by_phrases")
                _assign_operator_props(op, {"phrases": state.shape_key_phrases})

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_deselect_text_open",
                "Deselect Objects Containing Shape Key Text",
                icon="RESTRICT_SELECT_ON",
            )
            if tool:
                tool.prop(state, "shape_key_deselect_fragment")
                op = tool.operator("lcw.shape_key_deselect_phrase")
                _assign_operator_props(op, {"phrase": state.shape_key_deselect_fragment})

        section = _draw_collapsible_section(layout, state, "shape_section_animation_open", "Animation", icon="DECORATE_ANIMATE")
        if section:
            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_animation_open",
                "Preview Shape Keys by Name Fragment",
                icon="DECORATE_ANIMATE",
            )
            if tool:
                tool.prop(state, "shape_key_animation_names")
                row = tool.row(align=True)
                row.prop(state, "shape_key_animation_start")
                row.prop(state, "shape_key_animation_end")
                row = tool.row(align=True)
                row.prop(state, "shape_key_animation_min")
                row.prop(state, "shape_key_animation_max")
                op = tool.operator("lcw.shape_key_animate_partial")
                _assign_operator_props(
                    op,
                    {
                        "partial_names": state.shape_key_animation_names,
                        "start_frame": state.shape_key_animation_start,
                        "end_frame": state.shape_key_animation_end,
                        "min_value": state.shape_key_animation_min,
                        "max_value": state.shape_key_animation_max,
                    },
                )

        section = _draw_collapsible_section(layout, state, "shape_section_advanced_open", "Advanced", icon="PREFERENCES")
        if section:
            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_create_default")

            tool = _simple_tool_box(section)
            tool.operator("lcw.shape_key_names_check")


class LCW_PT_materials(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_materials"
    bl_label = "Materials"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        box = layout.box()
        row = box.row(align=True)
        row.operator("lcw.material_link_slots_data", icon="MESH_DATA")
        row.operator("lcw.material_link_slots_object", icon="OBJECT_DATA")
        box.operator("lcw.material_toggle_link")

        box = layout.box()
        for slot_index in range(1, 4):
            row = box.row(align=True)
            row.prop(state, f"material_quick_name_{slot_index}", text="")
            op = row.operator("lcw.material_use_quick_name", text="Use")
            op.slot_index = slot_index
        box.prop(state, "material_name")
        op = box.operator("lcw.material_assign_object")
        _assign_operator_props(op, {"material_name": state.material_name})

        box = _draw_collapsible_tool(
            layout,
            state,
            "material_tool_assign_faces_open",
            "Assign Material to Selected Faces",
            icon="EDITMODE_HLT",
        )
        if box:
            box.prop(state, "face_material_name")
            op = box.operator("lcw.material_assign_selected_faces")
            _assign_operator_props(op, {"material_name": state.face_material_name})

        box = _simple_tool_box(layout)
        box.operator("lcw.material_remove_unused_slots")


class LCW_PT_colors(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_colors"
    bl_label = "Colors"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        box = _draw_collapsible_tool(
            layout,
            state,
            "color_tool_initialize_open",
            "Initialize Color Attribute",
            icon="GROUP_VCOL",
        )
        if box:
            box.prop(state, "color_attribute_name")
            box.prop(state, "color_attribute_domain")
            box.prop(state, "color_attribute_type")
            box.prop(state, "replace_color_attribute")
            box.prop(state, "color_initialize_value")
            op = box.operator("lcw.color_attribute_initialize")
            _assign_operator_props(
                op,
                {
                    "attribute_name": state.color_attribute_name,
                    "domain": state.color_attribute_domain,
                    "data_type": state.color_attribute_type,
                    "replace_existing": state.replace_color_attribute,
                    "color": state.color_initialize_value,
                },
            )

        box = _draw_collapsible_tool(
            layout,
            state,
            "color_tool_apply_open",
            "Apply Vertex Colors",
            icon="VPAINT_HLT",
        )
        if box:
            box.label(text=f"Target Attribute: {state.color_attribute_name}", icon="GROUP_VCOL")
            box.prop(state, "color_value")
            box.prop(state, "color_mask_type")
            box.prop(state, "color_blend_mode")
            op = box.operator("lcw.color_attribute_apply")
            _assign_operator_props(
                op,
                {
                    "color": state.color_value,
                    "mask_type": state.color_mask_type,
                    "blend_mode": state.color_blend_mode,
                    "attribute_name": state.color_attribute_name,
                },
            )


class LCW_PT_uv(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_uv"
    bl_label = "UV"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        box = layout.box()
        row = box.row(align=True)
        row.operator("lcw.uv_set_active_1", text="UV1", icon="GROUP_UVS")
        row.operator("lcw.uv_set_active_2", text="UV2", icon="GROUP_UVS")
        row.operator("lcw.uv_set_active_3", text="UV3", icon="GROUP_UVS")

        box = _draw_collapsible_tool(
            layout,
            state,
            "uv_tool_add_channel_open",
            "Add UV Channel",
            icon="ADD",
        )
        if box:
            box.prop(state, "uv_add_channel_target")
            box.prop(state, "uv_add_channel_name")
            if state.uv_add_channel_target == "1":
                op = box.operator("lcw.uv_add_uv1")
                _assign_operator_props(op, {"channel_name": state.uv_add_channel_name})
            elif state.uv_add_channel_target == "2":
                op = box.operator("lcw.uv_add_uv2")
                _assign_operator_props(op, {"channel_name": state.uv_add_channel_name})
            else:
                op = box.operator("lcw.uv_add_uv3")
                _assign_operator_props(op, {"channel_name": state.uv_add_channel_name})

        box = _draw_collapsible_tool(
            layout,
            state,
            "uv_tool_rename_channels_open",
            "Rename UV Channels",
            icon="SORTALPHA",
        )
        if box:
            row = box.row(align=True)
            row.prop(state, "uv_rename_uv1", text="UV1")
            op = row.operator("lcw.uv_rename_uv1", text="Rename")
            op.new_name = state.uv_rename_uv1

            row = box.row(align=True)
            row.prop(state, "uv_rename_uv2", text="UV2")
            op = row.operator("lcw.uv_rename_uv2", text="Rename")
            op.new_name = state.uv_rename_uv2

            row = box.row(align=True)
            row.prop(state, "uv_rename_uv3", text="UV3")
            op = row.operator("lcw.uv_rename_uv3", text="Rename")
            op.new_name = state.uv_rename_uv3


class LCW_PT_mesh_utilities(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_mesh_utilities"
    bl_label = "Mesh Utilities"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        box = _tool_box(layout, "Mesh Data")
        box.operator("lcw.mesh_set_data_names")
        box.operator("lcw.mesh_clear_custom_normals")
        box.operator("lcw.mesh_reveal_in_edit_mode")

        box = _tool_box(layout, "Object Utilities")
        box.prop(state, "object_offset_y")
        op = box.operator("lcw.mesh_progressive_offset_y")
        _assign_operator_props(op, {"base_offset": state.object_offset_y})
        box.prop(state, "rename_suffix_width")
        op = box.operator("lcw.object_rename_dot_suffix")
        _assign_operator_props(op, {"zfill_width": state.rename_suffix_width})


class LCW_PT_workflow_presets(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_workflow_presets"
    bl_label = "Workflow Presets"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        preferences = addon_preferences(context)

        row = layout.row()
        row.template_list(
            "LCW_UL_workflow_presets",
            "",
            preferences,
            "presets",
            preferences,
            "active_preset_index",
            rows=3,
        )
        col = row.column(align=True)
        col.operator("lcw.workflow_preset_add", text="", icon="ADD")
        col.operator("lcw.workflow_preset_remove", text="", icon="REMOVE")
        move = col.operator("lcw.workflow_preset_move", text="", icon="TRIA_UP")
        move.direction = "UP"
        move = col.operator("lcw.workflow_preset_move", text="", icon="TRIA_DOWN")
        move.direction = "DOWN"

        if not preferences.presets:
            layout.label(text="Create a preset to build action chains.", icon="INFO")
            return

        preset_index = max(0, min(preferences.active_preset_index, len(preferences.presets) - 1))
        preferences.active_preset_index = preset_index
        preset = preferences.presets[preset_index]
        layout.prop(preset, "name")
        layout.operator("lcw.workflow_preset_run", icon="PLAY")

        row = layout.row()
        row.template_list(
            "LCW_UL_workflow_actions",
            "",
            preset,
            "actions",
            preset,
            "active_action_index",
            rows=5,
        )
        col = row.column(align=True)
        col.operator("lcw.workflow_action_add", text="", icon="ADD")
        col.operator("lcw.workflow_action_remove", text="", icon="REMOVE")
        move = col.operator("lcw.workflow_action_move", text="", icon="TRIA_UP")
        move.direction = "UP"
        move = col.operator("lcw.workflow_action_move", text="", icon="TRIA_DOWN")
        move.direction = "DOWN"

        if preset.actions:
            action_index = max(0, min(preset.active_action_index, len(preset.actions) - 1))
            preset.active_action_index = action_index
            action = preset.actions[action_index]
            box = layout.box()
            box.label(text="Action Settings")
            _draw_preset_action_settings(box, action)


class LCW_PT_kalibra_tools(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_kalibra_tools"
    bl_label = "Kalibra Tools"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        box = _tool_box(layout, "CSV Export")
        box.prop(state, "kalibra_export_csv")
        op = box.operator("lcw.kalibra_export_selection_csv")
        _assign_operator_props(op, {"filepath": state.kalibra_export_csv})

        box = _tool_box(layout, "Bounding Box")
        box.prop(state, "kalibra_bbox_name")
        box.prop(state, "kalibra_bbox_csv")
        op = box.operator("lcw.kalibra_create_combined_bbox")
        _assign_operator_props(op, {"bbox_name": state.kalibra_bbox_name, "csv_path": state.kalibra_bbox_csv})

        box = _tool_box(layout, "Glass Control Object")
        box.prop(state, "kalibra_glass_search")
        box.prop(state, "kalibra_glass_replace")
        box.prop(state, "kalibra_angle_threshold")
        op = box.operator("lcw.kalibra_create_glass_control")
        _assign_operator_props(
            op,
            {
                "search_text": state.kalibra_glass_search,
                "replace_text": state.kalibra_glass_replace,
                "angle_threshold": state.kalibra_angle_threshold,
            },
        )

        box = _tool_box(layout, "Selected Edge Loops")
        box.prop(state, "kalibra_scale_amount")
        op = box.operator("lcw.kalibra_scale_loops_xz")
        _assign_operator_props(op, {"scale_amount": state.kalibra_scale_amount})
        op = box.operator("lcw.kalibra_scale_loops_x")
        _assign_operator_props(op, {"scale_amount": state.kalibra_scale_amount})
        box.prop(state, "kalibra_axis")
        box.prop(state, "kalibra_falloff_power")
        op = box.operator("lcw.kalibra_space_vertices_axis")
        _assign_operator_props(op, {"axis": state.kalibra_axis, "falloff_power": state.kalibra_falloff_power})


CLASSES = (
    LCW_PT_root,
    LCW_PT_shape_keys,
    LCW_PT_materials,
    LCW_PT_colors,
    LCW_PT_uv,
    LCW_PT_mesh_utilities,
    LCW_PT_workflow_presets,
    LCW_PT_kalibra_tools,
)
