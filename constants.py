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


ACTION_DEFINITIONS: tuple[ActionDefinition, ...] = (
    ActionDefinition("shape_keys.create_default", "Create Default Shape Keys", "lcw.shape_key_create_default", "Shape Keys"),
    ActionDefinition("shape_keys.match_active", "Match Active Shape Key", "lcw.shape_key_match_active", "Shape Keys"),
    ActionDefinition("shape_keys.set_value", "Set Active Shape Key Value", "lcw.shape_key_set_value", "Shape Keys", ("float_value",)),
    ActionDefinition("shape_keys.copy_names", "Copy Shape Key Names from Active", "lcw.shape_key_copy_names", "Shape Keys"),
    ActionDefinition("shape_keys.set_active_phrase", "Set Active Shape Key by Phrase", "lcw.shape_key_set_active_phrase", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.zero_all", "Set All Shape Keys to Zero", "lcw.shape_key_zero_all", "Shape Keys"),
    ActionDefinition("shape_keys.add_prefix", "Add Prefix to Shape Keys", "lcw.shape_key_add_prefix", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.replace_words", "Replace in Shape Key Names", "lcw.shape_key_replace_words", "Shape Keys", ("text_value", "text_value_2")),
    ActionDefinition("shape_keys.reset_all", "Reset All Shape Keys", "lcw.shape_key_reset_all", "Shape Keys"),
    ActionDefinition("shape_keys.reset_by_phrases", "Reset Shape Keys by Phrases", "lcw.shape_key_reset_by_phrases", "Shape Keys", ("list_value",)),
    ActionDefinition("shape_keys.deselect_phrase", "Deselect by Shape Key Phrase", "lcw.shape_key_deselect_phrase", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.names_check", "Create Shape Key Name Collections", "lcw.shape_key_names_check", "Shape Keys"),
    ActionDefinition("shape_keys.create_auto_prefix", "Create Auto Prefix Shape Key", "lcw.shape_key_create_auto_prefix", "Shape Keys", ("text_value",)),
    ActionDefinition("shape_keys.animate_partial", "Animate Shape Keys by Partial Names", "lcw.shape_key_animate_partial", "Shape Keys", ("list_value", "int_value", "int_value_2", "float_value", "float_value_2")),
    ActionDefinition("materials.assign_object", "Assign Material to Selected Objects", "lcw.material_assign_object", "Materials", ("text_value",)),
    ActionDefinition("materials.toggle_link", "Toggle Material Link", "lcw.material_toggle_link", "Materials"),
    ActionDefinition("materials.remove_unused_slots", "Remove Unused Material Slots", "lcw.material_remove_unused_slots", "Materials"),
    ActionDefinition("materials.assign_faces", "Assign Material to Selected Faces", "lcw.material_assign_selected_faces", "Materials", ("text_value",)),
    ActionDefinition("colors.ensure_attribute", "Initialize Color Attribute", "lcw.color_attribute_initialize", "Colors", ("text_value", "color_domain", "color_type", "bool_value")),
    ActionDefinition("colors.apply", "Apply Vertex Colors", "lcw.color_attribute_apply", "Colors", ("color_value", "color_mask", "color_blend", "text_value")),
    ActionDefinition("uv.ensure_second", "Ensure Second UV Channel", "lcw.uv_ensure_second", "UV", ("text_value",)),
    ActionDefinition("uv.set_active", "Set Active UV Channel", "lcw.uv_set_active_channel", "UV", ("int_value", "bool_value")),
    ActionDefinition("uv.rename_channel", "Rename UV Channel", "lcw.uv_rename_channel", "UV", ("int_value", "text_value", "bool_value")),
    ActionDefinition("mesh.set_data_names", "Set Mesh Data Names", "lcw.mesh_set_data_names", "Mesh Utilities"),
    ActionDefinition("mesh.clear_custom_normals", "Clear Custom Normals", "lcw.mesh_clear_custom_normals", "Mesh Utilities"),
    ActionDefinition("mesh.reveal_edit", "Reveal Mesh in Edit Mode", "lcw.mesh_reveal_in_edit_mode", "Mesh Utilities"),
    ActionDefinition("mesh.offset_y", "Progressive Y Offset", "lcw.mesh_progressive_offset_y", "Mesh Utilities", ("float_value",)),
    ActionDefinition("mesh.rename_suffix", "Rename Dot Suffix to Underscore", "lcw.object_rename_dot_suffix", "Mesh Utilities", ("int_value",)),
    ActionDefinition("kalibra.export_selection_csv", "Export Selection Overview to CSV", "lcw.kalibra_export_selection_csv", "Kalibra Tools", ("filepath_value",)),
    ActionDefinition("kalibra.create_bbox", "Create Combined Bounding Box", "lcw.kalibra_create_combined_bbox", "Kalibra Tools", ("text_value", "filepath_value")),
    ActionDefinition("kalibra.create_glass_control", "Create Glass Control Object", "lcw.kalibra_create_glass_control", "Kalibra Tools", ("text_value", "text_value_2", "float_value")),
    ActionDefinition("kalibra.scale_loops_xz", "Scale Edge Loops in X and Z", "lcw.kalibra_scale_loops_xz", "Kalibra Tools", ("float_value",)),
    ActionDefinition("kalibra.scale_loops_x", "Scale Edge Loops in X", "lcw.kalibra_scale_loops_x", "Kalibra Tools", ("float_value",)),
    ActionDefinition("kalibra.space_vertices_axis", "Space Vertices with Axis Falloff", "lcw.kalibra_space_vertices_axis", "Kalibra Tools", ("axis_value", "float_value")),
)

ACTION_ITEMS = tuple(
    (definition.action_id, f"{definition.category}: {definition.label}", "")
    for definition in ACTION_DEFINITIONS
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


def iter_actions_for_category(category: str) -> Iterable[ActionDefinition]:
    return tuple(definition for definition in ACTION_DEFINITIONS if definition.category == category)
