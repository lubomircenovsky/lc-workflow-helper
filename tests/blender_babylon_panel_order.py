"""Kalibra and Babylon are top-level categories; old saved orders migrate.

Until 2026-10 both were nested under one "Project specific tools" category.
"""
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.constants import PANEL_LABELS, normalize_panel_order
from LC_workflow_addon.ui import panels

addon.register()
try:
    assert 'project_specific_tools' not in PANEL_LABELS
    assert not hasattr(panels, 'LCW_PT_project_specific_tools')
    for cls in (panels.LCW_PT_kalibra_tools, panels.LCW_PT_babylon_export):
        assert cls.bl_parent_id == 'LCW_PT_root', cls
    # A saved order naming the old group expands to both tools at its place.
    legacy = 'scene_info,favorites,project_specific_tools,materials'
    bpy.context.scene.lcw_scene_state.panel_order = legacy
    panels._refresh_panel_order_on_load(None)
    normalized = normalize_panel_order(legacy)
    assert normalized[:5] == ('scene_info', 'favorites', 'kalibra_tools', 'babylon_export', 'materials'), normalized
    assert set(normalized) == set(PANEL_LABELS), 'old orders have no separators; all categories present'
    assert panels.LCW_PT_kalibra_tools.bl_order == normalized.index('kalibra_tools') + 1
    assert panels.LCW_PT_babylon_export.bl_order == normalized.index('babylon_export') + 1
    # Orders saved after the split (each tool on its own) are kept as they are.
    split = 'babylon_export,scene_info,kalibra_tools'
    assert normalize_panel_order(split)[:3] == ('babylon_export', 'scene_info', 'kalibra_tools')
    assert bpy.ops.lcw.main_panel_move(panel_key='kalibra_tools', direction='DOWN') == {'FINISHED'}
finally:
    addon.unregister()
print('PASS blender_babylon_panel_order')
