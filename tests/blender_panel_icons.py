"""Every category panel draws a valid header icon; status icons resolve.

blender --background --factory-startup --python tests/blender_panel_icons.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon import icons
from LC_workflow_addon.constants import PANEL_LABELS
from LC_workflow_addon.ui import panels

ICON_IDS = {item.identifier for item in bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items}


class Layout:
    def __init__(self, calls):
        self.calls = calls

    def _child(self, *_args, **_kwargs):
        return Layout(self.calls)

    row = column = box = split = _child

    def label(self, **kwargs):
        if 'icon' in kwargs:
            assert kwargs['icon'] in ICON_IDS, kwargs['icon']
        if 'icon_value' in kwargs:
            assert kwargs['icon_value'] > 0, kwargs
        self.calls.append(('label', kwargs))

    def prop(self, *args, **kwargs):
        self.calls.append(('prop', kwargs))

    def operator(self, *args, **kwargs):
        self.calls.append(('operator', kwargs))
        return SimpleNamespace()


def header_calls(panel_cls):
    calls = []
    panel_cls.draw_header(SimpleNamespace(layout=Layout(calls), lcw_icon_key=getattr(panel_cls, 'lcw_icon_key', None)), bpy.context)
    return calls


addon.register()
try:
    assert set(PANEL_LABELS) <= set(icons.CATEGORY_ICONS), set(PANEL_LABELS) - set(icons.CATEGORY_ICONS)
    for key, name in icons.CATEGORY_ICONS.items():
        assert name in ICON_IDS, (key, name)
    for status, name in icons.STATUS_ICONS.items():
        assert name in ICON_IDS, (status, name)
        Layout([]).label(text=status, **icons.status_icon(status))
    # Status shapes must differ: meaning never rests on color alone.
    assert len(set(icons.STATUS_ICONS.values())) == len(icons.STATUS_ICONS)

    nested = {'kalibra_tools': panels.LCW_PT_kalibra_tools, 'babylon_export': panels.LCW_PT_babylon_export}
    for key, panel_cls in {**panels.PANEL_CLASS_MAP, **nested}.items():
        calls = header_calls(panel_cls)
        assert len(calls) == 1 and calls[0][1].get('text') == '', (key, calls)
        assert calls[0][1] == {'text': '', **icons.category_icon(key)}, (key, calls)
    assert header_calls(panels.LCW_PT_root) == [], 'root panel draws no header icon'

    # Main Category Order shows the same icon as the panel header.
    bpy.context.window_manager.lcw_state.root_category_order_open = True
    calls = []
    panels.LCW_PT_root.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
    for key, label in PANEL_LABELS.items():
        assert any(c[0] == 'label' and c[1].get('text') == label
                   and c[1].get('icon', c[1].get('icon_value')) == icons.category_icon(key).get('icon', icons.category_icon(key).get('icon_value'))
                   for c in calls), key
finally:
    addon.unregister()
print('PASS blender_panel_icons')
