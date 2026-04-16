from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


ADDON_PACKAGE = __package__
WINDOW_MANAGER_STATE_ID = "lcw_state"


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    label: str
    operator: str
    category: str
    params: tuple[str, ...] = ()
    allow_preset: bool = True
    allow_favorite: bool = True


ACTION_DEFINITIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition("shape_keys.create_default", "Ensure Default Width/Height Keys", "lcw.shape_key_create_default", "Shape Keys"),
    ActionDefinition("shape_keys.match_active", "Sync Active Shape Key Across Selection", "lcw.shape_key_match_active", "Shape Keys"),
    ActionDefinition("shape_keys.set_value", "Set Active Shape Key Value Across Selection", "lcw.shape_key_set_value", "Shape Keys", ("float_value",)),
    ActionDefinition("shape_keys.copy_names", "Copy Shape Key Names from Active Object", "lcw.shape_key_copy_names", "Shape Keys"),
    ActionDefinition("shape_keys.set_active_phrase", "Select Shape Key by Name Fragment", "lcw.shape_key_set_active_phrase", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.zero_all", "Zero All Shape Key Values", "lcw.shape_key_zero_all", "Shape Keys"),
    ActionDefinition("shape_keys.add_prefix", "Add Prefix to Non-Basis Shape Keys", "lcw.shape_key_add_prefix", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.replace_words", "Replace Text in Non-Basis Shape Key Names", "lcw.shape_key_replace_words", "Shape Keys", ("text_value", "text_value_2")),
    ActionDefinition("shape_keys.reset_all", "Reset Shape Keys", "lcw.shape_key_reset_all", "Shape Keys"),
    ActionDefinition("shape_keys.reset_by_phrases", "Reset Matching Shape Keys by Name", "lcw.shape_key_reset_by_phrases", "Shape Keys", ("list_value",)),
    ActionDefinition("shape_keys.deselect_phrase", "Deselect Objects Containing Shape Key Text", "lcw.shape_key_deselect_phrase", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.names_check", "Create Analysis Collections from Shape Key Names", "lcw.shape_key_names_check", "Shape Keys"),
    ActionDefinition(
        "shape_keys.preview_partial",
        "Preview Shape Keys by Name Fragment",
        "lcw.shape_key_animate_partial",
        "Shape Keys",
        ("list_value", "int_value", "int_value_2", "float_value", "float_value_2"),
        False,
        True,
    ),
    ActionDefinition("materials.assign_object", "Assign Material to Selected Objects", "lcw.material_assign_object", "Materials", ("text_value",)),
    ActionDefinition("materials.link_slots_data", "Link Slots to Data", "lcw.material_link_slots_data", "Materials"),
    ActionDefinition("materials.link_slots_object", "Link Slots to Object", "lcw.material_link_slots_object", "Materials"),
    ActionDefinition("materials.toggle_link", "Toggle Slot Link", "lcw.material_toggle_link", "Materials"),
    ActionDefinition("materials.random_active_color", "Randomize Active Material Color", "lcw.material_random_active_color", "Materials"),
    ActionDefinition("materials.remove_unused_slots", "Remove Unused Material Slots", "lcw.material_remove_unused_slots", "Materials"),
    ActionDefinition("materials.assign_faces", "Assign Material to Selected Faces", "lcw.material_assign_selected_faces", "Materials", ("text_value",)),
    ActionDefinition("colors.ensure_attribute", "Initialize Color Attribute", "lcw.color_attribute_initialize", "Colors", ("text_value", "color_domain", "color_type", "bool_value", "color_value")),
    ActionDefinition("colors.apply", "Apply Vertex Colors", "lcw.color_attribute_apply", "Colors", ("color_value", "color_mask", "color_blend", "text_value")),
    ActionDefinition("uv.set_active_uv1", "Set UV1 Active", "lcw.uv_set_active_1", "UV"),
    ActionDefinition("uv.set_active_uv2", "Set UV2 Active", "lcw.uv_set_active_2", "UV"),
    ActionDefinition("uv.set_active_uv3", "Set UV3 Active", "lcw.uv_set_active_3", "UV"),
    ActionDefinition("uv.add_uv1", "Add UV1 Channel", "lcw.uv_add_uv1", "UV", ("text_value",)),
    ActionDefinition("uv.add_uv2", "Add UV2 Channel", "lcw.uv_add_uv2", "UV", ("text_value",)),
    ActionDefinition("uv.add_uv3", "Add UV3 Channel", "lcw.uv_add_uv3", "UV", ("text_value",)),
    ActionDefinition("uv.rename_uv1", "Rename UV1", "lcw.uv_rename_uv1", "UV", ("text_value",)),
    ActionDefinition("uv.rename_uv2", "Rename UV2", "lcw.uv_rename_uv2", "UV", ("text_value",)),
    ActionDefinition("uv.rename_uv3", "Rename UV3", "lcw.uv_rename_uv3", "UV", ("text_value",)),
    ActionDefinition("mesh.set_data_names", "Set Mesh Data Names", "lcw.mesh_set_data_names", "Object and Mesh Utilities"),
    ActionDefinition("mesh.clear_custom_normals", "Clear Custom Normals", "lcw.mesh_clear_custom_normals", "Object and Mesh Utilities"),
    ActionDefinition("mesh.reveal_edit", "Reveal Mesh in Edit Mode", "lcw.mesh_reveal_in_edit_mode", "Object and Mesh Utilities"),
    ActionDefinition(
        "mesh.offset_y",
        "Progressive Cursor Offset",
        "lcw.mesh_progressive_offset_y",
        "Object and Mesh Utilities",
        ("float_value", "bool_value", "bool_value_2", "bool_value_3"),
    ),
    ActionDefinition("mesh.rename_suffix", "Rename Dot Suffix to Underscore", "lcw.object_rename_dot_suffix", "Object and Mesh Utilities", ("int_value",)),
    ActionDefinition("kalibra.export_selection_csv", "Export Selection Overview to CSV", "lcw.kalibra_export_selection_csv", "Kalibra Tools", ("filepath_value",)),
    ActionDefinition("kalibra.create_bbox", "Create Combined Bounding Box", "lcw.kalibra_create_combined_bbox", "Kalibra Tools", ("text_value", "filepath_value")),
    ActionDefinition("kalibra.create_glass_control", "Create Glass Control Object", "lcw.kalibra_create_glass_control", "Kalibra Tools", ("text_value", "text_value_2", "float_value")),
    ActionDefinition(
        "kalibra.scale_loops_xz",
        "Shrink Edge Loops by Distance",
        "lcw.kalibra_scale_loops_xz",
        "Kalibra Tools",
        ("float_value", "space_value", "bool_value", "bool_value_2", "bool_value_3"),
    ),
    ActionDefinition("kalibra.scale_loops_x", "Scale Edge Loops in X", "lcw.kalibra_scale_loops_x", "Kalibra Tools", ("float_value",)),
    ActionDefinition("kalibra.space_vertices_axis", "Space Vertices with Axis Falloff", "lcw.kalibra_space_vertices_axis", "Kalibra Tools", ("axis_value", "float_value")),
)

ACTION_ITEMS = tuple(
    (definition.action_id, f"{definition.category}: {definition.label}", "")
    for definition in ACTION_DEFINITIONS
    if definition.allow_preset
)

ACTION_MAP = {definition.action_id: definition for definition in ACTION_DEFINITIONS}

COLOR_DOMAIN_ITEMS = (
    ("CORNER", "Face Corner", "Store colors per face corner"),
    ("POINT", "Point", "Store colors per vertex"),
)

COLOR_TYPE_ITEMS = (
    ("BYTE_COLOR", "Byte Color", "Use byte precision color storage"),
    ("FLOAT_COLOR", "Float Color", "Use float precision color storage"),
)

COLOR_MASK_ITEMS = (
    ("FACE", "Selected Faces", "Affect selected faces only"),
    ("VERTEX", "Selected Vertices", "Affect faces or points with selected vertices"),
)

COLOR_BLEND_ITEMS = (
    ("SET", "Set", "Set the color directly"),
    ("ADD", "Add", "Add the color values"),
    ("MULTIPLY", "Multiply", "Multiply the existing colors"),
    ("OVERLAY", "Overlay", "Use a simple overlay style blend"),
)

AXIS_ITEMS = (
    ("X", "X", "Sort by X axis"),
    ("Y", "Y", "Sort by Y axis"),
    ("Z", "Z", "Sort by Z axis"),
    ("-X", "-X", "Sort by negative X axis"),
    ("-Y", "-Y", "Sort by negative Y axis"),
    ("-Z", "-Z", "Sort by negative Z axis"),
)

SPACE_MODE_ITEMS = (
    ("GLOBAL", "Global", "Use world-space axes"),
    ("LOCAL", "Local", "Use the active object's local axes"),
)

PANEL_ORDER_DEFAULT = (
    "scene_info",
    "favorites",
    "shape_keys",
    "materials",
    "colors",
    "uv",
    "mesh_utilities",
    "workflow_presets",
    "kalibra_tools",
)

PANEL_LABELS = {
    "scene_info": "Scene Info",
    "favorites": "Favorites",
    "shape_keys": "Shape Keys",
    "materials": "Materials",
    "colors": "Colors",
    "uv": "UV",
    "mesh_utilities": "Object and Mesh Utilities",
    "workflow_presets": "Workflow Presets",
    "kalibra_tools": "Kalibra Tools",
}


def normalize_panel_order(raw_value: str | Iterable[str] | None) -> tuple[str, ...]:
    if raw_value is None:
        ordered_keys: list[str] = []
    elif isinstance(raw_value, str):
        ordered_keys = [part.strip() for part in raw_value.split(",") if part.strip()]
    else:
        ordered_keys = [part for part in raw_value if part]

    filtered = [key for key in ordered_keys if key in PANEL_LABELS]
    for key in PANEL_ORDER_DEFAULT:
        if key not in filtered:
            filtered.append(key)
    return tuple(filtered)


def iter_actions_for_category(category: str) -> Iterable[ActionDefinition]:
    return tuple(definition for definition in ACTION_DEFINITIONS if definition.category == category)
