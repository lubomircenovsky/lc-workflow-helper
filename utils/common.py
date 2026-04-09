from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import bpy

from ..constants import ADDON_PACKAGE, WINDOW_MANAGER_STATE_ID


def addon_preferences(context: bpy.types.Context) -> bpy.types.AddonPreferences:
    return context.preferences.addons[ADDON_PACKAGE].preferences


def is_favorite_action(context: bpy.types.Context, action_id: str) -> bool:
    state = scene_state(context)
    return any(item.action_id == action_id for item in state.favorite_actions)


def wm_state(context: bpy.types.Context):
    return getattr(context.window_manager, WINDOW_MANAGER_STATE_ID)


def scene_state(context: bpy.types.Context):
    return getattr(context.scene, "lcw_scene_state")


def selected_mesh_objects(context: bpy.types.Context) -> list[bpy.types.Object]:
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def active_mesh_object(context: bpy.types.Context) -> bpy.types.Object | None:
    obj = context.active_object
    if obj and obj.type == "MESH":
        return obj
    return None


def has_selected_mesh_objects(context: bpy.types.Context) -> bool:
    return any(obj.type == "MESH" for obj in context.selected_objects)


@contextmanager
def preserved_selection(context: bpy.types.Context) -> Iterator[None]:
    active = context.view_layer.objects.active
    selected = list(context.selected_objects)
    mode = active.mode if active else "OBJECT"
    try:
        yield
    finally:
        if active and active.name in bpy.data.objects and mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except RuntimeError:
                pass
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if active and active.name in bpy.data.objects:
            context.view_layer.objects.active = active
            if mode != "OBJECT":
                try:
                    bpy.ops.object.mode_set(mode=mode)
                except RuntimeError:
                    pass


def set_active_object(context: bpy.types.Context, obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    context.view_layer.objects.active = obj


def ensure_material(material_name: str) -> bpy.types.Material:
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(name=material_name)
    return material


def parse_phrase_list(raw_value: str) -> list[str]:
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def report_info_lines(operator: bpy.types.Operator, lines: list[str]) -> None:
    if not lines:
        return
    operator.report({"INFO"}, " | ".join(lines[:3]))
