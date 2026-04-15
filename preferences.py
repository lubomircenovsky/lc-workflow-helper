from __future__ import annotations

import bpy
from bpy.props import CollectionProperty, IntProperty

from .properties import LCW_PG_WorkflowPreset


class LCW_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    presets: CollectionProperty(type=LCW_PG_WorkflowPreset)
    active_preset_index: IntProperty(name="Active Preset", default=0)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.label(text="LC Workflow helper stores workflow presets globally.")
        layout.label(text="Use the N-panel to create, edit, and run presets.")
        layout.label(text="Main category order is stored in each .blend file.")


CLASSES = (LCW_AddonPreferences,)
