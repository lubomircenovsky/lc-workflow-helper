from __future__ import annotations

import bmesh
import bpy

from ..utils.common import ensure_material, has_selected_mesh_objects, preserved_selection, scene_state, selected_mesh_objects, set_active_object


def _set_material_slot_link(context: bpy.types.Context, target_link: str) -> int:
    updated = 0
    for obj in selected_mesh_objects(context):
        for slot in obj.material_slots:
            if slot.link != target_link:
                slot.link = target_link
                updated += 1
    return updated


class LCW_OT_material_assign_object(bpy.types.Operator):
    bl_idname = "lcw.material_assign_object"
    bl_label = "Assign Material to Selected Objects"
    bl_description = "Runs on all selected mesh objects, creates a material slot when needed, and assigns the entered material to all slots on each object"
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


class LCW_OT_material_use_quick_name(bpy.types.Operator):
    bl_idname = "lcw.material_use_quick_name"
    bl_label = "Use Quick Material Name"
    bl_description = "Copies the stored quick material name into the main material field for Assign Material to Selected Objects"
    bl_options = {"REGISTER", "UNDO"}

    slot_index: bpy.props.IntProperty(name="Quick Slot", default=1, min=1, max=3)

    def execute(self, context: bpy.types.Context):
        state = context.window_manager.lcw_state
        file_state = scene_state(context)
        quick_name = getattr(file_state, f"material_quick_name_{self.slot_index}", "").strip()
        if not quick_name:
            self.report({"WARNING"}, f"Quick slot {self.slot_index} is empty.")
            return {"CANCELLED"}
        state.material_name = quick_name
        self.report({"INFO"}, f"Loaded material name from quick slot {self.slot_index}.")
        return {"FINISHED"}


class LCW_OT_material_toggle_link(bpy.types.Operator):
    bl_idname = "lcw.material_toggle_link"
    bl_label = "Toggle Slot Link"
    bl_description = "Runs on all selected mesh objects and inverts each material slot link between Object and Data. Mixed states are only swapped, not unified"
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


class LCW_OT_material_link_slots_data(bpy.types.Operator):
    bl_idname = "lcw.material_link_slots_data"
    bl_label = "Link Slots to Data"
    bl_description = "Runs on all selected mesh objects and sets every material slot link to Data so mixed states are unified"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        updated = _set_material_slot_link(context, "DATA")
        self.report({"INFO"}, f"Set {updated} material slot link(s) to Data.")
        return {"FINISHED"}


class LCW_OT_material_link_slots_object(bpy.types.Operator):
    bl_idname = "lcw.material_link_slots_object"
    bl_label = "Link Slots to Object"
    bl_description = "Runs on all selected mesh objects and sets every material slot link to Object so mixed states are unified"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        updated = _set_material_slot_link(context, "OBJECT")
        self.report({"INFO"}, f"Set {updated} material slot link(s) to Object.")
        return {"FINISHED"}


class LCW_OT_material_remove_unused_slots(bpy.types.Operator):
    bl_idname = "lcw.material_remove_unused_slots"
    bl_label = "Remove Unused Material Slots"
    bl_description = "Runs on all selected mesh objects, temporarily switches to Object Mode if needed, and removes unused material slots"
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
    bl_description = "Runs in Edit Mode on selected mesh objects, adds the entered material to slots when missing, and assigns it only to selected faces"
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
    LCW_OT_material_use_quick_name,
    LCW_OT_material_toggle_link,
    LCW_OT_material_link_slots_data,
    LCW_OT_material_link_slots_object,
    LCW_OT_material_remove_unused_slots,
    LCW_OT_material_assign_selected_faces,
)
