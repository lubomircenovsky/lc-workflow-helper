from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty

from .constants import (
    ACTION_ITEMS,
    AXIS_ITEMS,
    COLOR_BLEND_ITEMS,
    COLOR_DOMAIN_ITEMS,
    COLOR_MASK_ITEMS,
    COLOR_TYPE_ITEMS,
    PANEL_ORDER_DEFAULT,
    SDB_AA_ITEMS,
    SDB_ATTENUATION_ITEMS,
    SDB_CULLING_MODE_ITEMS,
    SDB_EXPORT_SOURCE_ITEMS,
    SDB_DISTRIBUTION_ITEMS,
    SDB_FORMAT_ITEMS,
    SDB_HIT_STRATEGY_ITEMS,
    SDB_JOB_STATUS_ITEMS,
    SDB_MATCH_MODE_ITEMS,
    SDB_NORMAL_MAP_ORIENTATION_ITEMS,
    SDB_NORMAL_MAP_SPACE_ITEMS,
    SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS,
    SDB_OUTPUT_TEXTURE_SPACE_ITEMS,
    SDB_SELECTION_MODE_ITEMS,
    SDB_SIZE_ITEMS,
    SDB_HEIGHT_NORMALIZATION_ITEMS,
    SDB_THICKNESS_NORMALIZATION_ITEMS,
    SPACE_MODE_ITEMS,
    WINDOW_MANAGER_STATE_ID,
)


def _sync_baker_output_size(self, _context: bpy.types.Context | None = None) -> None:
    if getattr(self, "output_size_locked", False):
        self.output_size_y = self.output_size_x


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
        subtype="COLOR_GAMMA",
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


class LCW_PG_BakerProfile(bpy.types.PropertyGroup):
    profile_id: StringProperty(name="Profile ID", default="")
    name: StringProperty(
        name="Profile Name",
        description="Name shown in the Baker Profiles list",
        default="Baker Profile",
    )
    baker_enable_ambient_occlusion: BoolProperty(
        name="Ambient Occlusion",
        description="Include Ambient Occlusion when this baker recipe is applied",
        default=True,
    )
    baker_enable_bent_normal: BoolProperty(
        name="Bent Normal",
        description="Include Bent Normal when this baker recipe is applied",
        default=False,
    )
    baker_enable_curvature: BoolProperty(
        name="Curvature",
        description="Include Curvature when this baker recipe is applied",
        default=False,
    )
    baker_enable_height: BoolProperty(
        name="Height",
        description="Include Height when this baker recipe is applied",
        default=False,
    )
    baker_enable_normal: BoolProperty(
        name="Normal",
        description="Include Normal when this baker recipe is applied",
        default=False,
    )
    baker_enable_thickness: BoolProperty(
        name="Thickness",
        description="Include Thickness when this baker recipe is applied",
        default=False,
    )
    selection_mode: EnumProperty(
        name="Selection Mode",
        description="Choose how meshes are grouped into bake targets",
        items=SDB_SELECTION_MODE_ITEMS,
        default="ALL_EXCEPT_EXCLUDED",
    )
    excluded_material_pattern: StringProperty(
        name="Excluded Material Pattern",
        description="Skip materials whose name contains this text when using All Materials Except Excluded",
        default="occluder",
    )
    material_name_contains: StringProperty(
        name="Material Name Contains",
        description="Legacy profile field kept for compatibility with older saved profiles",
        default="bake",
    )
    excluded_material_exact: StringProperty(
        name="Excluded Material",
        description="Legacy profile field kept for compatibility with older saved profiles",
        default="_0_occluder",
    )
    output_size_x: EnumProperty(
        name="Width",
        description="Output width for baked textures",
        items=SDB_SIZE_ITEMS,
        default="2048",
        update=_sync_baker_output_size,
    )
    output_size_y: EnumProperty(
        name="Height",
        description="Output height for baked textures",
        items=SDB_SIZE_ITEMS,
        default="2048",
    )
    output_size_locked: BoolProperty(
        name="Lock Output Size",
        description="Keep width and height matched for square outputs",
        default=True,
        update=_sync_baker_output_size,
    )
    output_format: EnumProperty(
        name="Format",
        description="Image format used for baked outputs",
        items=SDB_FORMAT_ITEMS,
        default="png",
    )
    uv_set: IntProperty(
        name="UV Set",
        description="UV channel index used for baking",
        default=0,
        min=0,
    )
    padding_radius: IntProperty(
        name="Dilation Width (px)",
        description="Extend baked pixels beyond UV borders to reduce seams",
        default=2,
        min=0,
    )
    enable_mip_diffusion: BoolProperty(
        name="Apply Diffusion",
        description="Diffuse edge colors to improve mipmap stability",
        default=True,
    )
    anti_aliasing: EnumProperty(
        name="Anti Alias",
        description="Supersampling mode used during baking",
        items=SDB_AA_ITEMS,
        default="none",
    )
    average_normals: BoolProperty(
        name="Average Normals",
        description="Smooth shading normals before the bake when supported",
        default=True,
    )
    use_lowdef_as_highdef: BoolProperty(
        name="Use Low Definition As High Definition",
        description="Reuse the low definition meshes as the high definition source in the generated bake plan",
        default=True,
    )
    projection_max_height: FloatProperty(
        name="Max Frontal Distance",
        description="Maximum projection distance in front of the low definition surface",
        default=0.01,
        min=0.0,
    )
    projection_max_depth: FloatProperty(
        name="Max Rear Distance",
        description="Maximum projection distance behind the low definition surface",
        default=0.01,
        min=0.0,
    )
    projection_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale projection distances relative to the mesh bounding box",
        default=True,
    )
    projection_cull_backfaces: BoolProperty(
        name="Ignore Backface",
        description="Ignore backfacing geometry during projection rays",
        default=True,
    )
    projection_match_mode: EnumProperty(
        name="Match",
        description="How low and high meshes are matched for projection",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    projection_hit_strategy: EnumProperty(
        name="Hit Selection Strategy",
        description="Choose which projection hit is used when multiple surfaces are found",
        items=SDB_HIT_STRATEGY_ITEMS,
        default="inward",
    )
    skew_correction: BoolProperty(
        name="Use Skew Correction",
        description="Enable skew correction during projection",
        default=False,
    )
    skew_map_path: StringProperty(
        name="Skew Texture",
        description="Optional skew map texture used for projection correction",
        subtype="FILE_PATH",
        default="",
    )
    projection_skew_map_invert: BoolProperty(
        name="Invert Skew Correction",
        description="Invert the skew map when skew correction is enabled",
        default=False,
    )
    projection_offset_map_path: StringProperty(
        name="Offset Map",
        description="Optional offset map texture used during projection",
        subtype="FILE_PATH",
        default="",
    )
    secondary_sample_count: IntProperty(
        name="Secondary Rays",
        description="Number of AO rays shot from each texel",
        default=64,
        min=1,
        max=256,
    )
    secondary_min_distance: FloatProperty(
        name="Min Occluder Distance",
        description="Ignore AO hits closer than this distance",
        default=0.00001,
        min=0.0,
    )
    secondary_max_distance: FloatProperty(
        name="Max Occluder Distance",
        description="Ignore AO hits farther than this distance",
        default=1.0,
        min=0.0,
    )
    secondary_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale AO distance values relative to the mesh bounding box",
        default=True,
    )
    secondary_spread_angle: FloatProperty(
        name="Spread Angle",
        description="Angular spread of AO rays in degrees",
        default=180.0,
        min=0.0,
        max=180.0,
    )
    secondary_sample_distribution: EnumProperty(
        name="Distribution",
        description="Distribution pattern used for AO secondary rays",
        items=SDB_DISTRIBUTION_ITEMS,
        default="cosine",
    )
    culling_mode: EnumProperty(
        name="Ignore Backface",
        description="Control whether AO rays can hit backfaces",
        items=SDB_CULLING_MODE_ITEMS,
        default="never",
    )
    secondary_mesh_match_mode: EnumProperty(
        name="Self Occlusion",
        description="Choose which meshes are allowed to occlude each other",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    normal_map_path: StringProperty(
        name="Normal Map",
        description="Optional normal map used to guide AO shading",
        subtype="FILE_PATH",
        default="",
    )
    normal_map_space: EnumProperty(
        name="Map Type",
        description="Coordinate space used by the normal map",
        items=SDB_NORMAL_MAP_SPACE_ITEMS,
        default="tangent_space",
    )
    normal_map_orientation: EnumProperty(
        name="Normal Orientation",
        description="Normal map axis convention",
        items=SDB_NORMAL_MAP_ORIENTATION_ITEMS,
        default="directx",
    )
    attenuation: EnumProperty(
        name="Attenuation",
        description="Falloff model applied to ambient occlusion distance",
        items=SDB_ATTENUATION_ITEMS,
        default="linear",
    )
    enable_ground_plane: BoolProperty(
        name="Ground Plane",
        description="Add an infinite ground plane as an occluder",
        default=False,
    )
    ground_offset: FloatProperty(
        name="Ground Plane Offset",
        description="Offset of the ground plane from the object origin",
        default=0.0,
    )
    bent_secondary_sample_count: IntProperty(name="Bent Secondary Rays", default=64, min=1, max=256)
    bent_secondary_min_distance: FloatProperty(name="Bent Min Occluder Distance", default=0.00001, min=0.0)
    bent_secondary_max_distance: FloatProperty(name="Bent Max Occluder Distance", default=1.0, min=0.0)
    bent_secondary_normalized_distance: BoolProperty(name="Bent Relative To Bounding Box", default=True)
    bent_secondary_spread_angle: FloatProperty(name="Bent Spread Angle", default=180.0, min=0.0, max=180.0)
    bent_secondary_sample_distribution: EnumProperty(name="Bent Distribution", items=SDB_DISTRIBUTION_ITEMS, default="cosine")
    bent_culling_mode: EnumProperty(name="Bent Ignore Backface", items=SDB_CULLING_MODE_ITEMS, default="never")
    bent_secondary_mesh_match_mode: EnumProperty(name="Bent Self Occlusion", items=SDB_MATCH_MODE_ITEMS, default="match_all")
    bent_output_texture_space: EnumProperty(name="Bent Output Type", items=SDB_OUTPUT_TEXTURE_SPACE_ITEMS, default="tangent_space")
    bent_output_texture_orientation: EnumProperty(name="Bent Output Orientation", items=SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS, default="directx")
    curvature_secondary_sample_count: IntProperty(name="Curvature Secondary Rays", default=32, min=1, max=256)
    curvature_sampling_radius: FloatProperty(name="Curvature Sampling Radius", default=0.001, min=0.0)
    curvature_normalized_distance: BoolProperty(name="Curvature Relative To Bounding Box", default=True)
    curvature_mesh_match_mode: EnumProperty(name="Curvature Self Intersection", items=SDB_MATCH_MODE_ITEMS, default="match_all")
    curvature_normal_map_path: StringProperty(name="Curvature Normal Map", subtype="FILE_PATH", default="")
    curvature_normal_map_space: EnumProperty(name="Curvature Map Type", items=SDB_NORMAL_MAP_SPACE_ITEMS, default="tangent_space")
    curvature_normal_map_orientation: EnumProperty(name="Curvature Normal Orientation", items=SDB_NORMAL_MAP_ORIENTATION_ITEMS, default="directx")
    curvature_auto_minmax: BoolProperty(name="Curvature Auto Tonemapping", default=True)
    curvature_value_min: FloatProperty(name="Curvature Min", default=-1.0)
    curvature_value_max: FloatProperty(name="Curvature Max", default=1.0)
    height_normalization: EnumProperty(name="Height Normalization", items=SDB_HEIGHT_NORMALIZATION_ITEMS, default="low_poly_distance")
    height_divisor: FloatProperty(name="Height Scaling Divisor", default=1.0, min=0.0)
    normal_output_texture_space: EnumProperty(name="Normal Output Type", items=SDB_OUTPUT_TEXTURE_SPACE_ITEMS, default="tangent_space")
    normal_output_texture_orientation: EnumProperty(name="Normal Output Orientation", items=SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS, default="directx")
    thickness_secondary_sample_count: IntProperty(name="Thickness Secondary Rays", default=64, min=1, max=256)
    thickness_secondary_min_distance: FloatProperty(name="Thickness Min Occluder Distance", default=0.00001, min=0.0)
    thickness_secondary_max_distance: FloatProperty(name="Thickness Max Occluder Distance", default=0.1, min=0.0)
    thickness_secondary_normalized_distance: BoolProperty(name="Thickness Relative To Bounding Box", default=True)
    thickness_secondary_spread_angle: FloatProperty(name="Thickness Spread Angle", default=180.0, min=0.0, max=180.0)
    thickness_secondary_sample_distribution: EnumProperty(name="Thickness Distribution", items=SDB_DISTRIBUTION_ITEMS, default="cosine")
    thickness_secondary_mesh_match_mode: EnumProperty(name="Thickness Self Occlusion", items=SDB_MATCH_MODE_ITEMS, default="match_all")
    thickness_normalization: EnumProperty(name="Thickness Normalization", items=SDB_THICKNESS_NORMALIZATION_ITEMS, default="min_max")


class LCW_PG_SDBPreviewItem(bpy.types.PropertyGroup):
    label: StringProperty(name="Label", default="")
    detail: StringProperty(name="Detail", default="")
    item_kind: StringProperty(name="Kind", default="INFO")
    included: BoolProperty(name="Included", default=True)


class LCW_PG_SubstanceDesignerBakeState(bpy.types.PropertyGroup):
    target_collection: PointerProperty(
        name="Collection",
        description="Collection exported and inspected for bake targets",
        type=bpy.types.Collection,
    )
    profile_id: StringProperty(
        name="Profile",
        description="Stored baker profile linked to this .blend file",
        default="",
    )
    baker_enable_ambient_occlusion: BoolProperty(
        name="Ambient Occlusion",
        description="Enable Ambient Occlusion output for the next bake",
        default=True,
    )
    baker_enable_bent_normal: BoolProperty(
        name="Bent Normal",
        description="Enable Bent Normal output for the next bake",
        default=False,
    )
    baker_enable_curvature: BoolProperty(
        name="Curvature",
        description="Enable Curvature output for the next bake",
        default=False,
    )
    baker_enable_height: BoolProperty(
        name="Height",
        description="Enable Height output for the next bake",
        default=False,
    )
    baker_enable_normal: BoolProperty(
        name="Normal",
        description="Enable Normal output for the next bake",
        default=False,
    )
    baker_enable_thickness: BoolProperty(
        name="Thickness",
        description="Enable Thickness output for the next bake",
        default=False,
    )
    selection_mode: EnumProperty(
        name="Selection Mode",
        description="Choose how meshes are grouped into bake targets",
        items=SDB_SELECTION_MODE_ITEMS,
        default="ALL_EXCEPT_EXCLUDED",
    )
    excluded_material_pattern: StringProperty(
        name="Excluded Material Pattern",
        description="Skip materials whose name contains this text when using All Materials Except Excluded",
        default="occluder",
    )
    material_name_contains: StringProperty(
        name="Material Name Contains",
        description="Legacy scene field kept for compatibility with older saved files",
        default="bake",
    )
    excluded_material_exact: StringProperty(
        name="Excluded Material",
        description="Legacy scene field kept for compatibility with older saved files",
        default="_0_occluder",
    )
    output_root: StringProperty(
        name="Output Root",
        description="Folder where bake jobs write their output subdirectories",
        subtype="DIR_PATH",
        default="",
    )
    output_size_x: EnumProperty(
        name="Width",
        description="Output width for baked textures",
        items=SDB_SIZE_ITEMS,
        default="2048",
        update=_sync_baker_output_size,
    )
    output_size_y: EnumProperty(
        name="Height",
        description="Output height for baked textures",
        items=SDB_SIZE_ITEMS,
        default="2048",
    )
    output_size_locked: BoolProperty(
        name="Lock Output Size",
        description="Keep width and height matched for square outputs",
        default=True,
        update=_sync_baker_output_size,
    )
    output_format: EnumProperty(
        name="Format",
        description="Image format used for baked outputs",
        items=SDB_FORMAT_ITEMS,
        default="png",
    )
    uv_set: IntProperty(
        name="UV Set",
        description="UV channel index used for baking",
        default=0,
        min=0,
    )
    padding_radius: IntProperty(
        name="Dilation Width (px)",
        description="Extend baked pixels beyond UV borders to reduce seams",
        default=2,
        min=0,
    )
    enable_mip_diffusion: BoolProperty(
        name="Apply Diffusion",
        description="Diffuse edge colors to improve mipmap stability",
        default=True,
    )
    anti_aliasing: EnumProperty(
        name="Anti Alias",
        description="Supersampling mode used during baking",
        items=SDB_AA_ITEMS,
        default="none",
    )
    average_normals: BoolProperty(
        name="Average Normals",
        description="Smooth shading normals before the bake when supported",
        default=True,
    )
    use_lowdef_as_highdef: BoolProperty(
        name="Use Low Definition As High Definition",
        description="Reuse the low definition meshes as the high definition source in the generated bake plan",
        default=True,
    )
    high_scene_paths: StringProperty(
        name="High Poly Mesh Paths",
        description="Reserved list of high poly scene files for a future workflow phase",
        subtype="FILE_PATH",
        default="",
    )
    use_cage: BoolProperty(
        name="Use Cage",
        description="Reserved cage toggle for a future workflow phase",
        default=False,
    )
    cage_scene_path: StringProperty(
        name="Cage Mesh Path",
        description="Reserved cage mesh path for a future workflow phase",
        subtype="FILE_PATH",
        default="",
    )
    projection_max_height: FloatProperty(
        name="Max Frontal Distance",
        description="Maximum projection distance in front of the low definition surface",
        default=0.01,
        min=0.0,
    )
    projection_max_depth: FloatProperty(
        name="Max Rear Distance",
        description="Maximum projection distance behind the low definition surface",
        default=0.01,
        min=0.0,
    )
    projection_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale projection distances relative to the mesh bounding box",
        default=True,
    )
    projection_cull_backfaces: BoolProperty(
        name="Ignore Backface",
        description="Ignore backfacing geometry during projection rays",
        default=True,
    )
    projection_match_mode: EnumProperty(
        name="Match",
        description="How low and high meshes are matched for projection",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    projection_hit_strategy: EnumProperty(
        name="Hit Selection Strategy",
        description="Choose which projection hit is used when multiple surfaces are found",
        items=SDB_HIT_STRATEGY_ITEMS,
        default="inward",
    )
    skew_correction: BoolProperty(
        name="Use Skew Correction",
        description="Enable skew correction during projection",
        default=False,
    )
    skew_map_path: StringProperty(
        name="Skew Texture",
        description="Optional skew map texture used for projection correction",
        subtype="FILE_PATH",
        default="",
    )
    projection_skew_map_invert: BoolProperty(
        name="Invert Skew Correction",
        description="Invert the skew map when skew correction is enabled",
        default=False,
    )
    projection_offset_map_path: StringProperty(
        name="Offset Map",
        description="Optional offset map texture used during projection",
        subtype="FILE_PATH",
        default="",
    )
    secondary_sample_count: IntProperty(
        name="Secondary Rays",
        description="Number of AO rays shot from each texel",
        default=64,
        min=1,
        max=256,
    )
    secondary_min_distance: FloatProperty(
        name="Min Occluder Distance",
        description="Ignore AO hits closer than this distance",
        default=0.00001,
        min=0.0,
    )
    secondary_max_distance: FloatProperty(
        name="Max Occluder Distance",
        description="Ignore AO hits farther than this distance",
        default=1.0,
        min=0.0,
    )
    secondary_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale AO distance values relative to the mesh bounding box",
        default=True,
    )
    secondary_spread_angle: FloatProperty(
        name="Spread Angle",
        description="Angular spread of AO rays in degrees",
        default=180.0,
        min=0.0,
        max=180.0,
    )
    secondary_sample_distribution: EnumProperty(
        name="Distribution",
        description="Distribution pattern used for AO secondary rays",
        items=SDB_DISTRIBUTION_ITEMS,
        default="cosine",
    )
    culling_mode: EnumProperty(
        name="Ignore Backface",
        description="Control whether AO rays can hit backfaces",
        items=SDB_CULLING_MODE_ITEMS,
        default="never",
    )
    secondary_mesh_match_mode: EnumProperty(
        name="Self Occlusion",
        description="Choose which meshes are allowed to occlude each other",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    normal_map_path: StringProperty(
        name="Normal Map",
        description="Optional normal map used to guide AO shading",
        subtype="FILE_PATH",
        default="",
    )
    normal_map_space: EnumProperty(
        name="Map Type",
        description="Coordinate space used by the normal map",
        items=SDB_NORMAL_MAP_SPACE_ITEMS,
        default="tangent_space",
    )
    normal_map_orientation: EnumProperty(
        name="Normal Orientation",
        description="Normal map axis convention",
        items=SDB_NORMAL_MAP_ORIENTATION_ITEMS,
        default="directx",
    )
    attenuation: EnumProperty(
        name="Attenuation",
        description="Falloff model applied to ambient occlusion distance",
        items=SDB_ATTENUATION_ITEMS,
        default="linear",
    )
    enable_ground_plane: BoolProperty(
        name="Ground Plane",
        description="Add an infinite ground plane as an occluder",
        default=False,
    )
    ground_offset: FloatProperty(
        name="Ground Plane Offset",
        description="Offset of the ground plane from the object origin",
        default=0.0,
    )
    bent_secondary_sample_count: IntProperty(
        name="Secondary Rays",
        description="Number of rays used to estimate the bent normal direction",
        default=64,
        min=1,
        max=256,
    )
    bent_secondary_min_distance: FloatProperty(
        name="Min Occluder Distance",
        description="Ignore bent-normal occluders closer than this distance",
        default=0.00001,
        min=0.0,
    )
    bent_secondary_max_distance: FloatProperty(
        name="Max Occluder Distance",
        description="Ignore bent-normal occluders farther than this distance",
        default=1.0,
        min=0.0,
    )
    bent_secondary_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale bent-normal distances relative to the mesh bounding box",
        default=True,
    )
    bent_secondary_spread_angle: FloatProperty(
        name="Spread Angle",
        description="Angular spread of bent-normal rays in degrees",
        default=180.0,
        min=0.0,
        max=180.0,
    )
    bent_secondary_sample_distribution: EnumProperty(
        name="Distribution",
        description="Distribution pattern used for bent-normal rays",
        items=SDB_DISTRIBUTION_ITEMS,
        default="cosine",
    )
    bent_culling_mode: EnumProperty(
        name="Ignore Backface",
        description="Control whether bent-normal rays can hit backfaces",
        items=SDB_CULLING_MODE_ITEMS,
        default="never",
    )
    bent_secondary_mesh_match_mode: EnumProperty(
        name="Self Occlusion",
        description="Choose which meshes are allowed to occlude bent-normal rays",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    bent_output_texture_space: EnumProperty(
        name="Output Type",
        description="Coordinate space written by the bent-normal baker",
        items=SDB_OUTPUT_TEXTURE_SPACE_ITEMS,
        default="tangent_space",
    )
    bent_output_texture_orientation: EnumProperty(
        name="Output Orientation",
        description="Normal orientation convention written by the bent-normal baker",
        items=SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS,
        default="directx",
    )
    curvature_secondary_sample_count: IntProperty(
        name="Secondary Rays",
        description="Number of rays used by the curvature baker",
        default=32,
        min=1,
        max=256,
    )
    curvature_sampling_radius: FloatProperty(
        name="Sampling Radius",
        description="Radius used when measuring local curvature",
        default=0.001,
        min=0.0,
    )
    curvature_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale curvature sampling distance relative to the mesh bounding box",
        default=True,
    )
    curvature_mesh_match_mode: EnumProperty(
        name="Self Intersection",
        description="Choose how meshes are matched while computing curvature intersections",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    curvature_normal_map_path: StringProperty(
        name="Normal Map",
        description="Optional normal map used to guide curvature computation",
        subtype="FILE_PATH",
        default="",
    )
    curvature_normal_map_space: EnumProperty(
        name="Map Type",
        description="Coordinate space used by the curvature normal map",
        items=SDB_NORMAL_MAP_SPACE_ITEMS,
        default="tangent_space",
    )
    curvature_normal_map_orientation: EnumProperty(
        name="Normal Orientation",
        description="Normal map axis convention used by curvature",
        items=SDB_NORMAL_MAP_ORIENTATION_ITEMS,
        default="directx",
    )
    curvature_auto_minmax: BoolProperty(
        name="Auto Tonemapping",
        description="Let the curvature baker choose value bounds automatically",
        default=True,
    )
    curvature_value_min: FloatProperty(
        name="Min",
        description="Manual minimum curvature value when auto tonemapping is disabled",
        default=-1.0,
    )
    curvature_value_max: FloatProperty(
        name="Max",
        description="Manual maximum curvature value when auto tonemapping is disabled",
        default=1.0,
    )
    height_normalization: EnumProperty(
        name="Normalization",
        description="How height values are normalized into the output texture",
        items=SDB_HEIGHT_NORMALIZATION_ITEMS,
        default="low_poly_distance",
    )
    height_divisor: FloatProperty(
        name="Scaling Divisor",
        description="Manual divisor used by the height baker when supported by the selected normalization",
        default=1.0,
        min=0.0,
    )
    normal_output_texture_space: EnumProperty(
        name="Output Type",
        description="Coordinate space written by the normal baker",
        items=SDB_OUTPUT_TEXTURE_SPACE_ITEMS,
        default="tangent_space",
    )
    normal_output_texture_orientation: EnumProperty(
        name="Output Orientation",
        description="Normal orientation convention written by the normal baker",
        items=SDB_OUTPUT_TEXTURE_ORIENTATION_ITEMS,
        default="directx",
    )
    thickness_secondary_sample_count: IntProperty(
        name="Secondary Rays",
        description="Number of rays used by the thickness baker",
        default=64,
        min=1,
        max=256,
    )
    thickness_secondary_min_distance: FloatProperty(
        name="Min Occluder Distance",
        description="Ignore thickness hits closer than this distance",
        default=0.00001,
        min=0.0,
    )
    thickness_secondary_max_distance: FloatProperty(
        name="Max Occluder Distance",
        description="Ignore thickness hits farther than this distance",
        default=0.1,
        min=0.0,
    )
    thickness_secondary_normalized_distance: BoolProperty(
        name="Relative To Bounding Box",
        description="Scale thickness distances relative to the mesh bounding box",
        default=True,
    )
    thickness_secondary_spread_angle: FloatProperty(
        name="Spread Angle",
        description="Angular spread of thickness rays in degrees",
        default=180.0,
        min=0.0,
        max=180.0,
    )
    thickness_secondary_sample_distribution: EnumProperty(
        name="Distribution",
        description="Distribution pattern used for thickness rays",
        items=SDB_DISTRIBUTION_ITEMS,
        default="cosine",
    )
    thickness_secondary_mesh_match_mode: EnumProperty(
        name="Self Occlusion",
        description="Choose which meshes are allowed to occlude thickness rays",
        items=SDB_MATCH_MODE_ITEMS,
        default="match_all",
    )
    thickness_normalization: EnumProperty(
        name="Normalization",
        description="How thickness values are normalized into the output texture",
        items=SDB_THICKNESS_NORMALIZATION_ITEMS,
        default="min_max",
    )
    export_source_kind: EnumProperty(name="Export Source", items=SDB_EXPORT_SOURCE_ITEMS, default="INTERNAL_FBX")
    export_source_name: StringProperty(name="Export Source Name", default="")
    export_source_path: StringProperty(name="Export Source Path", subtype="FILE_PATH", default="")
    export_source_label: StringProperty(name="Export Source Label", default="")
    preview_items: CollectionProperty(type=LCW_PG_SDBPreviewItem)
    preview_target_count: IntProperty(name="Preview Targets", default=0, min=0)
    preview_group_count: IntProperty(name="Preview Groups", default=0, min=0)
    preview_skipped_count: IntProperty(name="Preview Skipped", default=0, min=0)
    preview_message: StringProperty(name="Preview Message", default="")
    last_export_path: StringProperty(name="Last Export Path", subtype="FILE_PATH", default="")
    last_output_dir: StringProperty(name="Last Output Directory", subtype="DIR_PATH", default="")
    last_log_path: StringProperty(name="Last Log Path", subtype="FILE_PATH", default="")
    last_plan_path: StringProperty(name="Last Plan Path", subtype="FILE_PATH", default="")
    last_job_id: StringProperty(name="Last Job ID", default="")
    last_summary: StringProperty(name="Last Summary", default="")
    job_status: EnumProperty(name="Job Status", items=SDB_JOB_STATUS_ITEMS, default="IDLE")
    job_message: StringProperty(name="Job Message", default="")
    export_section_open: BoolProperty(name="Export Section", default=True)
    preview_section_open: BoolProperty(name="Preview Section", default=True)
    scope_section_open: BoolProperty(name="Scope Section", default=True)
    bakers_section_open: BoolProperty(name="Bakers Section", default=True)
    ambient_occlusion_section_open: BoolProperty(name="Ambient Occlusion Section", default=True)
    bent_normal_section_open: BoolProperty(name="Bent Normal Section", default=False)
    curvature_section_open: BoolProperty(name="Curvature Section", default=False)
    height_section_open: BoolProperty(name="Height Section", default=False)
    normal_section_open: BoolProperty(name="Normal Section", default=False)
    thickness_section_open: BoolProperty(name="Thickness Section", default=False)
    high_poly_section_open: BoolProperty(name="Setup High Poly Meshes", default=False)
    defaults_section_open: BoolProperty(name="Common Settings", default=True)
    actions_section_open: BoolProperty(name="Bake Actions", default=True)


class LCW_PG_SceneState(bpy.types.PropertyGroup):
    material_quick_name_1: StringProperty(name="Quick Name 1", default="")
    material_quick_name_2: StringProperty(name="Quick Name 2", default="")
    material_quick_name_3: StringProperty(name="Quick Name 3", default="")
    panel_order: StringProperty(name="Main Category Order", default=",".join(PANEL_ORDER_DEFAULT))
    favorite_actions: CollectionProperty(type=LCW_PG_FavoriteAction)
    substance_designer_baker: PointerProperty(type=LCW_PG_SubstanceDesignerBakeState)


class LCW_PG_WindowState(bpy.types.PropertyGroup):
    material_name: StringProperty(name="Material", default="cavity_bake_v2")
    face_material_name: StringProperty(name="Face Material", default="00_Config_wood_int")
    color_attribute_name: StringProperty(name="Color Attribute", default="Color")
    color_attribute_domain: EnumProperty(name="Color Domain", items=COLOR_DOMAIN_ITEMS, default="CORNER")
    color_attribute_type: EnumProperty(name="Color Type", items=COLOR_TYPE_ITEMS, default="BYTE_COLOR")
    replace_color_attribute: BoolProperty(name="Replace Existing", default=False)
    color_initialize_value: FloatVectorProperty(
        name="Initialize Color",
        subtype="COLOR_GAMMA",
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 1.0),
    )
    color_mask_type: EnumProperty(name="Mask Type", items=COLOR_MASK_ITEMS, default="FACE")
    color_blend_mode: EnumProperty(name="Blend Mode", items=COLOR_BLEND_ITEMS, default="SET")
    color_value: FloatVectorProperty(
        name="Color",
        subtype="COLOR_GAMMA",
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
    LCW_PG_BakerProfile,
    LCW_PG_SDBPreviewItem,
    LCW_PG_SubstanceDesignerBakeState,
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
