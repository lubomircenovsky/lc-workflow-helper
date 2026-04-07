from __future__ import annotations

import bmesh
import bpy

from ..utils.common import ensure_material, has_selected_mesh_objects, preserved_selection, selected_mesh_objects, set_active_object


class LCW_OT_material_assign_object(bpy.types.Operator):
    bl_idname = "lcw.material_assign_object"
    bl_label = "Assign Material to Selected Objects"
    bl_options = {"REGISTER", "UNDO"}

    material_name: bpy.props.StringProperty(name="Material", default="cavity_bake_v2")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        material = ensure_material(self.material_name)
        updated = 0
        for obj in selected_mesh_objects(context):
            if not obj.material_slots:
                obj.data.materials.append(material)
                updated += 1
                continue
            for slot in obj.material_slots:
                slot.material = material
            updated += 1
        self.report({"INFO"}, f"Assigned material '{material.name}' to {updated} object(s).")
        return {"FINISHED"}


class LCW_OT_material_toggle_link(bpy.types.Operator):
    bl_idname = "lcw.material_toggle_link"
    bl_label = "Toggle Material Link"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        toggled = 0
        for obj in selected_mesh_objects(context):
            for slot in obj.material_slots:
                slot.link = "DATA" if slot.link == "OBJECT" else "OBJECT"
                toggled += 1
        self.report({"INFO"}, f"Toggled {toggled} material slot link(s).")
        return {"FINISHED"}


class LCW_OT_material_remove_unused_slots(bpy.types.Operator):
    bl_idname = "lcw.material_remove_unused_slots"
    bl_label = "Remove Unused Material Slots"
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
                bpy.ops.object.material_slot_remove_unused()
                processed += 1
        self.report({"INFO"}, f"Processed {processed} object(s).")
        return {"FINISHED"}


class LCW_OT_material_assign_selected_faces(bpy.types.Operator):
    bl_idname = "lcw.material_assign_selected_faces"
    bl_label = "Assign Material to Selected Faces"
    bl_options = {"REGISTER", "UNDO"}

    material_name: bpy.props.StringProperty(name="Material", default="00_Config_wood_int")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "EDIT_MESH" and has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        material = ensure_material(self.material_name)
        assigned_faces = 0

        with preserved_selection(context):
            bpy.ops.object.mode_set(mode="OBJECT")
            for obj in selected_mesh_objects(context):
                set_active_object(context, obj)
                bpy.ops.object.mode_set(mode="EDIT")
                bm = bmesh.from_edit_mesh(obj.data)
                if material.name not in obj.data.materials:
                    obj.data.materials.append(material)
                material_index = obj.data.materials.find(material.name)

                for face in bm.faces:
                    if face.select:
                        face.material_index = material_index
                        assigned_faces += 1
                bmesh.update_edit_mesh(obj.data)
                bpy.ops.object.mode_set(mode="OBJECT")

        self.report({"INFO"}, f"Assigned material to {assigned_faces} face(s).")
        return {"FINISHED"}


CLASSES = (
    LCW_OT_material_assign_object,
    LCW_OT_material_toggle_link,
    LCW_OT_material_remove_unused_slots,
    LCW_OT_material_assign_selected_faces,
)
