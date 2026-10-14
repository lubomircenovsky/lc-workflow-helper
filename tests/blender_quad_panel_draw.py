"""Draw the Quad Reconstruction panel against registered RNA, incl. the progress bar.

blender --background --factory-startup --python tests/blender_quad_panel_draw.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.quad_reconstruction.panels import LCW_PT_quad_reconstruction

FUNCTIONS = bpy.types.UILayout.bl_rna.functions


class Layout:
    def __init__(self, calls):
        self.calls = calls

    def _child(self, *_args, **_kwargs):
        return Layout(self.calls)

    row = column = box = split = grid_flow = _child

    def _check(self, name, kwargs):
        params = FUNCTIONS[name].parameters
        for key, value in kwargs.items():
            assert key in params, (name, key)
            if params[key].type == 'ENUM':
                assert value in {item.identifier for item in params[key].enum_items}, (name, key, value)

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self._check('prop', kwargs)
        self.calls.append(('prop', name, kwargs))

    def label(self, **kwargs):
        self._check('label', kwargs)
        self.calls.append(('label', kwargs.get('text', ''), kwargs))

    def operator(self, name, **kwargs):
        self._check('operator', kwargs)
        namespace, operator = name.split('.')
        getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        self.calls.append(('operator', name, kwargs))
        return SimpleNamespace()

    def progress(self, **kwargs):
        self._check('progress', kwargs)
        self.calls.append(('progress', kwargs.get('text', ''), kwargs))

    def template_list(self, *args, **kwargs):
        self.calls.append(('list', args[0], kwargs))


addon.register()
try:
    assert LCW_PT_quad_reconstruction.bl_options == {'DEFAULT_CLOSED'}
    state = bpy.context.scene.lcw_quad_reconstruction
    for progress, label in ((0.0, ''), (0.42, 'Region 3/7')):
        state.progress = progress
        state.progress_label = label
        calls = []
        LCW_PT_quad_reconstruction.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
        bars = [c for c in calls if c[0] == 'progress']
        assert len(bars) == 1, bars
        assert abs(bars[0][2]['factor'] - progress) < 1e-6
        assert bars[0][1] == (label or f'{progress:.0%}')
        assert not any(c[:2] == ('prop', 'progress') for c in calls), 'progress must not be editable'
    print('PASS blender_quad_panel_draw')
finally:
    addon.unregister()
