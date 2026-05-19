from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, StringProperty

from .properties import LCW_PG_BakerProfile, LCW_PG_WorkflowPreset


class LCW_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    presets: CollectionProperty(type=LCW_PG_WorkflowPreset)
    active_preset_index: IntProperty(name="Active Preset", default=0)
    baker_profiles: CollectionProperty(type=LCW_PG_BakerProfile)
    active_baker_profile_index: IntProperty(name="Active Baker Profile", default=0)
    substance_baker_executable: StringProperty(
        name="Substance Baker Executable",
        subtype="FILE_PATH",
        default=r"C:\Program Files\Adobe\Adobe Substance 3D Designer\substance3d_baker.exe",
    )
    substance_baker_workspace_root: StringProperty(
        name="Workspace Root",
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

        profiles_box = layout.box()
        profiles_box.label(text="Baker Profiles")
        row = profiles_box.row()
        row.template_list(
            "LCW_UL_baker_profiles",
            "",
            self,
            "baker_profiles",
            self,
            "active_baker_profile_index",
            rows=3,
        )
        col = row.column(align=True)
        col.operator("lcw.baker_profile_add", text="", icon="ADD")
        col.operator("lcw.baker_profile_remove", text="", icon="REMOVE")
        move = col.operator("lcw.baker_profile_move", text="", icon="TRIA_UP")
        move.direction = "UP"
        move = col.operator("lcw.baker_profile_move", text="", icon="TRIA_DOWN")
        move.direction = "DOWN"

        if self.baker_profiles:
            index = max(0, min(self.active_baker_profile_index, len(self.baker_profiles) - 1))
            self.active_baker_profile_index = index
            profiles_box.prop(self.baker_profiles[index], "name")


CLASSES = (LCW_AddonPreferences,)
