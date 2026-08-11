from __future__ import annotations

import bmesh
import bpy

from ..utils.common import has_selected_mesh_objects, scene_state, selected_mesh_objects


UV_SEAM_TOLERANCE = 1e-6


def _uv_samples_are_discontinuous(
    samples: list[dict[int, tuple[float, float]]],
    vertex_indices: tuple[int, int],
) -> bool:
    if len(samples) < 2:
        return False

    tolerance_squared = UV_SEAM_TOLERANCE * UV_SEAM_TOLERANCE
    reference = samples[0]
    for sample in samples[1:]:
        for vertex_index in vertex_indices:
            reference_uv = reference.get(vertex_index)
            sample_uv = sample.get(vertex_index)
            if reference_uv is None or sample_uv is None:
                return True
            delta_u = reference_uv[0] - sample_uv[0]
            delta_v = reference_uv[1] - sample_uv[1]
            if (delta_u * delta_u) + (delta_v * delta_v) > tolerance_squared:
                return True
    return False


def _rebuild_object_mode_seams(mesh: bpy.types.Mesh, uv_layer_name: str) -> None:
    uv_layer = mesh.uv_layers.get(uv_layer_name)
    if uv_layer is None:
        raise RuntimeError(f"UV layer '{uv_layer_name}' was not found.")

    samples_by_edge: dict[int, list[dict[int, tuple[float, float]]]] = {
        edge.index: [] for edge in mesh.edges
    }
    for polygon in mesh.polygons:
        loop_indices = tuple(polygon.loop_indices)
        for offset, loop_index in enumerate(loop_indices):
            next_loop_index = loop_indices[(offset + 1) % len(loop_indices)]
            loop = mesh.loops[loop_index]
            next_loop = mesh.loops[next_loop_index]
            samples_by_edge[loop.edge_index].append(
                {
                    loop.vertex_index: tuple(uv_layer.data[loop_index].uv),
                    next_loop.vertex_index: tuple(uv_layer.data[next_loop_index].uv),
                }
            )

    for edge in mesh.edges:
        edge.use_seam = _uv_samples_are_discontinuous(
            samples_by_edge[edge.index],
            tuple(edge.vertices),
        )
    mesh.update()


def _rebuild_edit_mode_seams(mesh: bpy.types.Mesh, uv_layer_name: str) -> None:
    edit_mesh = bmesh.from_edit_mesh(mesh)
    uv_layer = edit_mesh.loops.layers.uv.get(uv_layer_name)
    if uv_layer is None:
        raise RuntimeError(f"UV layer '{uv_layer_name}' was not found in Edit Mode.")

    edit_mesh.verts.ensure_lookup_table()
    for edge in edit_mesh.edges:
        samples: list[dict[int, tuple[float, float]]] = []
        for loop in edge.link_loops:
            next_loop = loop.link_loop_next
            samples.append(
                {
                    loop.vert.index: tuple(loop[uv_layer].uv),
                    next_loop.vert.index: tuple(next_loop[uv_layer].uv),
                }
            )
        edge.seam = _uv_samples_are_discontinuous(
            samples,
            (edge.verts[0].index, edge.verts[1].index),
        )
    bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)


def rebuild_uv_seams_from_layer(mesh: bpy.types.Mesh, uv_layer_name: str) -> None:
    if mesh.is_editmode:
        _rebuild_edit_mode_seams(mesh, uv_layer_name)
    else:
        _rebuild_object_mode_seams(mesh, uv_layer_name)


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
        rebuilt_meshes = 0
        rebuild_failures = 0
        processed_meshes: set[int] = set()
        rebuild_seams = scene_state(context).uv_rebuild_seams_on_switch

        for obj in selected_mesh_objects(context):
            if len(obj.data.uv_layers) > target_index:
                obj.data.uv_layers.active_index = target_index
                updated += 1
                mesh_pointer = obj.data.as_pointer()
                if rebuild_seams and mesh_pointer not in processed_meshes:
                    processed_meshes.add(mesh_pointer)
                    try:
                        rebuild_uv_seams_from_layer(
                            obj.data,
                            obj.data.uv_layers[target_index].name,
                        )
                        rebuilt_meshes += 1
                    except (RuntimeError, ValueError):
                        rebuild_failures += 1
            elif self.deselect_if_missing:
                obj.select_set(False)
                deselected += 1

        message = f"Updated {updated} object(s), deselected {deselected}."
        if rebuild_seams:
            message = (
                f"{message} Rebuilt seams on {rebuilt_meshes} mesh datablock(s)"
                f"{f'; {rebuild_failures} failed' if rebuild_failures else ''}."
            )
        self.report({"WARNING"} if rebuild_failures else {"INFO"}, message)
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


class LCW_OT_uv_remove_channel(bpy.types.Operator):
    bl_idname = "lcw.uv_remove_channel"
    bl_label = "Remove UV Channel"
    bl_description = "Runs on all selected mesh objects and removes the requested UV channel after confirmation"
    bl_options = {"REGISTER", "UNDO"}

    channel_number: bpy.props.IntProperty(name="UV Channel", default=2, min=1, max=5)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        selected_count = len(selected_mesh_objects(context))
        channel_label = f"UV{self.channel_number}"
        object_label = "object" if selected_count == 1 else "objects"
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Remove UV Channel",
            message=f"Remove {channel_label} from {selected_count} selected mesh {object_label}?",
            confirm_text="Remove",
            icon="WARNING",
        )

    def execute(self, context: bpy.types.Context):
        target_index = self.channel_number - 1
        removed_meshes = 0
        skipped_objects = 0
        affected_objects = 0
        processed_meshes: set[int] = set()

        for obj in selected_mesh_objects(context):
            uv_layers = obj.data.uv_layers
            if len(uv_layers) <= target_index:
                skipped_objects += 1
                continue

            mesh_pointer = obj.data.as_pointer()
            if mesh_pointer in processed_meshes:
                affected_objects += 1
                continue

            uv_layers.remove(uv_layers[target_index])
            processed_meshes.add(mesh_pointer)
            removed_meshes += 1
            affected_objects += 1

        self.report(
            {"INFO"},
            (
                f"Removed UV{self.channel_number} from {removed_meshes} mesh datablock(s), "
                f"affecting {affected_objects} object(s); skipped {skipped_objects} object(s)."
            ),
        )
        return {"FINISHED"}


class LCW_OT_uv_set_active_1(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_1"
    bl_label = "Set UV1 Active"
    bl_description = "Set UV1 active on selected mesh objects, optionally rebuild seams from its islands, and deselect objects without UV1"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_set_active_channel("EXEC_DEFAULT", channel_number=1, deselect_if_missing=True)


class LCW_OT_uv_set_active_2(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_2"
    bl_label = "Set UV2 Active"
    bl_description = "Set UV2 active on selected mesh objects, optionally rebuild seams from its islands, and deselect objects without UV2"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return has_selected_mesh_objects(context)

    def execute(self, context: bpy.types.Context):
        return bpy.ops.lcw.uv_set_active_channel("EXEC_DEFAULT", channel_number=2, deselect_if_missing=True)


class LCW_OT_uv_set_active_3(bpy.types.Operator):
    bl_idname = "lcw.uv_set_active_3"
    bl_label = "Set UV3 Active"
    bl_description = "Set UV3 active on selected mesh objects, optionally rebuild seams from its islands, and deselect objects without UV3"
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
    LCW_OT_uv_remove_channel,
    LCW_OT_uv_set_active_1,
    LCW_OT_uv_set_active_2,
    LCW_OT_uv_set_active_3,
    LCW_OT_uv_rename_uv1,
    LCW_OT_uv_rename_uv2,
    LCW_OT_uv_rename_uv3,
)
