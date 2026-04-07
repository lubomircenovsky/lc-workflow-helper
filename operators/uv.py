from __future__ import annotations

import bpy

from ..utils.common import has_selected_mesh_objects, selected_mesh_objects


def _ensure_uv_layers_to_index(obj: bpy.types.Object, target_index: int) -> None:
    uv_layers = obj.data.uv_layers
    if len(uv_layers) == 0:
        uv_layers.new(name="UVMap")
    while len(uv_layers) <= target_index:
        uv_layers.new(name=f"UVMap.{len(uv_layers):03d}")


class LCW_OT_uv_ensure_second(bpy.types.Operator):
    bl_idname = "lcw.uv_ensure_second"
    bl_label = "Ensure Second UV Channel"
    bl_description = "Runs on all selected mesh objects and ensures a second UV channel exists, renaming it to the entered name when present"
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
    bl_description = "Runs on all selected mesh objects, sets the requested UV channel active, and deselects objects that do not contain that channel when Deselect if Missing is enabled"
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
    bl_description = "Runs on all selected mesh objects, renames the requested UV channel, and deselects objects that do not contain that channel when Deselect if Missing is enabled"
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


class LCW_OT_uv_add_channel(bpy.types.Operator):
    bl_idname = "lcw.uv_add_channel"
    bl_label = "Add UV Channel"
    bl_description = "Runs on all selected mesh objects, creates missing UV channels up to UV1, UV2, or UV3, and assigns the entered name to the target channel"
    bl_options = {"REGISTER", "UNDO"}

    channel_number: bpy.props.IntProperty(name="UV Channel", default=2, min=1, max=3)
    channel_name: bpy.props.StringProperty(name="Channel Name", default="Lightmap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        target_index = self.channel_number - 1
        updated = 0
        for obj in selected_mesh_objects(context):
            _ensure_uv_layers_to_index(obj, target_index)
            obj.data.uv_layers[target_index].name = self.channel_name
            updated += 1
        self.report({"INFO"}, f"Prepared UV{self.channel_number} on {updated} object(s).")
        return {"FINISHED"}


class LCW_OT_uv_add_uv1(bpy.types.Operator):
    bl_idname = "lcw.uv_add_uv1"
    bl_label = "Add UV1 Channel"
    bl_description = "Runs on all selected mesh objects, creates UV1 when missing, and assigns the entered name to UV1"
    bl_options = {"REGISTER", "UNDO"}

    channel_name: bpy.props.StringProperty(name="UV1 Name", default="UVMap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_add_channel("EXEC_DEFAULT", channel_number=1, channel_name=self.channel_name)


class LCW_OT_uv_add_uv2(bpy.types.Operator):
    bl_idname = "lcw.uv_add_uv2"
    bl_label = "Add UV2 Channel"
    bl_description = "Runs on all selected mesh objects, creates UV2 when missing, and assigns the entered name to UV2"
    bl_options = {"REGISTER", "UNDO"}

    channel_name: bpy.props.StringProperty(name="UV2 Name", default="Lightmap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_add_channel("EXEC_DEFAULT", channel_number=2, channel_name=self.channel_name)


class LCW_OT_uv_add_uv3(bpy.types.Operator):
    bl_idname = "lcw.uv_add_uv3"
    bl_label = "Add UV3 Channel"
    bl_description = "Runs on all selected mesh objects, creates missing channels up to UV3 when needed, and assigns the entered name to UV3"
    bl_options = {"REGISTER", "UNDO"}

    channel_name: bpy.props.StringProperty(name="UV3 Name", default="UV3")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_add_channel("EXEC_DEFAULT", channel_number=3, channel_name=self.channel_name)


class LCW_OT_uv_set_active_1(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_1"
    bl_label = "Set UV1 Active"
    bl_description = "Runs on all selected mesh objects, sets UV1 active, and deselects objects that do not contain UV1"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_set_active_channel("EXEC_DEFAULT", channel_number=1, deselect_if_missing=True)


class LCW_OT_uv_set_active_2(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_2"
    bl_label = "Set UV2 Active"
    bl_description = "Runs on all selected mesh objects, sets UV2 active, and deselects objects that do not contain UV2"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_set_active_channel("EXEC_DEFAULT", channel_number=2, deselect_if_missing=True)


class LCW_OT_uv_set_active_3(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_3"
    bl_label = "Set UV3 Active"
    bl_description = "Runs on all selected mesh objects, sets UV3 active, and deselects objects that do not contain UV3"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_set_active_channel("EXEC_DEFAULT", channel_number=3, deselect_if_missing=True)


class LCW_OT_uv_rename_uv1(bpy.types.Operator):
    bl_idname = "lcw.uv_rename_uv1"
    bl_label = "Rename UV1"
    bl_description = "Runs on all selected mesh objects, renames UV1, and deselects objects that do not contain UV1"
    bl_options = {"REGISTER", "UNDO"}

    new_name: bpy.props.StringProperty(name="UV1 Name", default="UVMap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_rename_channel("EXEC_DEFAULT", channel_number=1, new_name=self.new_name, deselect_if_missing=True)


class LCW_OT_uv_rename_uv2(bpy.types.Operator):
    bl_idname = "lcw.uv_rename_uv2"
    bl_label = "Rename UV2"
    bl_description = "Runs on all selected mesh objects, renames UV2, and deselects objects that do not contain UV2"
    bl_options = {"REGISTER", "UNDO"}

    new_name: bpy.props.StringProperty(name="UV2 Name", default="Lightmap")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_rename_channel("EXEC_DEFAULT", channel_number=2, new_name=self.new_name, deselect_if_missing=True)


class LCW_OT_uv_rename_uv3(bpy.types.Operator):
    bl_idname = "lcw.uv_rename_uv3"
    bl_label = "Rename UV3"
    bl_description = "Runs on all selected mesh objects, renames UV3, and deselects objects that do not contain UV3"
    bl_options = {"REGISTER", "UNDO"}

    new_name: bpy.props.StringProperty(name="UV3 Name", default="UV3")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_rename_channel("EXEC_DEFAULT", channel_number=3, new_name=self.new_name, deselect_if_missing=True)


CLASSES = (
    LCW_OT_uv_ensure_second,
    LCW_OT_uv_set_active_channel,
    LCW_OT_uv_rename_channel,
    LCW_OT_uv_add_channel,
    LCW_OT_uv_add_uv1,
    LCW_OT_uv_add_uv2,
    LCW_OT_uv_add_uv3,
    LCW_OT_uv_set_active_1,
    LCW_OT_uv_set_active_2,
    LCW_OT_uv_set_active_3,
    LCW_OT_uv_rename_uv1,
    LCW_OT_uv_rename_uv2,
    LCW_OT_uv_rename_uv3,
)
