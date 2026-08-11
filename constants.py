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

ACTION_PARAMETER_NAMES = frozenset(
    {
        "axis_value",
        "bool_value",
        "bool_value_2",
        "bool_value_3",
        "color_blend",
        "color_domain",
        "color_mask",
        "color_type",
        "color_value",
        "filepath_value",
        "float_value",
        "float_value_2",
        "int_value",
        "int_value_2",
        "list_value",
        "space_value",
        "text_value",
        "text_value_2",
        "text_value_3",
    }
)


def _validate_action_definitions(definitions: Iterable[ActionDefinition]) -> None:
    seen_action_ids: set[str] = set()
    for definition in definitions:
        if definition.action_id in seen_action_ids:
            raise ValueError(f"Duplicate workflow action id: {definition.action_id}")
        seen_action_ids.add(definition.action_id)

        unknown_params = set(definition.params) - ACTION_PARAMETER_NAMES
        if unknown_params:
            params = ", ".join(sorted(unknown_params))
            raise ValueError(f"Unknown parameter(s) for workflow action {definition.action_id}: {params}")


_validate_action_definitions(ACTION_DEFINITIONS)


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

SDB_SELECTION_MODE_ITEMS = (
    ("ALL_EXCEPT_EXCLUDED", "All Materials Except Excluded", "Bake all material groups except those matching the excluded pattern"),
    ("MATERIALS_TOGETHER", "Materials Together", "Bake all meshes and group them by material across all objects"),
    ("OBJECTS_TOGETHER", "Objects Together", "Bake all meshes and group them by Blender object, including all mesh/material parts"),
)

SDB_AA_ITEMS = (
    ("none", "None", "Do not use supersampling"),
    ("2x2", "2x2", "Use 2x2 supersampling"),
    ("4x4", "4x4", "Use 4x4 supersampling"),
    ("8x8", "8x8", "Use 8x8 supersampling"),
)

SDB_SIZE_ITEMS = (
    ("128", "128", "Bake at 128 pixels"),
    ("256", "256", "Bake at 256 pixels"),
    ("512", "512", "Bake at 512 pixels"),
    ("1024", "1024", "Bake at 1024 pixels"),
    ("2048", "2048", "Bake at 2048 pixels"),
    ("4096", "4096", "Bake at 4096 pixels"),
    ("8192", "8192", "Bake at 8192 pixels"),
)

SDB_FORMAT_ITEMS = (
    ("png", "png", "Portable Network Graphics"),
    ("tga", "tga", "Truevision TGA"),
    ("bmp", "bmp", "Windows Bitmap"),
    ("tif", "tif", "Tagged Image File Format"),
    ("jpg", "jpg", "JPEG"),
    ("exr", "exr", "OpenEXR"),
)

SDB_HIT_STRATEGY_ITEMS = (
    ("inward", "Inward cast", "Suited to capture floater geometry"),
    ("closest_from_source", "Closest from source", "Select the closest low poly point"),
)

SDB_MATCH_MODE_ITEMS = (
    ("match_all", "Always", "Use any matching high poly mesh"),
    ("match_mesh_name", "By Mesh Name", "Only use matching high poly meshes with the same name"),
)

SDB_DISTRIBUTION_ITEMS = (
    ("cosine", "Cosine", "Use cosine-weighted ray distribution"),
    ("uniform", "Uniform", "Use uniform ray distribution"),
)

SDB_ATTENUATION_ITEMS = (
    ("none", "None", "Do not attenuate shadowing by distance"),
    ("smooth", "Smooth", "Apply smooth attenuation by distance"),
    ("linear", "Linear", "Apply linear attenuation by distance"),
)

SDB_CULLING_MODE_ITEMS = (
    ("never", "Never", "Do not ignore backfacing triangles"),
    ("always", "Always", "Always ignore backfacing triangles"),
    ("match_mesh_name", "By Suffix", "Ignore backfaces only for meshes with the dedicated suffix"),
)

SDB_NORMAL_MAP_SPACE_ITEMS = (
    ("tangent_space", "Tangent space", "Interpret the normal map in tangent space"),
    ("world_space", "World space", "Interpret the normal map in world space"),
)

SDB_NORMAL_MAP_ORIENTATION_ITEMS = (
    ("directx", "DirectX", "Use DirectX normal orientation"),
    ("opengl", "OpenGL", "Use OpenGL normal orientation"),
)

SDB_OUTPUT_TEXTURE_SPACE_ITEMS = (
    ("tangent_space", "Tangent space", "Bake tangent-space normal vectors"),
    ("world_space", "World space", "Bake world-space normal vectors"),
)

SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS = (
    ("directx", "DirectX", "Use DirectX normal orientation"),
    ("opengl", "OpenGL", "Use OpenGL normal orientation"),
)

SDB_HEIGHT_NORMALIZATION_ITEMS = (
    ("low_poly_distance", "Relative to low mesh (per UV tile)", "Normalize height from the low-poly mesh range per UV tile"),
    ("ray_distance", "Relative to ray distance", "Normalize height using the projection ray distance"),
    ("min_max", "Relative to min/max", "Normalize height using explicit min/max values"),
    ("manual", "Manual", "Use the scaling divisor manually"),
)

SDB_THICKNESS_NORMALIZATION_ITEMS = (
    ("min_max", "Relative to min/max (per UV tile)", "Normalize thickness using the min/max range per UV tile"),
    ("ray_distance", "Relative to ray distance", "Normalize thickness using the ray distance"),
    ("none", "None", "Do not normalize thickness values"),
)

SDB_JOB_STATUS_ITEMS = (
    ("IDLE", "Idle", "No bake job is running"),
    ("VALID", "Validated", "Settings were validated successfully"),
    ("PREVIEW_READY", "Preview Ready", "Preview results are available"),
    ("RUNNING", "Running", "A bake job is running"),
    ("SUCCEEDED", "Succeeded", "The last bake job completed successfully"),
    ("FAILED", "Failed", "The last bake job failed"),
)

SDB_EXPORT_SOURCE_ITEMS = (
    ("INTERNAL_FBX", "Internal FBX Export", "Use the addon fallback FBX export"),
    ("COLLECTION_EXPORTER", "Collection Exporter", "Use the first configured FBX exporter on the collection"),
)

PANEL_ORDER_DEFAULT = (
    "scene_info",
    "favorites",
    "shape_keys",
    "materials",
    "substance_designer_baker",
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
    "substance_designer_baker": "Bakers",
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
