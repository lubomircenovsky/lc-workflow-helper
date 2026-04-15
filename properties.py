from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty

from .constants import ACTION_ITEMS, AXIS_ITEMS, COLOR_BLEND_ITEMS, COLOR_DOMAIN_ITEMS, COLOR_MASK_ITEMS, COLOR_TYPE_ITEMS, PANEL_ORDER_DEFAULT, SPACE_MODE_ITEMS, WINDOW_MANAGER_STATE_ID


class LCW_PG_WorkflowActionItem(bpy.types.PropertyGroup):
    action_id: EnumProperty(name="Action", items=ACTION_ITEMS)
    label_override: StringProperty(name="Label Override", default="")
    text_value: StringProperty(name="Text", default="")
    text_value_2: StringProperty(name="Text 2", default="")
    text_value_3: StringProperty(name="Text 3", default="")
    list_value: StringProperty(name="List", default="")
    float_value: FloatProperty(name="Float", default=0.0)
    float_value_2: FloatProperty(name="Float 2", default=1.0)
    int_value: IntProperty(name="Integer", default=1)
    int_value_2: IntProperty(name="Integer 2", default=30)
    bool_value: BoolProperty(name="Boolean", default=True)
    bool_value_2: BoolProperty(name="Boolean 2", default=False)
    bool_value_3: BoolProperty(name="Boolean 3", default=False)
    color_domain: EnumProperty(name="Color Domain", items=COLOR_DOMAIN_ITEMS, default="CORNER")
    color_type: EnumProperty(name="Color Type", items=COLOR_TYPE_ITEMS, default="BYTE_COLOR")
    color_mask: EnumProperty(name="Color Mask", items=COLOR_MASK_ITEMS, default="FACE")
    color_blend: EnumProperty(name="Color Blend", items=COLOR_BLEND_ITEMS, default="SET")
    axis_value: EnumProperty(name="Axis", items=AXIS_ITEMS, default="-X")
    space_value: EnumProperty(name="Space", items=SPACE_MODE_ITEMS, default="GLOBAL")
    filepath_value: StringProperty(name="File Path", subtype="FILE_PATH", default="")
    color_value: FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )


class LCW_PG_WorkflowPreset(bpy.types.PropertyGroup):
    name: StringProperty(name="Preset Name", default="New Preset")
    actions: CollectionProperty(type=LCW_PG_WorkflowActionItem)
    active_action_index: IntProperty(name="Active Action", default=0)


class LCW_PG_FavoriteAction(bpy.types.PropertyGroup):
    action_id: StringProperty(name="Action ID", default="")


class LCW_PG_SceneState(bpy.types.PropertyGroup):
    material_quick_name_1: StringProperty(name="Quick Name 1", default="")
    material_quick_name_2: StringProperty(name="Quick Name 2", default="")
    material_quick_name_3: StringProperty(name="Quick Name 3", default="")
    panel_order: StringProperty(name="Main Category Order", default=",".join(PANEL_ORDER_DEFAULT))
    favorite_actions: CollectionProperty(type=LCW_PG_FavoriteAction)


class LCW_PG_WindowState(bpy.types.PropertyGroup):
    material_name: StringProperty(name="Material", default="cavity_bake_v2")
    face_material_name: StringProperty(name="Face Material", default="00_Config_wood_int")
    color_attribute_name: StringProperty(name="Color Attribute", default="Color")
    color_attribute_domain: EnumProperty(name="Color Domain", items=COLOR_DOMAIN_ITEMS, default="CORNER")
    color_attribute_type: EnumProperty(name="Color Type", items=COLOR_TYPE_ITEMS, default="BYTE_COLOR")
    replace_color_attribute: BoolProperty(name="Replace Existing", default=False)
    color_initialize_value: FloatVectorProperty(
        name="Initialize Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )
    color_mask_type: EnumProperty(name="Mask Type", items=COLOR_MASK_ITEMS, default="FACE")
    color_blend_mode: EnumProperty(name="Blend Mode", items=COLOR_BLEND_ITEMS, default="SET")
    color_value: FloatVectorProperty(
        name="Color",
        subtype="COLOR",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )
    uv_deselect_if_missing: BoolProperty(name="Deselect if Missing", default=True)
    uv_add_channel_target: EnumProperty(
        name="Add Channel",
        items=(
            ("1", "UV1", "Create or prepare UV1"),
            ("2", "UV2", "Create or prepare UV2"),
            ("3", "UV3", "Create or prepare UV3"),
        ),
        default="2",
    )
    uv_add_channel_name: StringProperty(name="New UV Name", default="Lightmap")
    uv_remove_channel_target: EnumProperty(
        name="Remove Channel",
        items=(
            ("1", "UV1", "Remove UV1"),
            ("2", "UV2", "Remove UV2"),
            ("3", "UV3", "Remove UV3"),
            ("4", "UV4", "Remove UV4"),
            ("5", "UV5", "Remove UV5"),
        ),
        default="2",
    )
    uv_rename_uv1: StringProperty(name="UV1 Name", default="UVMap")
    uv_rename_uv2: StringProperty(name="UV2 Name", default="Lightmap")
    uv_rename_uv3: StringProperty(name="UV3 Name", default="UV3")
    shape_key_select_fragment: StringProperty(
        name="Name Fragment",
        description="Text used to find the first matching shape key on each selected object",
        default="",
    )
    shape_key_deselect_fragment: StringProperty(
        name="Name Fragment",
        description="Text used to find scene objects that should be deselected by shape key name",
        default="",
    )
    shape_key_prefix: StringProperty(
        name="Prefix",
        description="Text added to the start of each non-Basis shape key name",
        default="",
    )
    shape_key_search: StringProperty(
        name="Search Text",
        description="Text to replace in non-Basis shape key names",
        default="",
    )
    shape_key_replace: StringProperty(
        name="Replace With",
        description="Replacement text for matching shape key names",
        default="",
    )
    shape_key_phrases: StringProperty(
        name="Name Fragments",
        description="Comma-separated fragments used to find shape keys to reset",
        default="Width,Height",
    )
    shape_key_value: FloatProperty(
        name="Shape Key Value",
        description="Value copied from the active shape key to matching selected objects",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    shape_key_animation_names: StringProperty(
        name="Name Fragments",
        description="Comma-separated fragments used to find shape keys for the temporary preview",
        default="width,height",
    )
    shape_key_animation_start: IntProperty(
        name="Start Frame",
        description="First frame used for the temporary shape key preview",
        default=1,
        min=0,
    )
    shape_key_animation_end: IntProperty(
        name="End Frame",
        description="Last frame used for the temporary shape key preview",
        default=30,
        min=1,
    )
    shape_key_animation_min: FloatProperty(
        name="Min Value",
        description="Shape key value used on the first frame",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    shape_key_animation_max: FloatProperty(
        name="Max Value",
        description="Shape key value used on the last frame",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    shape_section_selection_open: BoolProperty(name="Selection Section", default=True)
    shape_section_naming_open: BoolProperty(name="Naming Section", default=False)
    shape_section_reset_open: BoolProperty(name="Reset Section", default=False)
    shape_section_animation_open: BoolProperty(name="Animation Section", default=False)
    shape_section_advanced_open: BoolProperty(name="Advanced Section", default=False)
    shape_tool_select_by_name_open: BoolProperty(name="Select Shape Key by Name", default=False)
    shape_tool_set_value_open: BoolProperty(name="Set Active Shape Key Value", default=False)
    shape_tool_add_prefix_open: BoolProperty(name="Add Prefix", default=False)
    shape_tool_replace_text_open: BoolProperty(name="Replace Text", default=False)
    shape_tool_reset_matching_open: BoolProperty(name="Reset Matching Shape Keys", default=False)
    shape_tool_deselect_text_open: BoolProperty(name="Deselect by Shape Key Text", default=False)
    shape_tool_animation_open: BoolProperty(name="Preview Shape Keys", default=False)
    root_category_order_open: BoolProperty(name="Main Category Order", default=False)
    material_tool_assign_faces_open: BoolProperty(name="Assign Material to Faces", default=False)
    color_tool_initialize_open: BoolProperty(name="Initialize Color Attribute", default=True)
    color_tool_apply_open: BoolProperty(name="Apply Vertex Colors", default=False)
    uv_tool_add_channel_open: BoolProperty(name="Add UV Channel", default=False)
    uv_tool_remove_channel_open: BoolProperty(name="Remove UV Channel", default=False)
    uv_tool_rename_channels_open: BoolProperty(name="Rename UV Channels", default=False)
    mesh_section_data_open: BoolProperty(name="Mesh Data Section", default=True)
    mesh_section_object_open: BoolProperty(name="Object Utilities Section", default=True)
    mesh_tool_offset_y_open: BoolProperty(name="Progressive Cursor Offset", default=False)
    mesh_tool_rename_suffix_open: BoolProperty(name="Rename Dot Suffix", default=False)
    mesh_offset_axis_x: BoolProperty(name="X", default=False)
    mesh_offset_axis_y: BoolProperty(name="Y", default=True)
    mesh_offset_axis_z: BoolProperty(name="Z", default=False)
    object_offset_y: FloatProperty(name="Offset Step", default=1.0)
    rename_suffix_width: IntProperty(name="Suffix Digits", default=2, min=1, max=6)
    kalibra_export_csv: StringProperty(name="CSV Path", subtype="FILE_PATH", default="")
    kalibra_bbox_name: StringProperty(name="Bounding Box Name", default="Combined_BBox")
    kalibra_bbox_csv: StringProperty(name="Bounding CSV", subtype="FILE_PATH", default="")
    kalibra_glass_search: StringProperty(name="Search", default="_Wood")
    kalibra_glass_replace: StringProperty(name="Replace", default="GGB_position")
    kalibra_angle_threshold: FloatProperty(name="Angle Threshold", default=150.0, min=0.0, max=180.0)
    kalibra_scale_amount: FloatProperty(name="Scale Amount", default=0.002)
    kalibra_scale_space: EnumProperty(name="Space", items=SPACE_MODE_ITEMS, default="GLOBAL")
    kalibra_scale_axis_x: BoolProperty(name="X", default=True)
    kalibra_scale_axis_y: BoolProperty(name="Y", default=False)
    kalibra_scale_axis_z: BoolProperty(name="Z", default=True)
    kalibra_axis: EnumProperty(name="Axis", items=AXIS_ITEMS, default="-X")
    kalibra_falloff_power: FloatProperty(name="Falloff Power", default=2.4, min=0.01)
    kalibra_tool_export_open: BoolProperty(name="Kalibra CSV Export", default=False)
    kalibra_tool_bbox_open: BoolProperty(name="Kalibra Bounding Box", default=False)
    kalibra_tool_glass_open: BoolProperty(name="Kalibra Glass Control", default=False)
    kalibra_section_loops_open: BoolProperty(name="Kalibra Loops Section", default=True)
    kalibra_tool_scale_loops_open: BoolProperty(name="Kalibra Scale Loops", default=False)
    kalibra_tool_space_vertices_open: BoolProperty(name="Kalibra Space Vertices", default=False)


CLASSES = (
    LCW_PG_WorkflowActionItem,
    LCW_PG_WorkflowPreset,
    LCW_PG_FavoriteAction,
    LCW_PG_SceneState,
    LCW_PG_WindowState,
)


def register_properties() -> None:
    bpy.types.WindowManager.lcw_state = PointerProperty(type=LCW_PG_WindowState)
    bpy.types.Scene.lcw_scene_state = PointerProperty(type=LCW_PG_SceneState)


def unregister_properties() -> None:
    if hasattr(bpy.types.Scene, "lcw_scene_state"):
        delattr(bpy.types.Scene, "lcw_scene_state")
    if hasattr(bpy.types.WindowManager, WINDOW_MANAGER_STATE_ID):
        delattr(bpy.types.WindowManager, WINDOW_MANAGER_STATE_ID)
