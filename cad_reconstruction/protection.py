"""Edit Mode tools for user-protected faces (BOOLEAN face attribute cad_protected).

Protected faces are kept exactly as authored by every CAD reconstruction run;
features touching them are left unchanged. These operators only edit that
attribute on the active mesh; geometry is never modified.
"""
import bmesh
import bpy
from bpy.props import EnumProperty

from ..cad_mesh_tool.protected import ATTRIBUTE

ACTIONS = (
    ("PROTECT", "Protect Selected", "Mark the selected faces as protected"),
    ("UNPROTECT", "Unprotect Selected", "Remove protection from the selected faces"),
    ("SELECT", "Select Protected", "Select all protected faces"),
    ("CLEAR", "Clear All", "Remove protection from every face of this mesh"),
)


def _face_layer(bm, create):
    layer = bm.faces.layers.bool.get(ATTRIBUTE)
    if layer is None and create:
        layer = bm.faces.layers.bool.new(ATTRIBUTE)
    return layer


def protected_count(obj):
    """Count from object data; in Edit Mode the edit mesh is authoritative."""
    if obj is None or obj.type != "MESH":
        return None
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        layer = _face_layer(bm, False)
        return 0 if layer is None else sum(face[layer] for face in bm.faces)
    from ..cad_mesh_tool.protected import faces_from_mesh
    return len(faces_from_mesh(obj.data))


class LCW_OT_cad_protect_faces(bpy.types.Operator):
    bl_idname = "lcw.cad_protect_faces"
    bl_label = "CAD Protected Faces"
    bl_description = "Edit the protected-face marking used by CAD Mesh Reconstruction"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(name="Action", items=ACTIONS, default="PROTECT")

    @classmethod
    def description(cls, context, properties):
        return next(item[2] for item in ACTIONS if item[0] == properties.action)

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and obj.mode == "EDIT"

    def execute(self, context):
        obj = context.active_object
        existing = obj.data.attributes.get(ATTRIBUTE)
        if existing is not None and (existing.domain != "FACE" or existing.data_type != "BOOLEAN"):
            self.report({"ERROR"}, f"Attribute {ATTRIBUTE} exists with another type or domain")
            return {"CANCELLED"}
        bm = bmesh.from_edit_mesh(obj.data)
        if self.action == "CLEAR":
            layer = _face_layer(bm, False)
            if layer is not None:
                bm.faces.layers.bool.remove(layer)
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({"INFO"}, "Protection cleared")
            return {"FINISHED"}
        if self.action == "SELECT":
            layer = _face_layer(bm, False)
            # Deselect everything first: deselecting a face also deselects
            # vertices it shares with a protected face.
            for face in bm.faces:
                face.select_set(False)
            count = 0
            for face in bm.faces:
                if layer is not None and face[layer]:
                    face.select_set(True)
                    count += 1
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            self.report({"INFO"}, f"{count} protected face(s) selected")
            return {"FINISHED"}
        if not any(face.select for face in bm.faces):
            self.report({"WARNING"}, "Select faces first")
            return {"CANCELLED"}
        # Adding a layer reallocates BMesh face data: create it before
        # collecting face references.
        layer = _face_layer(bm, self.action == "PROTECT")
        selected = [face for face in bm.faces if face.select]
        if layer is not None:
            for face in selected:
                face[layer] = self.action == "PROTECT"
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, f"{len(selected)} face(s) {'protected' if self.action == 'PROTECT' else 'unprotected'}")
        return {"FINISHED"}


CLASSES = (LCW_OT_cad_protect_faces,)
