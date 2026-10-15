from __future__ import annotations

import bpy

from ..constants import PANEL_LABELS, PANEL_SEPARATOR_KEYS, is_panel_separator, normalize_panel_order
from ..ui import panels
from ..utils.common import scene_state


class LCW_OT_main_panel_move(bpy.types.Operator):
    bl_idname = "lcw.main_panel_move"
    bl_label = "Move Main Category"
    bl_options = {"REGISTER"}

    panel_key: bpy.props.StringProperty(name="Panel Key", default="")
    direction: bpy.props.EnumProperty(
        name="Direction",
        items=(
            ("UP", "Up", "Move the category up"),
            ("DOWN", "Down", "Move the category down"),
        ),
    )

    def execute(self, context: bpy.types.Context):
        file_state = scene_state(context)
        order = list(normalize_panel_order(file_state.panel_order))
        if self.panel_key not in order:
            self.report({"WARNING"}, "Unknown category.")
            return {"CANCELLED"}

        index = order.index(self.panel_key)
        new_index = index - 1 if self.direction == "UP" else index + 1
        if new_index < 0 or new_index >= len(order):
            return {"CANCELLED"}

        order[index], order[new_index] = order[new_index], order[index]
        file_state.panel_order = ",".join(order)
        panels.refresh_panel_registration()

        direction_label = "up" if self.direction == "UP" else "down"
        label = "Separator" if is_panel_separator(self.panel_key) else PANEL_LABELS[self.panel_key]
        self.report({"INFO"}, f"Moved '{label}' {direction_label}.")
        return {"FINISHED"}


class LCW_OT_main_panel_separator_add(bpy.types.Operator):
    bl_idname = "lcw.main_panel_separator_add"
    bl_label = "Add Separator"
    bl_description = "Add a separator line between categories; move it with the arrows and optionally name the group"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):
        file_state = scene_state(context)
        order = list(normalize_panel_order(file_state.panel_order))
        free = [key for key in PANEL_SEPARATOR_KEYS if key not in order]
        if not free:
            self.report({"WARNING"}, f"At most {len(PANEL_SEPARATOR_KEYS)} separators.")
            return {"CANCELLED"}
        key = free[0]
        order.append(key)  # predictable: at the end, then moved with the arrows
        file_state.panel_order = ",".join(order)
        item = next((item for item in file_state.panel_separators if item.key == key), None)
        if item is None:
            item = file_state.panel_separators.add()
            item.key = key
        item.title = ""
        panels.refresh_panel_registration()
        return {"FINISHED"}


class LCW_OT_main_panel_separator_remove(bpy.types.Operator):
    bl_idname = "lcw.main_panel_separator_remove"
    bl_label = "Remove Separator"
    bl_description = "Remove this separator"
    bl_options = {"REGISTER", "UNDO"}

    panel_key: bpy.props.StringProperty(name="Separator Key", default="")

    def execute(self, context: bpy.types.Context):
        if not is_panel_separator(self.panel_key):
            return {"CANCELLED"}
        file_state = scene_state(context)
        order = [key for key in normalize_panel_order(file_state.panel_order) if key != self.panel_key]
        file_state.panel_order = ",".join(order)
        for index, item in enumerate(file_state.panel_separators):
            if item.key == self.panel_key:
                file_state.panel_separators.remove(index)
                break
        panels.refresh_panel_registration()
        return {"FINISHED"}


CLASSES = (LCW_OT_main_panel_move, LCW_OT_main_panel_separator_add, LCW_OT_main_panel_separator_remove)
