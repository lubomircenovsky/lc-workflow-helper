from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, StringProperty

from .properties import LCW_PG_BakerProfile, LCW_PG_WorkflowPreset
from .utils.substance_designer_baker import ensure_profile_ids, get_profile_by_index


def _sync_active_baker_profile(self, context: bpy.types.Context | None) -> None:
    ensure_profile_ids(self)
    profile = get_profile_by_index(self, self.active_baker_profile_index)
    if context is None:
        return
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    file_state = getattr(scene, "lcw_scene_state", None)
    if file_state is None:
        return
    bake_state = getattr(file_state, "substance_designer_baker", None)
    if bake_state is None:
        return
    bake_state.profile_id = profile.profile_id if profile is not None else ""


class LCW_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    presets: CollectionProperty(type=LCW_PG_WorkflowPreset)
    active_preset_index: IntProperty(name="Active Preset", default=0)
    baker_profiles: CollectionProperty(type=LCW_PG_BakerProfile)
    active_baker_profile_index: IntProperty(
        name="Active Baker Profile",
        description="Selected global baker profile shown in the Bakers panel",
        default=0,
        update=_sync_active_baker_profile,
    )
    substance_baker_executable: StringProperty(
        name="Substance Baker Executable",
        description="Path to Adobe Substance 3D Designer's baker executable",
        subtype="FILE_PATH",
        default=r"C:\Program Files\Adobe\Adobe Substance 3D Designer\substance3d_baker.exe",
    )
    substance_baker_workspace_root: StringProperty(
        name="Workspace Root",
        description="Optional root folder for preview exports, plans, logs, and bake output jobs",
        subtype="DIR_PATH",
        default="",
    )
    substance_baker_backend_sal: BoolProperty(name="SAL", description="Enable the SAL raytracing backend", default=True)
    substance_baker_backend_sora: BoolProperty(name="SoRa", description="Enable the SoRa raytracing backend", default=True)
    substance_baker_keep_meshes_in_cache: BoolProperty(
        name="Keep Meshes In Cache",
        description="Keep meshes in memory between bakes when supported by the baker",
        default=True,
    )
    substance_baker_texture_cache_size: IntProperty(
        name="Texture Cache Size (MB)",
        description="Amount of memory allocated to intermediary textures used in the baking process",
        default=4096,
        min=256,
    )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.label(text="LC Workflow helper stores workflow presets globally.")
        layout.label(text="Use the N-panel to create, edit, and run presets.")
        layout.label(text="Main category order is stored in each .blend file.")
        box = layout.box()
        box.label(text="Bakers")
        box.prop(self, "substance_baker_executable")
        box.prop(self, "substance_baker_workspace_root")
        backend_row = box.row(align=True)
        backend_row.label(text="Backends")
        backend_row.prop(self, "substance_baker_backend_sal", text="SAL", toggle=True)
        backend_row.prop(self, "substance_baker_backend_sora", text="SoRa", toggle=True)
        row = box.row(align=True)
        row.prop(self, "substance_baker_keep_meshes_in_cache")
        row.prop(self, "substance_baker_texture_cache_size")
        hint_box = layout.box()
        hint_box.label(text="Baker profiles are managed from the N-panel Baker Scope section.", icon="INFO")


CLASSES = (LCW_AddonPreferences,)
