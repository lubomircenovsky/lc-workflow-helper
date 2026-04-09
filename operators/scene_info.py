from __future__ import annotations

import bpy


def _format_clipboard_float(value: float) -> str:
    return format(value, ".6f").rstrip("0").rstrip(".")


class LCW_OT_scene_cursor_copy_axis(bpy.types.Operator):
    bl_idname = "lcw.scene_cursor_copy_axis"
    bl_label = "Copy 3D Cursor Axis"
    bl_description = "Copy one 3D cursor location axis value to the clipboard"

    axis_index: bpy.props.IntProperty(name="Axis Index", min=0, max=2)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.scene is not None

    def execute(self, context: bpy.types.Context):
        axis_labels = ("X", "Y", "Z")
        value = context.scene.cursor.location[self.axis_index]
        context.window_manager.clipboard = _format_clipboard_float(value)
        self.report({"INFO"}, f"Copied 3D cursor {axis_labels[self.axis_index]} value.")
        return {"FINISHED"}


CLASSES = (LCW_OT_scene_cursor_copy_axis,)
