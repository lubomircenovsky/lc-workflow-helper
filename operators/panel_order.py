from __future__ import annotations

import bpy

from ..constants import PANEL_LABELS, normalize_panel_order
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
        if self.panel_key not in PANEL_LABELS:
            self.report({"WARNING"}, "Unknown category.")
            return {"CANCELLED"}

        file_state = scene_state(context)
        order = list(normalize_panel_order(file_state.panel_order))
        index = order.index(self.panel_key)
        new_index = index - 1 if self.direction == "UP" else index + 1
        if new_index < 0 or new_index >= len(order):
            return {"CANCELLED"}

        order[index], order[new_index] = order[new_index], order[index]
        file_state.panel_order = ",".join(order)
        panels.refresh_panel_registration()

        direction_label = "up" if self.direction == "UP" else "down"
        self.report({"INFO"}, f"Moved '{PANEL_LABELS[self.panel_key]}' {direction_label}.")
        return {"FINISHED"}


CLASSES = (LCW_OT_main_panel_move,)
