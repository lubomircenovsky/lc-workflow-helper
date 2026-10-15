"""Panel icons: category header icons and result status icons.

Callers never pick an icon identifier directly. They ask for a category or a
status and splat the returned keyword arguments into ``label()``/``operator()``,
so the source of the icon (a built-in Blender icon now, a custom colored PNG
once assets are loaded) can change without touching any panel code.
"""
from __future__ import annotations

# Built-in icon per LC Workflow category; keys follow constants.PANEL_LABELS
# plus the two panels nested under "Project specific tools".
CATEGORY_ICONS = {
    "scene_info": "INFO",
    "favorites": "SOLO_ON",
    "shape_keys": "SHAPEKEY_DATA",
    "materials": "MATERIAL",
    "substance_designer_baker": "RENDER_STILL",
    "colors": "GROUP_VCOL",
    "uv": "GROUP_UVS",
    "mesh_utilities": "MESH_DATA",
    "quad_reconstruction": "MESH_GRID",
    "cad_reconstruction": "MOD_REMESH",
    "gn_library": "GEOMETRY_NODES",
    "workflow_presets": "PRESET",
    "project_specific_tools": "TOOL_SETTINGS",
    "kalibra_tools": "SHADING_BBOX",
    "babylon_export": "EXPORT",
}

# Result severity. Each status has its own shape, so meaning never rests on
# color alone; the text next to the icon always states the status as well.
STATUS_ICONS = {
    "ok": "CHECKMARK",
    "warning": "ERROR",
    "error": "CANCEL",
    "info": "INFO",
    "idle": "RADIOBUT_OFF",
    "running": "TIME",
    "cancelled": "PAUSE",
}


def category_icon(key: str) -> dict:
    """Keyword arguments for the icon of an LC Workflow category."""
    return {"icon": CATEGORY_ICONS.get(key, "NONE")}


def status_icon(status: str) -> dict:
    """Keyword arguments for a result status icon (see STATUS_ICONS)."""
    return {"icon": STATUS_ICONS.get(status, STATUS_ICONS["idle"])}


def draw_header_icon(layout, key: str) -> None:
    """Draw a category icon in a panel header (use from Panel.draw_header)."""
    layout.label(text="", **category_icon(key))
