from __future__ import annotations

import csv
from math import degrees
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

from ..constants import AXIS_ITEMS
from ..utils.common import has_selected_mesh_objects, parse_phrase_list, preserved_selection, selected_mesh_objects, set_active_object


def _connected_edge_components(bm: bmesh.types.BMesh) -> list[set[bmesh.types.BMVert]]:
    graph: dict[bmesh.types.BMVert, set[bmesh.types.BMVert]] = {}
    for edge in bm.edges:
        if not edge.select:
            continue
        v0, v1 = edge.verts
        graph.setdefault(v0, set()).add(v1)
        graph.setdefault(v1, set()).add(v0)

    components: list[set[bmesh.types.BMVert]] = []
    visited: set[bmesh.types.BMVert] = set()
    for vertex in graph:
        if vertex in visited:
            continue
        component: set[bmesh.types.BMVert] = set()
        stack = [vertex]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(neighbor for neighbor in graph[current] if neighbor not in visited)
        components.append(component)
    return components


def _write_csv_row(csv_path: str, header: list[str], row: list[object]) -> None:
    path = Path(csv_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(header)
        writer.writerow(row)


class LCW_OT_kalibra_export_selection_csv(bpy.types.Operator):
    bl_idname = "lcw.kalibra_export_selection_csv"
    bl_label = "Export Selection Overview to CSV"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(name="CSV Path", subtype="FILE_PATH")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        if not self.filepath:
            self.report({"WARNING"}, "Choose a CSV output path.")
            return {"CANCELLED"}

        objects = selected_mesh_objects(context)
        max_shape_keys = max(
            (
                len(obj.data.shape_keys.key_blocks) - 1
                for obj in objects
                if obj.data.shape_keys
            ),
            default=0,
        )
        max_materials = max((len(obj.material_slots) for obj in objects), default=0)

        path = Path(self.filepath)
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            header = ["Object Name"]
            header.extend([f"Shape Key {index + 1}" for index in range(max_shape_keys)])
            header.extend([f"Material {index + 1}" for index in range(max_materials)])
            writer.writerow(header)

            for obj in objects:
                shape_keys = []
                if obj.data.shape_keys:
                    shape_keys = [
                        key.name
                        for key in obj.data.shape_keys.key_blocks
                        if key != obj.data.shape_keys.reference_key
                    ]
                shape_keys.extend(["---"] * (max_shape_keys - len(shape_keys)))
                materials = [slot.material.name for slot in obj.material_slots if slot.material]
                materials.extend(["---"] * (max_materials - len(materials)))
                writer.writerow([obj.name] + shape_keys + materials)

        self.report({"INFO"}, f"Exported selection overview to {self.filepath}.")
        return {"FINISHED"}


class LCW_OT_kalibra_create_combined_bbox(bpy.types.Operator):
    bl_idname = "lcw.kalibra_create_combined_bbox"
    bl_label = "Create Combined Bounding Box"
    bl_options = {"REGISTER", "UNDO"}

    bbox_name: bpy.props.StringProperty(name="Bounding Box Name", default="Combined_BBox")
    csv_path: bpy.props.StringProperty(name="CSV Path", subtype="FILE_PATH", default="")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        objects = selected_mesh_objects(context)
        all_world_corners: list[Vector] = []
        for obj in objects:
            all_world_corners.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)

        min_corner = Vector([min(corner[index] for corner in all_world_corners) for index in range(3)])
        max_corner = Vector([max(corner[index] for corner in all_world_corners) for index in range(3)])
        dimensions = max_corner - min_corner

        corners = [
            Vector((min_corner.x, min_corner.y, min_corner.z)),
            Vector((max_corner.x, min_corner.y, min_corner.z)),
            Vector((max_corner.x, max_corner.y, min_corner.z)),
            Vector((min_corner.x, max_corner.y, min_corner.z)),
            Vector((min_corner.x, min_corner.y, max_corner.z)),
            Vector((max_corner.x, min_corner.y, max_corner.z)),
            Vector((max_corner.x, max_corner.y, max_corner.z)),
            Vector((min_corner.x, max_corner.y, max_corner.z)),
        ]

        mesh_data = bpy.data.meshes.new(f"{self.bbox_name}_Mesh")
        bbox_object = bpy.data.objects.new(self.bbox_name, mesh_data)
        context.collection.objects.link(bbox_object)

        bm = bmesh.new()
        for coordinate in corners:
            bm.verts.new(coordinate)
        bm.verts.ensure_lookup_table()
        for edge_indices in (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ):
            bm.edges.new((bm.verts[edge_indices[0]], bm.verts[edge_indices[1]]))
        bm.to_mesh(mesh_data)
        bm.free()

        with preserved_selection(context):
            set_active_object(context, bbox_object)
            bbox_object.location = context.scene.cursor.location
            bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

        if self.csv_path:
            _write_csv_row(
                self.csv_path,
                ["Label", "X_dim", "Y_dim", "Z_dim", "X_min", "X_max", "Y_min", "Y_max", "Z_min", "Z_max"],
                [
                    self.bbox_name,
                    round(dimensions.x, 4),
                    round(dimensions.y, 4),
                    round(dimensions.z, 4),
                    round(min_corner.x, 4),
                    round(max_corner.x, 4),
                    round(min_corner.y, 4),
                    round(max_corner.y, 4),
                    round(min_corner.z, 4),
                    round(max_corner.z, 4),
                ],
            )

        self.report({"INFO"}, f"Created bounding box '{self.bbox_name}'.")
        return {"FINISHED"}


class LCW_OT_kalibra_create_glass_control(bpy.types.Operator):
    bl_idname = "lcw.kalibra_create_glass_control"
    bl_label = "Create Glass Control Object"
    bl_options = {"REGISTER", "UNDO"}

    search_text: bpy.props.StringProperty(name="Search", default="_Wood")
    replace_text: bpy.props.StringProperty(name="Replace", default="GGB_position")
    angle_threshold: bpy.props.FloatProperty(name="Angle Threshold", default=150.0, min=0.0, max=180.0)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        originals = selected_mesh_objects(context)
        created = 0

        with preserved_selection(context):
            for obj in originals:
                set_active_object(context, obj)
                bpy.ops.object.duplicate()
                duplicate = context.active_object

                if self.search_text and self.search_text in duplicate.name:
                    duplicate.name = duplicate.name.split(self.search_text)[0] + "_" + self.replace_text
                else:
                    duplicate.name = f"{duplicate.name}_{self.replace_text}"
                duplicate.data.name = duplicate.name

                bpy.ops.object.mode_set(mode="EDIT")
                bpy.ops.mesh.select_mode(type="VERT")
                bpy.ops.mesh.select_all(action="DESELECT")

                bm = bmesh.from_edit_mesh(duplicate.data)
                for vertex in bm.verts:
                    linked_edges = list(vertex.link_edges)
                    if len(linked_edges) == 2:
                        vector_1 = (linked_edges[0].other_vert(vertex).co - vertex.co).normalized()
                        vector_2 = (linked_edges[1].other_vert(vertex).co - vertex.co).normalized()
                        try:
                            angle = degrees(vector_1.angle(vector_2))
                        except ValueError:
                            angle = 180.0
                        vertex.select = angle < self.angle_threshold
                    elif len(linked_edges) == 1:
                        vertex.select = True
                bmesh.update_edit_mesh(duplicate.data)

                bpy.ops.mesh.select_all(action="INVERT")
                bpy.ops.mesh.delete(type="VERT")
                bpy.ops.object.mode_set(mode="OBJECT")
                duplicate.data.materials.clear()
                created += 1

        self.report({"INFO"}, f"Created {created} control object(s).")
        return {"FINISHED"}


class LCW_OT_kalibra_scale_loops_xz(bpy.types.Operator):
    bl_idname = "lcw.kalibra_scale_loops_xz"
    bl_label = "Scale Edge Loops in X and Z"
    bl_options = {"REGISTER", "UNDO"}

    scale_amount: bpy.props.FloatProperty(name="Scale Amount", default=0.002)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.active_object and context.active_object.type == "MESH" and context.mode == "EDIT_MESH")

    def execute(self, context: bpy.types.Context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        components = _connected_edge_components(bm)
        if not components:
            self.report({"WARNING"}, "Select at least one edge loop.")
            return {"CANCELLED"}

        processed = 0
        for component in components:
            global_coords = {vertex: obj.matrix_world @ vertex.co for vertex in component}
            xs = [coord.x for coord in global_coords.values()]
            zs = [coord.z for coord in global_coords.values()]
            width = max(xs) - min(xs)
            depth = max(zs) - min(zs)
            if width <= 0.0 or depth <= 0.0 or width < 2 * self.scale_amount or depth < 2 * self.scale_amount:
                continue

            factor_x = (width - 2 * self.scale_amount) / width
            factor_z = (depth - 2 * self.scale_amount) / depth
            center_x = (min(xs) + max(xs)) / 2
            center_z = (min(zs) + max(zs)) / 2

            for vertex, world_coord in global_coords.items():
                new_world = Vector(
                    (
                        center_x + (world_coord.x - center_x) * factor_x,
                        world_coord.y,
                        center_z + (world_coord.z - center_z) * factor_z,
                    )
                )
                vertex.co = obj.matrix_world.inverted() @ new_world
            processed += 1

        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        self.report({"INFO"}, f"Processed {processed} edge loop component(s).")
        return {"FINISHED"}


class LCW_OT_kalibra_scale_loops_x(bpy.types.Operator):
    bl_idname = "lcw.kalibra_scale_loops_x"
    bl_label = "Scale Edge Loops in X"
    bl_options = {"REGISTER", "UNDO"}

    scale_amount: bpy.props.FloatProperty(name="Scale Amount", default=0.002)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.active_object and context.active_object.type == "MESH" and context.mode == "EDIT_MESH")

    def execute(self, context: bpy.types.Context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        components = _connected_edge_components(bm)
        if not components:
            self.report({"WARNING"}, "Select at least one edge loop.")
            return {"CANCELLED"}

        processed = 0
        tolerance = 1e-5
        for component in components:
            global_coords = {vertex: obj.matrix_world @ vertex.co for vertex in component}
            some_coord = next(iter(global_coords.values()))
            if not all(abs(coord.y - some_coord.y) < tolerance and abs(coord.z - some_coord.z) < tolerance for coord in global_coords.values()):
                continue

            xs = [coord.x for coord in global_coords.values()]
            width = max(xs) - min(xs)
            if width <= 0.0 or width < 2 * self.scale_amount:
                continue

            factor = (width - 2 * self.scale_amount) / width
            center_x = (min(xs) + max(xs)) / 2
            for vertex, world_coord in global_coords.items():
                new_world = Vector((center_x + (world_coord.x - center_x) * factor, world_coord.y, world_coord.z))
                vertex.co = obj.matrix_world.inverted() @ new_world
            processed += 1

        bmesh.update_edit_mesh(obj.data, loop_triangles=True)
        self.report({"INFO"}, f"Processed {processed} line component(s).")
        return {"FINISHED"}


class LCW_OT_kalibra_space_vertices_axis(bpy.types.Operator):
    bl_idname = "lcw.kalibra_space_vertices_axis"
    bl_label = "Space Vertices with Axis Falloff"
    bl_options = {"REGISTER", "UNDO"}

    axis: bpy.props.EnumProperty(name="Axis", items=AXIS_ITEMS, default="-X")
    falloff_power: bpy.props.FloatProperty(name="Falloff Power", default=2.4, min=0.01)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return bool(context.active_object and context.active_object.type == "MESH" and context.mode == "EDIT_MESH")

    def execute(self, context: bpy.types.Context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        components = _connected_edge_components(bm)
        if not components:
            self.report({"WARNING"}, "Select at least one edge loop.")
            return {"CANCELLED"}

        axis_index = {"X": 0, "Y": 1, "Z": 2}[self.axis[-1]]
        reverse = not self.axis.startswith("+") and self.axis.startswith("-")

        processed = 0
        for component in components:
            ordered = sorted(component, key=lambda vertex: vertex.co[axis_index], reverse=reverse)
            if len(ordered) < 3:
                continue
            first = ordered[0]
            last = ordered[-1]
            first_position = first.co.copy()
            last_position = last.co.copy()
            intermediates = ordered[1:-1]

            for index, vertex in enumerate(intermediates, start=1):
                normalized = index / (len(intermediates) + 1)
                falloff = normalized ** self.falloff_power
                vertex.co = first_position.lerp(last_position, falloff)
            first.co = first_position
            last.co = last_position
            processed += 1

        bmesh.update_edit_mesh(obj.data)
        self.report({"INFO"}, f"Processed {processed} edge loop component(s).")
        return {"FINISHED"}


CLASSES = (
    LCW_OT_kalibra_export_selection_csv,
    LCW_OT_kalibra_create_combined_bbox,
    LCW_OT_kalibra_create_glass_control,
    LCW_OT_kalibra_scale_loops_xz,
    LCW_OT_kalibra_scale_loops_x,
    LCW_OT_kalibra_space_vertices_axis,
)
