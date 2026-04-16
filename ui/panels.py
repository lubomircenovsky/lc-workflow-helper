from __future__ import annotations

import bpy
from bpy.app.handlers import persistent

from ..constants import ACTION_MAP, PANEL_LABELS, normalize_panel_order
from ..operators.favorites import favorite_action_available
from ..utils.common import addon_preferences, is_favorite_action, scene_state, wm_state


def _assign_operator_props(operator, values: dict) -> None:
    for name, value in values.items():
        setattr(operator, name, value)


def _simple_tool_box(layout: bpy.types.UILayout):
    return layout.box().column(align=False)


def _favorite_icon(context: bpy.types.Context, action_id: str) -> str:
    return "SOLO_ON" if is_favorite_action(context, action_id) else "SOLO_OFF"


def _draw_favorite_toggle(layout: bpy.types.UILayout, context: bpy.types.Context, action_id: str) -> None:
    toggle = layout.operator(
        "lcw.favorite_toggle",
        text="",
        emboss=False,
        icon=_favorite_icon(context, action_id),
    )
    toggle.action_id = action_id


def _draw_action_button(
    layout: bpy.types.UILayout,
    context: bpy.types.Context,
    action_id: str,
    operator_id: str,
    *,
    text: str | None = None,
    icon: str = "NONE",
    props: dict | None = None,
):
    label = text if text is not None else ACTION_MAP[action_id].label
    operator = layout.operator(operator_id, text=label, icon=icon)
    if props:
        _assign_operator_props(operator, props)
    _draw_favorite_toggle(layout, context, action_id)
    return operator


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
    if action.action_id == "mesh.offset_y":
        layout.prop(action, "float_value", text="Offset Step")
        row = layout.row(align=True)
        row.label(text="Axes")
        row.prop(action, "bool_value", text="X", toggle=True)
        row.prop(action, "bool_value_2", text="Y", toggle=True)
        row.prop(action, "bool_value_3", text="Z", toggle=True)
        return
    if action.action_id == "kalibra.scale_loops_xz":
        layout.prop(action, "float_value", text="Scale Amount")
        row = layout.row(align=True)
        row.label(text="Space")
        row.prop_enum(action, "space_value", "GLOBAL")
        row.prop_enum(action, "space_value", "LOCAL")
        row = layout.row(align=True)
        row.label(text="Axes")
        row.prop(action, "bool_value", text="X", toggle=True)
        row.prop(action, "bool_value_2", text="Y", toggle=True)
        row.prop(action, "bool_value_3", text="Z", toggle=True)
        return
    if action.action_id == "kalibra.space_vertices_axis":
        row = layout.row(align=True)
        row.prop_enum(action, "axis_value", "X", text="+X")
        row.prop_enum(action, "axis_value", "-X", text="-X")
        row = layout.row(align=True)
        row.prop_enum(action, "axis_value", "Y", text="+Y")
        row.prop_enum(action, "axis_value", "-Y", text="-Y")
        row = layout.row(align=True)
        row.prop_enum(action, "axis_value", "Z", text="+Z")
        row.prop_enum(action, "axis_value", "-Z", text="-Z")
        layout.prop(action, "float_value", text="Falloff Power")
        return

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
        elif param_name == "bool_value_2":
            layout.prop(action, "bool_value_2")
        elif param_name == "bool_value_3":
            layout.prop(action, "bool_value_3")
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


def _draw_favorite_action_inputs(
    layout: bpy.types.UILayout,
    context: bpy.types.Context,
    action_id: str,
) -> None:
    state = wm_state(context)

    if action_id == "shape_keys.set_value":
        layout.prop(state, "shape_key_value")
    elif action_id == "shape_keys.set_active_phrase":
        layout.prop(state, "shape_key_select_fragment")
    elif action_id == "shape_keys.add_prefix":
        layout.prop(state, "shape_key_prefix")
    elif action_id == "shape_keys.replace_words":
        layout.prop(state, "shape_key_search")
        layout.prop(state, "shape_key_replace")
    elif action_id == "shape_keys.reset_by_phrases":
        layout.prop(state, "shape_key_phrases")
    elif action_id == "shape_keys.deselect_phrase":
        layout.prop(state, "shape_key_deselect_fragment")
    elif action_id == "shape_keys.preview_partial":
        layout.prop(state, "shape_key_animation_names")
        row = layout.row(align=True)
        row.prop(state, "shape_key_animation_start")
        row.prop(state, "shape_key_animation_end")
        row = layout.row(align=True)
        row.prop(state, "shape_key_animation_min")
        row.prop(state, "shape_key_animation_max")
    elif action_id == "materials.assign_object":
        layout.prop(state, "material_name")
    elif action_id == "materials.assign_faces":
        layout.prop(state, "face_material_name")
    elif action_id == "colors.ensure_attribute":
        layout.prop(state, "color_attribute_name")
        layout.prop(state, "color_attribute_domain")
        layout.prop(state, "color_attribute_type")
        layout.prop(state, "replace_color_attribute")
        layout.prop(state, "color_initialize_value")
    elif action_id == "colors.apply":
        layout.prop(state, "color_value")
        layout.prop(state, "color_mask_type")
        layout.prop(state, "color_blend_mode")
        layout.label(text=f"Target Attribute: {state.color_attribute_name}", icon="GROUP_VCOL")
    elif action_id in {"uv.add_uv1", "uv.add_uv2", "uv.add_uv3"}:
        layout.prop(state, "uv_add_channel_name")
    elif action_id == "uv.rename_uv1":
        layout.prop(state, "uv_rename_uv1")
    elif action_id == "uv.rename_uv2":
        layout.prop(state, "uv_rename_uv2")
    elif action_id == "uv.rename_uv3":
        layout.prop(state, "uv_rename_uv3")
    elif action_id == "mesh.offset_y":
        layout.prop(state, "object_offset_y")
        row = layout.row(align=True)
        row.label(text="Axes")
        row.prop(state, "mesh_offset_axis_x", text="X", toggle=True)
        row.prop(state, "mesh_offset_axis_y", text="Y", toggle=True)
        row.prop(state, "mesh_offset_axis_z", text="Z", toggle=True)
    elif action_id == "mesh.rename_suffix":
        layout.prop(state, "rename_suffix_width")
    elif action_id == "kalibra.export_selection_csv":
        layout.prop(state, "kalibra_export_csv")
    elif action_id == "kalibra.create_bbox":
        layout.prop(state, "kalibra_bbox_name")
        layout.prop(state, "kalibra_bbox_csv")
    elif action_id == "kalibra.create_glass_control":
        layout.prop(state, "kalibra_glass_search")
        layout.prop(state, "kalibra_glass_replace")
        layout.prop(state, "kalibra_angle_threshold")
    elif action_id == "kalibra.scale_loops_xz":
        layout.prop(state, "kalibra_scale_amount")
        row = layout.row(align=True)
        row.label(text="Space")
        row.prop_enum(state, "kalibra_scale_space", "GLOBAL")
        row.prop_enum(state, "kalibra_scale_space", "LOCAL")
        row = layout.row(align=True)
        row.label(text="Axes")
        row.prop(state, "kalibra_scale_axis_x", text="X", toggle=True)
        row.prop(state, "kalibra_scale_axis_y", text="Y", toggle=True)
        row.prop(state, "kalibra_scale_axis_z", text="Z", toggle=True)
    elif action_id == "kalibra.scale_loops_x":
        layout.prop(state, "kalibra_scale_amount")
    elif action_id == "kalibra.space_vertices_axis":
        row = layout.row(align=True)
        row.prop_enum(state, "kalibra_axis", "X", text="+X")
        row.prop_enum(state, "kalibra_axis", "-X", text="-X")
        row = layout.row(align=True)
        row.prop_enum(state, "kalibra_axis", "Y", text="+Y")
        row.prop_enum(state, "kalibra_axis", "-Y", text="-Y")
        row = layout.row(align=True)
        row.prop_enum(state, "kalibra_axis", "Z", text="+Z")
        row.prop_enum(state, "kalibra_axis", "-Z", text="-Z")
        layout.prop(state, "kalibra_falloff_power")


def _draw_favorite_action(
    layout: bpy.types.UILayout,
    context: bpy.types.Context,
    definition,
) -> None:
    box = layout.box()
    if definition.params:
        _draw_favorite_action_inputs(box, context, definition.action_id)
    row = box.row(align=True)
    row.enabled = favorite_action_available(definition.action_id)
    run = row.operator("lcw.favorite_run_action", text=definition.label, icon="PLAY")
    run.action_id = definition.action_id
    _draw_favorite_toggle(row, context, definition.action_id)


def _stored_panel_order(context: bpy.types.Context | None = None) -> tuple[str, ...]:
    if context is not None:
        scene = getattr(context, "scene", None)
    else:
        scene = getattr(bpy.context, "scene", None)
    file_state = getattr(scene, "lcw_scene_state", None)
    return normalize_panel_order(getattr(file_state, "panel_order", None))


def _apply_panel_order() -> None:
    for bl_order, panel_key in enumerate(_stored_panel_order(), start=1):
        PANEL_CLASS_MAP[panel_key].bl_order = bl_order


def _tag_redraw() -> None:
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            area.tag_redraw()


def prepare_register() -> None:
    _apply_panel_order()


def refresh_panel_registration() -> None:
    _apply_panel_order()
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            continue
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _tag_redraw()


def _refresh_panel_order_timer():
    refresh_panel_registration()
    return None


@persistent
def _refresh_panel_order_on_load(_dummy) -> None:
    refresh_panel_registration()


def register_handlers() -> None:
    if _refresh_panel_order_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_refresh_panel_order_on_load)
    if not bpy.app.timers.is_registered(_refresh_panel_order_timer):
        bpy.app.timers.register(_refresh_panel_order_timer, first_interval=0.1)


def unregister_handlers() -> None:
    if _refresh_panel_order_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_refresh_panel_order_on_load)
    if bpy.app.timers.is_registered(_refresh_panel_order_timer):
        bpy.app.timers.unregister(_refresh_panel_order_timer)


class LCW_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "LC Workflow"


class LCW_PT_root(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_root"
    bl_label = "LC Workflow helper"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)
        file_state = scene_state(context)

        layout.label(text="Workflow tools for LC production scenes.")
        section = _draw_collapsible_section(layout, state, "root_category_order_open", "Main Category Order", icon="SORTSIZE")
        if section:
            section.label(text="Use arrows to reorder categories in this .blend file.", icon="INFO")
            ordered_keys = normalize_panel_order(file_state.panel_order)
            for index, panel_key in enumerate(ordered_keys):
                row = section.row(align=True)
                row.label(text=PANEL_LABELS[panel_key])

                move_up = row.row(align=True)
                move_up.enabled = index > 0
                operator = move_up.operator("lcw.main_panel_move", text="", icon="TRIA_UP")
                operator.panel_key = panel_key
                operator.direction = "UP"

                move_down = row.row(align=True)
                move_down.enabled = index < len(ordered_keys) - 1
                operator = move_down.operator("lcw.main_panel_move", text="", icon="TRIA_DOWN")
                operator.panel_key = panel_key
                operator.direction = "DOWN"


class LCW_PT_scene_info(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_scene_info"
    bl_label = "Scene Info"
    bl_parent_id = "LCW_PT_root"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        active_object = context.active_object

        box = layout.box()
        row = box.row(align=False)

        object_col = row.column(align=True)
        object_col.label(text="Active Object", icon="OBJECT_DATA")
        if active_object is None:
            object_col.label(text="No active object", icon="INFO")
        else:
            object_col.prop(active_object, "dimensions", text="")

        cursor_col = row.column(align=True)
        cursor_col.label(text="3D Cursor", icon="CURSOR")
        for axis_index, axis_name in enumerate(("X", "Y", "Z")):
            axis_row = cursor_col.row(align=True)
            axis_row.prop(context.scene.cursor, "location", index=axis_index, text=axis_name)
            operator = axis_row.operator("lcw.scene_cursor_copy_axis", text="", icon="COPYDOWN")
            operator.axis_index = axis_index


class LCW_PT_favorites(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_favorites"
    bl_label = "Favorites"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        file_state = scene_state(context)

        favorite_ids = [item.action_id for item in file_state.favorite_actions if item.action_id in ACTION_MAP]
        if not favorite_ids:
            layout.label(text="Add favorite actions with the star buttons.", icon="INFO")
            return

        current_category = None
        for action_id in favorite_ids:
            definition = ACTION_MAP[action_id]
            if not definition.allow_favorite:
                continue
            if definition.category != current_category:
                current_category = definition.category
                layout.label(text=current_category, icon="BOOKMARKS")
            _draw_favorite_action(layout, context, definition)


class LCW_PT_shape_keys(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_shape_keys"
    bl_label = "Shape Keys"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        tool = _draw_collapsible_tool(
            layout,
            state,
            "shape_tool_set_value_open",
            "Set Active Shape Key Value Across Selection",
            icon="DRIVER",
        )
        if tool:
            tool.prop(state, "shape_key_value")
            row = tool.row(align=True)
            _draw_action_button(
                row,
                context,
                "shape_keys.set_value",
                "lcw.shape_key_set_value",
                props={"value": state.shape_key_value},
            )

        section = _draw_collapsible_section(layout, state, "shape_section_selection_open", "Selection", icon="RESTRICT_SELECT_OFF")
        if section:
            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.match_active", "lcw.shape_key_match_active")

            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.copy_names", "lcw.shape_key_copy_names")

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_select_by_name_open",
                "Set Active Shape Key",
                icon="VIEWZOOM",
            )
            if tool:
                tool.prop(state, "shape_key_select_fragment")
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.set_active_phrase",
                    "lcw.shape_key_set_active_phrase",
                    text="Select Shape Key by Name Fragment",
                    props={"phrase": state.shape_key_select_fragment},
                )

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
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.add_prefix",
                    "lcw.shape_key_add_prefix",
                    props={"prefix": state.shape_key_prefix},
                )

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
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.replace_words",
                    "lcw.shape_key_replace_words",
                    props={"search_text": state.shape_key_search, "replace_text": state.shape_key_replace},
                )

        section = _draw_collapsible_section(layout, state, "shape_section_reset_open", "Reset", icon="FILE_REFRESH")
        if section:
            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.zero_all", "lcw.shape_key_zero_all")

            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.reset_all", "lcw.shape_key_reset_all")

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_reset_matching_open",
                "Reset Matching Shape Keys by Name",
                icon="FILTER",
            )
            if tool:
                tool.prop(state, "shape_key_phrases")
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.reset_by_phrases",
                    "lcw.shape_key_reset_by_phrases",
                    props={"phrases": state.shape_key_phrases},
                )

            tool = _draw_collapsible_tool(
                section,
                state,
                "shape_tool_deselect_text_open",
                "Deselect Objects Containing Shape Key Text",
                icon="RESTRICT_SELECT_ON",
            )
            if tool:
                tool.prop(state, "shape_key_deselect_fragment")
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.deselect_phrase",
                    "lcw.shape_key_deselect_phrase",
                    props={"phrase": state.shape_key_deselect_fragment},
                )

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
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "shape_keys.preview_partial",
                    "lcw.shape_key_animate_partial",
                    props={
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
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.create_default", "lcw.shape_key_create_default")

            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "shape_keys.names_check", "lcw.shape_key_names_check")


class LCW_PT_materials(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_materials"
    bl_label = "Materials"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)
        file_state = scene_state(context)

        box = layout.box()
        row = box.row(align=True)
        _draw_action_button(row, context, "materials.link_slots_data", "lcw.material_link_slots_data", icon="MESH_DATA")
        _draw_action_button(row, context, "materials.link_slots_object", "lcw.material_link_slots_object", icon="OBJECT_DATA")
        row = box.row(align=True)
        _draw_action_button(row, context, "materials.toggle_link", "lcw.material_toggle_link")
        row = box.row(align=True)
        _draw_action_button(row, context, "materials.random_active_color", "lcw.material_random_active_color")

        box = layout.box()
        for slot_index in range(1, 4):
            row = box.row(align=True)
            split = row.split(factor=0.78, align=True)
            split.prop(file_state, f"material_quick_name_{slot_index}", text="")
            op = split.operator("lcw.material_use_quick_name", text="Use")
            op.slot_index = slot_index
        box.prop(state, "material_name")
        row = box.row(align=True)
        _draw_action_button(
            row,
            context,
            "materials.assign_object",
            "lcw.material_assign_object",
            props={"material_name": state.material_name},
        )

        box = _draw_collapsible_tool(
            layout,
            state,
            "material_tool_assign_faces_open",
            "Assign Material to Selected Faces",
            icon="EDITMODE_HLT",
        )
        if box:
            box.prop(state, "face_material_name")
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "materials.assign_faces",
                "lcw.material_assign_selected_faces",
                props={"material_name": state.face_material_name},
            )

        box = _simple_tool_box(layout)
        row = box.row(align=True)
        _draw_action_button(row, context, "materials.remove_unused_slots", "lcw.material_remove_unused_slots")


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
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "colors.ensure_attribute",
                "lcw.color_attribute_initialize",
                props={
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
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "colors.apply",
                "lcw.color_attribute_apply",
                props={
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
        _draw_action_button(row, context, "uv.set_active_uv1", "lcw.uv_set_active_1", text="UV1", icon="GROUP_UVS")
        _draw_action_button(row, context, "uv.set_active_uv2", "lcw.uv_set_active_2", text="UV2", icon="GROUP_UVS")
        _draw_action_button(row, context, "uv.set_active_uv3", "lcw.uv_set_active_3", text="UV3", icon="GROUP_UVS")

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
                row = box.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "uv.add_uv1",
                    "lcw.uv_add_uv1",
                    props={"channel_name": state.uv_add_channel_name},
                )
            elif state.uv_add_channel_target == "2":
                row = box.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "uv.add_uv2",
                    "lcw.uv_add_uv2",
                    props={"channel_name": state.uv_add_channel_name},
                )
            else:
                row = box.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "uv.add_uv3",
                    "lcw.uv_add_uv3",
                    props={"channel_name": state.uv_add_channel_name},
                )

        box = _draw_collapsible_tool(
            layout,
            state,
            "uv_tool_remove_channel_open",
            "Remove UV Channel",
            icon="TRASH",
        )
        if box:
            box.prop(state, "uv_remove_channel_target")
            row = box.row(align=True)
            operator = row.operator("lcw.uv_remove_channel", text="Remove UV Channel", icon="TRASH")
            operator.channel_number = int(state.uv_remove_channel_target)

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
            _draw_action_button(
                row,
                context,
                "uv.rename_uv1",
                "lcw.uv_rename_uv1",
                text="Rename",
                props={"new_name": state.uv_rename_uv1},
            )

            row = box.row(align=True)
            row.prop(state, "uv_rename_uv2", text="UV2")
            _draw_action_button(
                row,
                context,
                "uv.rename_uv2",
                "lcw.uv_rename_uv2",
                text="Rename",
                props={"new_name": state.uv_rename_uv2},
            )

            row = box.row(align=True)
            row.prop(state, "uv_rename_uv3", text="UV3")
            _draw_action_button(
                row,
                context,
                "uv.rename_uv3",
                "lcw.uv_rename_uv3",
                text="Rename",
                props={"new_name": state.uv_rename_uv3},
            )


class LCW_PT_mesh_utilities(LCW_PT_base, bpy.types.Panel):
    bl_idname = "LCW_PT_mesh_utilities"
    bl_label = "Object and Mesh Utilities"
    bl_parent_id = "LCW_PT_root"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        state = wm_state(context)

        section = _draw_collapsible_section(layout, state, "mesh_section_data_open", "Mesh Data", icon="MESH_DATA")
        if section:
            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "mesh.set_data_names", "lcw.mesh_set_data_names")

            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "mesh.clear_custom_normals", "lcw.mesh_clear_custom_normals")

            tool = _simple_tool_box(section)
            row = tool.row(align=True)
            _draw_action_button(row, context, "mesh.reveal_edit", "lcw.mesh_reveal_in_edit_mode")

        section = _draw_collapsible_section(layout, state, "mesh_section_object_open", "Object Utilities", icon="OBJECT_DATA")
        if section:
            tool = _draw_collapsible_tool(
                section,
                state,
                "mesh_tool_offset_y_open",
                "Progressive Cursor Offset",
                icon="EMPTY_AXIS",
            )
            if tool:
                tool.prop(state, "object_offset_y")
                row = tool.row(align=True)
                row.label(text="Axes")
                row.prop(state, "mesh_offset_axis_x", text="X", toggle=True)
                row.prop(state, "mesh_offset_axis_y", text="Y", toggle=True)
                row.prop(state, "mesh_offset_axis_z", text="Z", toggle=True)
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "mesh.offset_y",
                    "lcw.mesh_progressive_offset_y",
                    props={
                        "base_offset": state.object_offset_y,
                        "use_axis_x": state.mesh_offset_axis_x,
                        "use_axis_y": state.mesh_offset_axis_y,
                        "use_axis_z": state.mesh_offset_axis_z,
                    },
                )

            tool = _draw_collapsible_tool(
                section,
                state,
                "mesh_tool_rename_suffix_open",
                "Rename Dot Suffix to Underscore",
                icon="SORTALPHA",
            )
            if tool:
                tool.prop(state, "rename_suffix_width")
                row = tool.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "mesh.rename_suffix",
                    "lcw.object_rename_dot_suffix",
                    props={"zfill_width": state.rename_suffix_width},
                )


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

        box = _draw_collapsible_tool(
            layout,
            state,
            "kalibra_tool_export_open",
            "CSV Export",
            icon="EXPORT",
        )
        if box:
            box.prop(state, "kalibra_export_csv")
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "kalibra.export_selection_csv",
                "lcw.kalibra_export_selection_csv",
                props={"filepath": state.kalibra_export_csv},
            )

        box = _draw_collapsible_tool(
            layout,
            state,
            "kalibra_tool_bbox_open",
            "Bounding Box",
            icon="SHADING_BBOX",
        )
        if box:
            box.prop(state, "kalibra_bbox_name")
            box.prop(state, "kalibra_bbox_csv")
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "kalibra.create_bbox",
                "lcw.kalibra_create_combined_bbox",
                props={"bbox_name": state.kalibra_bbox_name, "csv_path": state.kalibra_bbox_csv},
            )

        box = _draw_collapsible_tool(
            layout,
            state,
            "kalibra_tool_glass_open",
            "Glass Control Object",
            icon="MOD_WIREFRAME",
        )
        if box:
            box.prop(state, "kalibra_glass_search")
            box.prop(state, "kalibra_glass_replace")
            box.prop(state, "kalibra_angle_threshold")
            row = box.row(align=True)
            _draw_action_button(
                row,
                context,
                "kalibra.create_glass_control",
                "lcw.kalibra_create_glass_control",
                props={
                    "search_text": state.kalibra_glass_search,
                    "replace_text": state.kalibra_glass_replace,
                    "angle_threshold": state.kalibra_angle_threshold,
                },
            )

        section = _draw_collapsible_section(layout, state, "kalibra_section_loops_open", "Selected Edge Loops", icon="MESH_DATA")
        if section:
            box = _draw_collapsible_tool(
                section,
                state,
                "kalibra_tool_scale_loops_open",
                "Scale Edge Loops | Rubber seals offset",
                icon="FULLSCREEN_EXIT",
            )
            if box:
                box.prop(state, "kalibra_scale_amount")
                row = box.row(align=True)
                row.label(text="Space")
                row.prop_enum(state, "kalibra_scale_space", "GLOBAL")
                row.prop_enum(state, "kalibra_scale_space", "LOCAL")
                row = box.row(align=True)
                row.label(text="Axes")
                row.prop(state, "kalibra_scale_axis_x", text="X", toggle=True)
                row.prop(state, "kalibra_scale_axis_y", text="Y", toggle=True)
                row.prop(state, "kalibra_scale_axis_z", text="Z", toggle=True)
                row = box.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "kalibra.scale_loops_xz",
                    "lcw.kalibra_scale_loops_xz",
                    props={
                        "scale_amount": state.kalibra_scale_amount,
                        "space_mode": state.kalibra_scale_space,
                        "use_axis_x": state.kalibra_scale_axis_x,
                        "use_axis_y": state.kalibra_scale_axis_y,
                        "use_axis_z": state.kalibra_scale_axis_z,
                    },
                )

            box = _draw_collapsible_tool(
                section,
                state,
                "kalibra_tool_space_vertices_open",
                "Space Vertices with Axis Falloff | Rustic door arch",
                icon="MOD_ARRAY",
            )
            if box:
                row = box.row(align=True)
                row.prop_enum(state, "kalibra_axis", "X", text="+X")
                row.prop_enum(state, "kalibra_axis", "-X", text="-X")
                row = box.row(align=True)
                row.prop_enum(state, "kalibra_axis", "Y", text="+Y")
                row.prop_enum(state, "kalibra_axis", "-Y", text="-Y")
                row = box.row(align=True)
                row.prop_enum(state, "kalibra_axis", "Z", text="+Z")
                row.prop_enum(state, "kalibra_axis", "-Z", text="-Z")
                box.prop(state, "kalibra_falloff_power")
                row = box.row(align=True)
                _draw_action_button(
                    row,
                    context,
                    "kalibra.space_vertices_axis",
                    "lcw.kalibra_space_vertices_axis",
                    props={"axis": state.kalibra_axis, "falloff_power": state.kalibra_falloff_power},
                )
                reminder_box = box.box()
                reminder_box.label(text="Spacing Reminder", icon="INFO")
                split = reminder_box.split(factor=1 / 3, align=True)
                col = split.column(align=True)
                col.label(text="24", icon="MESH_GRID")
                col.label(text="2.4", icon="CURVE_PATH")
                col = split.column(align=True)
                col.label(text="6", icon="MESH_GRID")
                col.label(text="2.2", icon="CURVE_PATH")
                col = split.column(align=True)
                col.label(text="20", icon="MESH_GRID")
                col.label(text="1.8", icon="CURVE_PATH")


PANEL_CLASS_MAP = {
    "scene_info": LCW_PT_scene_info,
    "favorites": LCW_PT_favorites,
    "shape_keys": LCW_PT_shape_keys,
    "materials": LCW_PT_materials,
    "colors": LCW_PT_colors,
    "uv": LCW_PT_uv,
    "mesh_utilities": LCW_PT_mesh_utilities,
    "workflow_presets": LCW_PT_workflow_presets,
    "kalibra_tools": LCW_PT_kalibra_tools,
}


CLASSES = (
    LCW_PT_root,
    LCW_PT_scene_info,
    LCW_PT_favorites,
    LCW_PT_shape_keys,
    LCW_PT_materials,
    LCW_PT_colors,
    LCW_PT_uv,
    LCW_PT_mesh_utilities,
    LCW_PT_workflow_presets,
    LCW_PT_kalibra_tools,
)
