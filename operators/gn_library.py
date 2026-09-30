"""Append self-contained Geometry Nodes assets from the extension package."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import bpy
from bpy.props import EnumProperty


ASSET_ID = "screw_replace"
ROOT_NAME = "GN_Screw_Replace_By_Geometry"
CHILD_NAME = "GN_Screw_Analyze_Head_and_Axis"
MIN_VERSION = (5, 2, 0)
ASSET_PATH = Path(__file__).resolve().parent.parent / "gn_library" / "screw_replace.blend"
TAG_ASSET = "lcw_gn_library_asset"
TAG_INSTANCE = "lcw_gn_library_instance"
TAG_PRIMARY = "lcw_gn_library_primary"


def supported_version() -> bool:
    return bpy.app.version >= MIN_VERSION


def _primary_group():
    for group in bpy.data.node_groups:
        if (
            group.bl_idname == "GeometryNodeTree"
            and group.get(TAG_ASSET) == ASSET_ID
            and group.get(TAG_PRIMARY, False)
        ):
            return group
    return None


def _rollback(groups_before: set, texts_before: set) -> None:
    for group in tuple(bpy.data.node_groups):
        if group not in groups_before:
            bpy.data.node_groups.remove(group, do_unlink=True)
    for text in tuple(bpy.data.texts):
        if text not in texts_before:
            bpy.data.texts.remove(text, do_unlink=True)


def _append_group(*, primary: bool):
    if not ASSET_PATH.is_file():
        raise RuntimeError("Bundled GN library file is missing")

    with bpy.data.libraries.load(str(ASSET_PATH), link=False) as (source, target):
        required = {ROOT_NAME, CHILD_NAME}
        if not required.issubset(source.node_groups):
            raise RuntimeError("Bundled GN library is missing a required node group")
        target.node_groups = [ROOT_NAME, CHILD_NAME]
        target.texts = list(source.texts)

    root, child = target.node_groups
    if root is None or child is None:
        raise RuntimeError("Could not append the bundled node groups")
    if root.bl_idname != "GeometryNodeTree" or child.bl_idname != "GeometryNodeTree":
        raise RuntimeError("The bundled data does not contain Geometry Nodes groups")
    if not any(node.type == "GROUP" and node.node_tree == child for node in root.nodes):
        raise RuntimeError("The appended group lost its internal dependency")

    instance_id = uuid4().hex
    for group in (root, child):
        group[TAG_ASSET] = ASSET_ID
        group[TAG_INSTANCE] = instance_id
    root[TAG_PRIMARY] = primary
    return root


class LCW_OT_gn_library_add(bpy.types.Operator):
    bl_idname = "lcw.gn_library_add"
    bl_label = "Add GN Library Asset"
    bl_description = "Load the bundled screw replacement Geometry Nodes group"
    bl_options = {"REGISTER", "UNDO"}

    action: EnumProperty(
        items=(("LOAD", "Load Group", "Load the group into this file"),
               ("MODIFIER", "Add Modifier", "Add a Geometry Nodes modifier to the active object")),
        default="LOAD",
    )

    def execute(self, context: bpy.types.Context):
        if not supported_version():
            self.report({"ERROR"}, "This GN Library asset requires Blender 5.2 or newer")
            return {"CANCELLED"}

        obj = context.active_object if self.action == "MODIFIER" else None
        if self.action == "MODIFIER" and (
            obj is None or obj.library is not None or obj.override_library is not None
            or not hasattr(obj, "modifiers")
        ):
            self.report({"ERROR"}, "Choose an editable active object for the Geometry Nodes modifier")
            return {"CANCELLED"}

        groups_before = set(bpy.data.node_groups)
        texts_before = set(bpy.data.texts)
        modifier = None
        try:
            mode = context.window_manager.lcw_state.gn_library_mode
            group = _primary_group() if mode == "REUSE" else None
            if group is None:
                group = _append_group(primary=(mode == "REUSE"))
            if self.action == "MODIFIER":
                modifier = obj.modifiers.new(name="Screw replacement (procedural)", type="NODES")
                modifier.node_group = group
            self.report({"INFO"}, f"{'Added modifier with' if modifier else 'Loaded'} {group.name}")
            return {"FINISHED"}
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
            if modifier is not None:
                obj.modifiers.remove(modifier)
            _rollback(groups_before, texts_before)
            self.report({"ERROR"}, f"GN Library: {exc}")
            return {"CANCELLED"}


CLASSES = (LCW_OT_gn_library_add,)
