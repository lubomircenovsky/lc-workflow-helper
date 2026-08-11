from __future__ import annotations

import re

import bpy

from ..utils.common import has_selected_mesh_objects, preserved_selection, selected_mesh_objects, set_active_object


MESH_DATA_SUFFIX_PATTERN = re.compile(r"^(?P<base>.+)\.(?P<suffix>\d{3,})$")

RELINK_STATUS_READY = "READY"
RELINK_STATUS_ALREADY_BASE = "ALREADY_BASE"
RELINK_STATUS_UNRESOLVED = "UNRESOLVED"

RELINK_STATUS_LABELS = {
    RELINK_STATUS_READY: "Ready",
    RELINK_STATUS_ALREADY_BASE: "Already Base",
    RELINK_STATUS_UNRESOLVED: "Unresolved",
}

RELINK_STATUS_ICONS = {
    RELINK_STATUS_READY: "CHECKMARK",
    RELINK_STATUS_ALREADY_BASE: "INFO",
    RELINK_STATUS_UNRESOLVED: "ERROR",
}


class LCW_PG_MeshRelinkPreviewItem(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty(name="Object")
    current_mesh_name: bpy.props.StringProperty(name="Current Mesh")
    target_mesh_name: bpy.props.StringProperty(name="Target Mesh")
    status: bpy.props.StringProperty(name="Status")
    details: bpy.props.StringProperty(name="Details")


def _object_is_editable(obj: bpy.types.Object) -> bool:
    return bool(
        getattr(
            obj,
            "is_editable",
            obj.library is None or obj.override_library is not None,
        )
    )


def _classify_mesh_relink(obj: bpy.types.Object) -> tuple[str, str, str]:
    current_mesh = obj.data
    match = MESH_DATA_SUFFIX_PATTERN.fullmatch(current_mesh.name)
    if match is None:
        return RELINK_STATUS_ALREADY_BASE, "", "Mesh name has no Blender numeric suffix."

    target_name = match.group("base")
    target_mesh = bpy.data.meshes.get(target_name)
    if target_mesh is None:
        return RELINK_STATUS_UNRESOLVED, target_name, "Original mesh datablock was not found."
    if not _object_is_editable(obj):
        return RELINK_STATUS_UNRESOLVED, target_name, "Object data is not editable."
    return RELINK_STATUS_READY, target_name, "Original mesh datablock found."


class LCW_UL_mesh_relink_preview(bpy.types.UIList):
    bl_idname = "LCW_UL_mesh_relink_preview"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index=0,
        flt_flag=0,
    ):
        row = layout.row(align=True)
        row.label(text=item.object_name, icon=RELINK_STATUS_ICONS.get(item.status, "QUESTION"))
        row.label(text=item.current_mesh_name)
        row.label(text=item.target_mesh_name or "-")
        row.label(text=RELINK_STATUS_LABELS.get(item.status, item.status))


class LCW_OT_mesh_relink_original_data(bpy.types.Operator):
    bl_idname = "lcw.mesh_relink_original_data"
    bl_label = "Relink Original Mesh Data"
    bl_description = (
        "Review selected mesh objects and relink Blender-numbered mesh copies "
        "to the exact original mesh datablock"
    )
    bl_options = {"REGISTER", "UNDO"}

    preview_items: bpy.props.CollectionProperty(type=LCW_PG_MeshRelinkPreviewItem)
    preview_index: bpy.props.IntProperty(name="Preview Item", default=0, min=0)
    select_unresolved_after: bpy.props.BoolProperty(
        name="Select Unresolved Objects After Relink",
        description="After relinking, select objects that could not be resolved safely",
        default=True,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and has_selected_mesh_objects(context)

    def _populate_preview(self, context: bpy.types.Context) -> None:
        self.preview_items.clear()
        for obj in sorted(selected_mesh_objects(context), key=lambda item: item.name.casefold()):
            status, target_name, details = _classify_mesh_relink(obj)
            item = self.preview_items.add()
            item.object_name = obj.name
            item.current_mesh_name = obj.data.name
            item.target_mesh_name = target_name
            item.status = status
            item.details = details

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        self._populate_preview(context)
        self.preview_index = 0
        return context.window_manager.invoke_props_dialog(self, width=860)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        ready_count = sum(item.status == RELINK_STATUS_READY for item in self.preview_items)
        already_base_count = sum(
            item.status == RELINK_STATUS_ALREADY_BASE for item in self.preview_items
        )
        unresolved_count = sum(
            item.status == RELINK_STATUS_UNRESOLVED for item in self.preview_items
        )

        summary = layout.box()
        row = summary.row(align=True)
        row.label(text=f"Ready: {ready_count}", icon="CHECKMARK")
        row.label(text=f"Already Base: {already_base_count}", icon="INFO")
        row.label(text=f"Unresolved: {unresolved_count}", icon="ERROR")

        header = layout.row(align=True)
        header.label(text="Object")
        header.label(text="Current Mesh")
        header.label(text="Target Mesh")
        header.label(text="Status")
        layout.template_list(
            "LCW_UL_mesh_relink_preview",
            "",
            self,
            "preview_items",
            self,
            "preview_index",
            rows=min(12, max(4, len(self.preview_items))),
        )

        if self.preview_items:
            active_index = min(self.preview_index, len(self.preview_items) - 1)
            active_item = self.preview_items[active_index]
            layout.label(text=active_item.details, icon=RELINK_STATUS_ICONS.get(active_item.status, "INFO"))
        layout.prop(self, "select_unresolved_after")
        layout.label(text="Detached bake meshes are not deleted and the operation supports Undo.", icon="INFO")

    def execute(self, context: bpy.types.Context):
        if len(self.preview_items) == 0:
            self._populate_preview(context)

        relinked = 0
        already_base = 0
        unresolved_count = 0
        unresolved_objects: list[bpy.types.Object] = []
        unresolved_names: set[str] = set()

        def add_unresolved(obj: bpy.types.Object | None) -> None:
            nonlocal unresolved_count
            unresolved_count += 1
            if obj is not None and obj.name not in unresolved_names:
                unresolved_names.add(obj.name)
                unresolved_objects.append(obj)

        for item in self.preview_items:
            obj = bpy.data.objects.get(item.object_name)
            if item.status == RELINK_STATUS_ALREADY_BASE:
                already_base += 1
                continue
            if item.status != RELINK_STATUS_READY:
                add_unresolved(obj)
                continue

            target_mesh = bpy.data.meshes.get(item.target_mesh_name)
            if (
                obj is None
                or obj.type != "MESH"
                or obj.data.name != item.current_mesh_name
                or target_mesh is None
                or not _object_is_editable(obj)
            ):
                add_unresolved(obj)
                continue

            try:
                obj.data = target_mesh
                relinked += 1
            except (AttributeError, RuntimeError, TypeError):
                add_unresolved(obj)

        selected_unresolved = 0
        if self.select_unresolved_after and unresolved_objects:
            bpy.ops.object.select_all(action="DESELECT")
            first_selected = None
            for obj in unresolved_objects:
                try:
                    obj.select_set(True)
                    selected_unresolved += 1
                    if first_selected is None:
                        first_selected = obj
                except RuntimeError:
                    continue
            if first_selected is not None:
                context.view_layer.objects.active = first_selected

        level = {"WARNING"} if unresolved_count else {"INFO"}
        self.report(
            level,
            (
                f"Relinked {relinked} object(s); {already_base} already used base-named data; "
                f"{unresolved_count} unresolved"
                f"{f', selected {selected_unresolved}' if self.select_unresolved_after and unresolved_objects else ''}."
            ),
        )
        return {"FINISHED"}


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
    LCW_PG_MeshRelinkPreviewItem,
    LCW_UL_mesh_relink_preview,
    LCW_OT_mesh_relink_original_data,
    LCW_OT_mesh_set_data_names,
    LCW_OT_mesh_clear_custom_normals,
    LCW_OT_mesh_reveal_in_edit_mode,
    LCW_OT_mesh_progressive_offset_y,
    LCW_OT_object_rename_dot_suffix,
)
