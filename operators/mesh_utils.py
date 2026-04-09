from __future__ import annotations

import re

import bpy

from ..utils.common import has_selected_mesh_objects, preserved_selection, selected_mesh_objects, set_active_object


class LCW_OT_mesh_set_data_names(bpy.types.Operator):
    bl_idname = "lcw.mesh_set_data_names"
    bl_label = "Set Mesh Data Names"
    bl_description = "Rename mesh datablocks of selected mesh objects so each datablock matches its object name"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        updated = 0
        for obj in selected_mesh_objects(context):
            obj.data.name = obj.name
            updated += 1
        self.report({"INFO"}, f"Updated mesh data names on {updated} object(s).")
        return {"FINISHED"}


class LCW_OT_mesh_clear_custom_normals(bpy.types.Operator):
    bl_idname = "lcw.mesh_clear_custom_normals"
    bl_label = "Clear Custom Normals"
    bl_description = "Clear custom split normals on all selected mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        processed = 0
        with preserved_selection(context):
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for obj in selected_mesh_objects(context):
                set_active_object(context, obj)
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                processed += 1
        self.report({"INFO"}, f"Cleared custom normals on {processed} object(s).")
        return {"FINISHED"}


class LCW_OT_mesh_reveal_in_edit_mode(bpy.types.Operator):
    bl_idname = "lcw.mesh_reveal_in_edit_mode"
    bl_label = "Reveal Mesh in Edit Mode"
    bl_description = "Temporarily enters Edit Mode on each selected mesh object and reveals hidden geometry"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        processed = 0
        with preserved_selection(context):
            if context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            for obj in selected_mesh_objects(context):
                set_active_object(context, obj)
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.reveal()
                bpy.ops.object.mode_set(mode="OBJECT")
                processed += 1
        self.report({"INFO"}, f"Revealed hidden geometry on {processed} object(s).")
        return {"FINISHED"}


class LCW_OT_mesh_progressive_offset_y(bpy.types.Operator):
    bl_idname = "lcw.mesh_progressive_offset_y"
    bl_label = "Progressive Cursor Offset"
    bl_description = "Move selected mesh objects to the 3D cursor, keep the first object at the cursor, then offset each next object by the step amount on the enabled axes"
    bl_options = {"REGISTER", "UNDO"}

    base_offset: bpy.props.FloatProperty(name="Offset Step", default=1.0)
    use_axis_x: bpy.props.BoolProperty(name="Use X", default=False)
    use_axis_y: bpy.props.BoolProperty(name="Use Y", default=True)
    use_axis_z: bpy.props.BoolProperty(name="Use Z", default=False)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        if not any((self.use_axis_x, self.use_axis_y, self.use_axis_z)):
            self.report({"WARNING"}, "Enable at least one axis for the progressive offset.")
            return {"CANCELLED"}

        cursor_location = context.scene.cursor.location.copy()
        for index, obj in enumerate(selected_mesh_objects(context)):
            step = self.base_offset * index
            obj.location = cursor_location.copy()
            if self.use_axis_x:
                obj.location.x += step
            if self.use_axis_y:
                obj.location.y += step
            if self.use_axis_z:
                obj.location.z += step
        context.view_layer.update()
        self.report({"INFO"}, "Offset selected objects from the 3D cursor.")
        return {"FINISHED"}


class LCW_OT_object_rename_dot_suffix(bpy.types.Operator):
    bl_idname = "lcw.object_rename_dot_suffix"
    bl_label = "Rename Dot Suffix to Underscore"
    bl_description = "Rename selected objects from Blender's .001 suffix style to underscore numbering and update matching datablock names"
    bl_options = {"REGISTER", "UNDO"}

    zfill_width: bpy.props.IntProperty(name="Suffix Digits", default=2, min=1, max=6)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.selected_objects)

    def execute(self, context: bpy.types.Context):
        pattern = re.compile(r"(.*)\.(\d{3})$")
        renamed = 0
        for obj in context.selected_objects:
            match = pattern.match(obj.name)
            if not match:
                continue
            new_name = f"{match.group(1)}_{int(match.group(2)):0{self.zfill_width}d}"
            obj.name = new_name
            if getattr(obj, "data", None) and hasattr(obj.data, "name"):
                obj.data.name = new_name
            renamed += 1
        self.report({"INFO"}, f"Renamed {renamed} object(s).")
        return {"FINISHED"}


CLASSES = (
    LCW_OT_mesh_set_data_names,
    LCW_OT_mesh_clear_custom_normals,
    LCW_OT_mesh_reveal_in_edit_mode,
    LCW_OT_mesh_progressive_offset_y,
    LCW_OT_object_rename_dot_suffix,
)
