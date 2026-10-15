"""User separators between LC Workflow categories: add, name, move, remove.

blender --background --factory-startup --python tests/blender_panel_separators.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.constants import (
    DEFAULT_SEPARATOR_TITLES, PANEL_LABELS, PANEL_ORDER_DEFAULT, PANEL_SEPARATOR_KEYS, normalize_panel_order)
from LC_workflow_addon.ui import panels

FUNCTIONS = bpy.types.UILayout.bl_rna.functions


class Layout:
    def __init__(self, calls):
        self.calls = calls
        self.active = True

    def _child(self, *_args, **_kwargs):
        return Layout(self.calls)

    row = column = box = split = _child

    def _check(self, name, kwargs):
        params = FUNCTIONS[name].parameters
        for key, value in kwargs.items():
            assert key in params, (name, key)
            if params[key].type == 'ENUM':
                assert value in {item.identifier for item in params[key].enum_items}, (name, key, value)

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self._check('prop', kwargs)
        self.calls.append(('prop', name, kwargs, data))

    def label(self, **kwargs):
        self._check('label', kwargs)
        self.calls.append(('label', kwargs.get('text', ''), kwargs, self))

    def operator(self, name, **kwargs):
        self._check('operator', kwargs)
        namespace, operator = name.split('.')
        getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        ns = SimpleNamespace()
        self.calls.append(('operator', name, kwargs, ns))
        return ns

    def separator(self, **kwargs):
        self._check('separator', kwargs)
        self.calls.append(('separator', kwargs.get('type', 'AUTO'), kwargs, None))


def order():
    return normalize_panel_order(bpy.context.scene.lcw_scene_state.panel_order)


def draw(panel_cls):
    calls = []
    panel_cls.draw(SimpleNamespace(layout=Layout(calls), lcw_separator_key=getattr(panel_cls, 'lcw_separator_key', '')),
                   bpy.context)
    return calls


# Normalization keeps known separators once and drops unknown keys.
assert normalize_panel_order('favorites,separator_1,separator_1,separator_99,uv')[:3] == ('favorites', 'separator_1', 'uv')
assert normalize_panel_order(None) == PANEL_ORDER_DEFAULT
assert normalize_panel_order(','.join(PANEL_ORDER_DEFAULT)) == PANEL_ORDER_DEFAULT
# A removed default separator is not brought back by normalization.
assert 'separator_1' not in normalize_panel_order(','.join(k for k in PANEL_ORDER_DEFAULT if k != 'separator_1'))

addon.register()
try:
    state = bpy.context.scene.lcw_scene_state
    first = panels.SEPARATOR_CLASS_MAP['separator_1']

    # A new file shows the default layout: four named groups.
    panels._refresh_panel_order_on_load(None)
    assert order() == PANEL_ORDER_DEFAULT
    for key, title in DEFAULT_SEPARATOR_TITLES.items():
        cls = panels.SEPARATOR_CLASS_MAP[key]
        assert cls.poll(bpy.context) and cls.bl_order == PANEL_ORDER_DEFAULT.index(key) + 1
        assert next(c for c in draw(cls) if c[0] == 'label')[1] == title, key
    # Opening the order editor gives the default separators editable names.
    assert len(state.panel_separators) == 0
    bpy.context.window_manager.lcw_state.root_category_order_open = True
    assert {i.key: i.title for i in state.panel_separators} == DEFAULT_SEPARATOR_TITLES

    # An older file's order without separators: none are shown.
    state.panel_order = ','.join(PANEL_LABELS)
    state.panel_separators.clear()
    panels.refresh_panel_registration()
    assert not first.poll(bpy.context), 'old orders have no separators'

    assert bpy.ops.lcw.main_panel_separator_add() == {'FINISHED'}
    assert order()[-1] == 'separator_1'
    assert first.poll(bpy.context) and first.bl_order == len(order())
    assert bpy.ops.lcw.main_panel_move(panel_key='separator_1', direction='UP') == {'FINISHED'}
    assert order()[-2] == 'separator_1' and first.bl_order == len(order()) - 1

    # Without a title the separator is only a line; with one, a dimmed group name.
    calls = draw(first)
    assert [c[:2] for c in calls] == [('separator', 'LINE')], calls
    state.panel_separators[0].title = 'Project'
    calls = draw(first)
    assert calls[0][:2] == ('separator', 'LINE')
    title = next(c for c in calls if c[0] == 'label')
    assert title[1] == 'Project' and title[3].active is False

    # Main Category Order lists the separator with its name field, arrows and remove.
    bpy.context.window_manager.lcw_state.root_category_order_open = True
    calls = []
    panels.LCW_PT_root.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
    assert any(c[:2] == ('prop', 'title') and c[3].key == 'separator_1' for c in calls)
    assert any(c[:2] == ('operator', 'lcw.main_panel_separator_remove') and c[3].panel_key == 'separator_1' for c in calls)
    assert any(c[:2] == ('operator', 'lcw.main_panel_separator_add') for c in calls)

    # The pool is limited; the next add after it is full is refused.
    for _ in range(len(PANEL_SEPARATOR_KEYS) - 1):
        assert bpy.ops.lcw.main_panel_separator_add() == {'FINISHED'}
    assert all(panels.SEPARATOR_CLASS_MAP[key].poll(bpy.context) for key in PANEL_SEPARATOR_KEYS)
    try:
        result = bpy.ops.lcw.main_panel_separator_add()
    except RuntimeError:
        result = {'CANCELLED'}
    assert result == {'CANCELLED'}

    # Order and names survive the load_post refresh.
    panels._refresh_panel_order_on_load(None)
    assert 'separator_1' in order() and first.poll(bpy.context)

    for key in PANEL_SEPARATOR_KEYS:
        assert bpy.ops.lcw.main_panel_separator_remove(panel_key=key) == {'FINISHED'}
    assert not any(key in order() for key in PANEL_SEPARATOR_KEYS)
    assert len(state.panel_separators) == 0
    assert not first.poll(bpy.context)
    assert set(order()) == set(PANEL_LABELS)

    # Reset restores the default layout and names in this file.
    state.panel_order = 'uv,favorites'
    assert bpy.ops.lcw.main_panel_reset_layout('EXEC_DEFAULT') == {'FINISHED'}
    assert order() == PANEL_ORDER_DEFAULT
    assert {i.key: i.title for i in state.panel_separators} == DEFAULT_SEPARATOR_TITLES
    assert all(panels.SEPARATOR_CLASS_MAP[k].poll(bpy.context) for k in DEFAULT_SEPARATOR_TITLES)
finally:
    addon.unregister()
print('PASS blender_panel_separators')
