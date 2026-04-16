from __future__ import annotations

import bpy

from ..constants import COLOR_BLEND_ITEMS, COLOR_DOMAIN_ITEMS, COLOR_MASK_ITEMS, COLOR_TYPE_ITEMS
from ..utils.color_attributes import blend_rgba, ensure_color_attribute, get_attribute_rgba, set_attribute_rgba
from ..utils.common import has_selected_mesh_objects, selected_mesh_objects


class LCW_OT_color_attribute_initialize(bpy.types.Operator):
    bl_idname = "lcw.color_attribute_initialize"
    bl_label = "Initialize Color Attribute"
    bl_description = "Runs on all selected mesh objects, creates or prepares a color attribute with the entered name, domain, and data type, and fills it with the selected color. Replace Existing recreates an attribute with the same name"
    bl_options = {"REGISTER", "UNDO"}

    attribute_name: bpy.props.StringProperty(name="Attribute Name", default="Color")
    domain: bpy.props.EnumProperty(name="Domain", items=COLOR_DOMAIN_ITEMS, default="CORNER")
    data_type: bpy.props.EnumProperty(name="Data Type", items=COLOR_TYPE_ITEMS, default="BYTE_COLOR")
    replace_existing: bpy.props.BoolProperty(name="Replace Existing", default=False)
    color: bpy.props.FloatVectorProperty(
        name="Initialize Color",
        subtype="COLOR_GAMMA",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        created = 0
        for obj in selected_mesh_objects(context):
            ensure_color_attribute(
                obj.data,
                self.attribute_name,
                self.domain,
                self.data_type,
                self.replace_existing,
                tuple(self.color),
            )
            created += 1
        self.report({"INFO"}, f"Prepared color attribute on {created} object(s).")
        return {"FINISHED"}


class LCW_OT_color_attribute_apply(bpy.types.Operator):
    bl_idname = "lcw.color_attribute_apply"
    bl_label = "Apply Vertex Colors"
    bl_description = "Applies the selected color to the current color attribute on selected mesh objects. In Edit Mode it temporarily switches to Object Mode, then restores Edit Mode when finished. Mask Type controls whether selected faces or selected vertices drive the update, and Blend Mode controls how the new color is combined with existing values"
    bl_options = {"REGISTER", "UNDO"}

    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype="COLOR_GAMMA",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )
    mask_type: bpy.props.EnumProperty(name="Mask Type", items=COLOR_MASK_ITEMS, default="FACE")
    blend_mode: bpy.props.EnumProperty(name="Blend Mode", items=COLOR_BLEND_ITEMS, default="SET")
    attribute_name: bpy.props.StringProperty(name="Attribute Name", default="Color")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context) and context.active_object is not None

    def execute(self, context: bpy.types.Context):
        original_mode = context.mode
        if original_mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="OBJECT")

        updated_objects = 0
        for obj in selected_mesh_objects(context):
            mesh = obj.data
            attribute = mesh.color_attributes.get(self.attribute_name)
            if attribute is None:
                attribute = ensure_color_attribute(mesh, self.attribute_name)

            selected_vertices = {vertex.index for vertex in mesh.vertices if vertex.select}
            selected_polygons = {polygon.index for polygon in mesh.polygons if polygon.select}

            if attribute.domain == "POINT":
                updated_vertices: set[int] = set()
                for polygon in mesh.polygons:
                    use_polygon = False
                    if self.mask_type == "FACE" and polygon.index in selected_polygons:
                        use_polygon = True
                    elif self.mask_type == "VERTEX" and any(index in selected_vertices for index in polygon.vertices):
                        use_polygon = True
                    if not use_polygon:
                        continue
                    updated_vertices.update(polygon.vertices)

                for vertex_index in updated_vertices:
                    color_value = attribute.data[vertex_index]
                    existing = get_attribute_rgba(color_value)
                    set_attribute_rgba(color_value, blend_rgba(existing, tuple(self.color), self.blend_mode))
            else:
                for polygon in mesh.polygons:
                    use_polygon = False
                    if self.mask_type == "FACE" and polygon.index in selected_polygons:
                        use_polygon = True
                    elif self.mask_type == "VERTEX" and any(index in selected_vertices for index in polygon.vertices):
                        use_polygon = True
                    if not use_polygon:
                        continue

                    for loop_index in polygon.loop_indices:
                        color_value = attribute.data[loop_index]
                        existing = get_attribute_rgba(color_value)
                        set_attribute_rgba(color_value, blend_rgba(existing, tuple(self.color), self.blend_mode))
            updated_objects += 1

        if original_mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")

        self.report({"INFO"}, f"Updated colors on {updated_objects} object(s).")
        return {"FINISHED"}


CLASSES = (
    LCW_OT_color_attribute_initialize,
    LCW_OT_color_attribute_apply,
)
