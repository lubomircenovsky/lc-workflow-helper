from __future__ import annotations

import bpy

from ..utils.common import has_selected_mesh_objects, selected_mesh_objects


class LCW_OT_uv_ensure_second(bpy.types.Operator):
    bl_idname = "lcw.uv_ensure_second"
    bl_label = "Ensure Second UV Channel"
    bl_options = {"REGISTER", "UNDO"}

    lightmap_name: bpy.props.StringProperty(name="Second UV Name", default="Lightmap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        updated = 0
        for obj in selected_mesh_objects(context):
            uv_layers = obj.data.uv_layers
            if len(uv_layers) == 0:
                uv_layers.new(name="UVMap")
                uv_layers.new(name=self.lightmap_name)
                updated += 1
            elif len(uv_layers) == 1:
                uv_layers.new(name=self.lightmap_name)
                updated += 1
            elif len(uv_layers) >= 2:
                uv_layers[1].name = self.lightmap_name
        self.report({"INFO"}, f"Ensured second UV channel on {updated} object(s).")
        return {"FINISHED"}


class LCW_OT_uv_set_active_channel(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_channel"
    bl_label = "Set Active UV Channel"
    bl_options = {"REGISTER", "UNDO"}

    channel_number: bpy.props.IntProperty(name="UV Channel", default=2, min=1)
    deselect_if_missing: bpy.props.BoolProperty(name="Deselect if Missing", default=True)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        target_index = self.channel_number - 1
        updated = 0
        deselected = 0
        for obj in selected_mesh_objects(context):
            if len(obj.data.uv_layers) > target_index:
                obj.data.uv_layers.active_index = target_index
                updated += 1
            elif self.deselect_if_missing:
                obj.select_set(False)
                deselected += 1
        self.report({"INFO"}, f"Updated {updated} object(s), deselected {deselected}.")
        return {"FINISHED"}


class LCW_OT_uv_rename_channel(bpy.types.Operator):
    bl_idname = "lcw.uv_rename_channel"
    bl_label = "Rename UV Channel"
    bl_options = {"REGISTER", "UNDO"}

    channel_number: bpy.props.IntProperty(name="UV Channel", default=2, min=1)
    new_name: bpy.props.StringProperty(name="New Name", default="Lightmap")
    deselect_if_missing: bpy.props.BoolProperty(name="Deselect if Missing", default=True)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        target_index = self.channel_number - 1
        renamed = 0
        deselected = 0
        for obj in selected_mesh_objects(context):
            if len(obj.data.uv_layers) > target_index:
                obj.data.uv_layers[target_index].name = self.new_name
                renamed += 1
            elif self.deselect_if_missing:
                obj.select_set(False)
                deselected += 1
        self.report({"INFO"}, f"Renamed {renamed} UV channel(s), deselected {deselected}.")
        return {"FINISHED"}


CLASSES = (
    LCW_OT_uv_ensure_second,
    LCW_OT_uv_set_active_channel,
    LCW_OT_uv_rename_channel,
)
