"""Old saved category orders migrate to one parent with two nested panels."""
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.constants import normalize_panel_order, PANEL_ORDER_DEFAULT
from LC_workflow_addon.ui import panels

addon.register()
try:
    for order in ('scene_info,kalibra_tools,materials', 'kalibra_tools,babylon_export,materials'):
        bpy.context.scene.lcw_scene_state.panel_order = order
        panels._refresh_panel_order_on_load(None)
        normalized = normalize_panel_order(order)
        assert set(normalized) == set(PANEL_ORDER_DEFAULT)
        assert normalized.count('project_specific_tools') == 1
        assert 'kalibra_tools' not in panels.PANEL_CLASS_MAP
        assert 'babylon_export' not in panels.PANEL_CLASS_MAP
        assert panels.LCW_PT_project_specific_tools.bl_parent_id == 'LCW_PT_root'
        assert panels.LCW_PT_kalibra_tools.bl_parent_id == 'LCW_PT_project_specific_tools'
        assert panels.LCW_PT_babylon_export.bl_parent_id == 'LCW_PT_project_specific_tools'
        assert panels.LCW_PT_project_specific_tools.bl_order == normalized.index('project_specific_tools') + 1
        assert panels.LCW_PT_kalibra_tools.bl_order == 0
        assert panels.LCW_PT_babylon_export.bl_order == 1
    assert bpy.ops.lcw.main_panel_move(panel_key='project_specific_tools', direction='DOWN') == {'FINISHED'}
finally:
    addon.unregister()
print('PASS blender_babylon_panel_order')
