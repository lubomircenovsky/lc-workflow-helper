"""Reversible Object Color display for generated CAD results."""

from __future__ import annotations

import bpy

from .jobs import COLORS


_spaces = {}
_original_colors = {}


def is_enabled(space):
    return space is not None and space.as_pointer() in _spaces


def any_enabled():
    return bool(_spaces)


def _status_objects(state):
    seen = set()
    for row in state.results:
        obj = row.output
        if (row.status in COLORS and obj is not None and obj.type == "MESH"
                and obj.get("lcw_cad_run_id") and obj.as_pointer() not in seen):
            seen.add(obj.as_pointer())
            yield obj, COLORS[row.status]
    scene = state.id_data
    for obj in scene.objects:
        status = obj.get("lcw_cad_status")
        if (status in COLORS and obj.type == "MESH" and obj.get("lcw_cad_run_id")
                and obj.as_pointer() not in seen):
            seen.add(obj.as_pointer())
            yield obj, COLORS[status]


def refresh(state):
    if not _spaces:
        return
    for obj, color in _status_objects(state):
        key = obj.as_pointer()
        if key not in _original_colors:
            _original_colors[key] = (obj, tuple(obj.color))
        obj.color = color


def base_color(obj):
    saved = _original_colors.get(obj.as_pointer())
    return saved[1] if saved is not None else tuple(obj.color)


def _restore_space(space, original):
    try:
        shading = space.shading
        shading.type, shading.color_type, shading.wireframe_color_type = original
    except (ReferenceError, RuntimeError, AttributeError):
        pass


def _restore_colors():
    for obj, color in _original_colors.values():
        try:
            obj.color = color
        except (ReferenceError, RuntimeError):
            pass
    _original_colors.clear()


@bpy.app.handlers.persistent
def _before_load(_dummy):
    clear()


def show(space, state=None):
    if space is None or space.type != "VIEW_3D":
        raise ValueError("Open a 3D Viewport first")
    if state is None:
        state = bpy.context.scene.lcw_cad_reconstruction
    key = space.as_pointer()
    if key in _spaces:
        refresh(state)
        return
    shading = space.shading
    original = (shading.type, shading.color_type, shading.wireframe_color_type)
    try:
        if shading.type not in {"SOLID", "WIREFRAME"}:
            shading.type = "SOLID"
        shading.color_type = "OBJECT"
        shading.wireframe_color_type = "OBJECT"
        _spaces[key] = (space, original)
        if _before_load not in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.append(_before_load)
        refresh(state)
    except Exception:
        _spaces.pop(key, None)
        _restore_space(space, original)
        if not _spaces:
            _restore_colors()
        raise


def hide(space):
    clear()


def clear():
    for space, original in tuple(_spaces.values()):
        _restore_space(space, original)
    _spaces.clear()
    _restore_colors()
    if _before_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_before_load)
