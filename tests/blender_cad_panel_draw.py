"""Exercise panel draw branches against registered Blender RNA and icon enums."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction.panels import LCW_PT_cad_reconstruction


class OperatorProperties:
    def __init__(self, rna):
        object.__setattr__(self, 'rna', rna)

    def __setattr__(self, key, value):
        assert key in self.rna.properties, key
        object.__setattr__(self, key, value)


class Layout:
    def __init__(self, calls, icons, path=()):
        self.calls = calls
        self.icons = icons
        self.path = path

    def _child(self, name):
        return Layout(self.calls, self.icons, self.path + (name, len(self.calls)))

    def row(self, **kwargs):
        return self._child('row')

    def column(self, **kwargs):
        return self._child('column')

    def split(self, **kwargs):
        return self._child('split')

    def box(self):
        return self._child('box')

    def _icon(self, kwargs):
        if 'icon' in kwargs:
            assert kwargs['icon'] in self.icons, kwargs['icon']

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self._icon(kwargs)
        self.calls.append(('prop', name, self.path, kwargs))

    def label(self, **kwargs):
        self._icon(kwargs)
        self.calls.append(('label', kwargs.get('text', ''), self.path, kwargs))

    def operator(self, name, **kwargs):
        self._icon(kwargs)
        namespace, operator = name.split('.')
        rna = getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        self.calls.append(('operator', name, self.path, kwargs))
        return OperatorProperties(rna)


addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.workflow_mode = "POWER_USER"
    icons = {item.identifier for item in bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items}
    area = next(area for area in bpy.context.window.screen.areas if area.type == 'VIEW_3D')
    bpy.ops.mesh.primitive_cube_add()
    source = bpy.context.object
    row = state.analysis_lines.add()
    row.source = source
    row.message = 'Screened recommendation.'
    row.recommendation = '{"arcs": false}'
    row.run_dir = str(Path(__file__).parent)
    state.analysis_ready = True
    state.analysis_details_open = True
    result = state.results.add()
    result.source = source
    result.source_label = 'Cube / Solid 1'
    result.status = 'REVIEW'
    result.details_open = True
    result.partial = True
    for busy in (False, True):
        state.analysis_running = busy
        for mode in ('SELECTED', 'COLLECTION'):
            state.mode = mode
            calls = []
            with bpy.context.temp_override(area=area):
                LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(calls, icons)), bpy.context)
            assert any(c[0:2] == ('prop', 'hole_detail_factor') for c in calls)
            hole_path = next(c[2] for c in calls if c[0:2] == ('prop', 'circular_holes'))
            factor_path = next(c[2] for c in calls if c[0:2] == ('prop', 'hole_detail_factor'))
            assert hole_path == factor_path[:-2], (hole_path, factor_path)
            assert any(c[0:2] == ('prop', 'hole_epsilon_mm') for c in calls)
            assert any(c[0:2] == ('prop', 'worker_timeout_minutes') for c in calls)
            assert not any('Try Non-Manifold' in c[3].get('text', '') for c in calls)
    state.workflow_mode='AUTO'
    state.auto_run_settings_open=False
    calls=[]
    with bpy.context.temp_override(area=area):
        LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(calls, icons)), bpy.context)
    properties={c[1] for c in calls if c[0]=='prop'}
    assert {'auto_hole_detail_factor','auto_epsilon_mm','auto_hole_epsilon_mm','auto_perimeter_clearance_mm'}<=properties
    assert not {'hole_detail_factor','epsilon_mm','arcs','separate_solids','normal_override','output_collection','concurrent_workers'}&properties
    assert not any(c[:2]==('operator','lcw.cad_analyze') for c in calls)
    assert any(c[3].get('text')=='Analyze & Reconstruct' for c in calls)
    assert 'worker_timeout_minutes' not in properties
    state.auto_run_settings_open=True
    calls=[]
    with bpy.context.temp_override(area=area):
        LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(calls, icons)), bpy.context)
    assert any(c[0:2] == ('prop', 'worker_timeout_minutes') for c in calls)
    assert any(c[0:2] == ('prop', 'auto_objective') for c in calls)
    for objective in ('LIGHTWEIGHT', 'EDITABLE'):
        state.auto_objective = objective
        state.protection_section_open = True
        calls=[]
        with bpy.context.temp_override(area=area):
            LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(calls, icons)), bpy.context)
        protect = [c for c in calls if c[:2] == ('operator', 'lcw.cad_protect_faces')]
        assert len(protect) == 4, protect
        assert any('protected face' in c[1] for c in calls if c[0] == 'label')
        assert any(objective.title() in c[1] for c in calls if c[0] == 'label')
    print('CAD_PANEL_DRAW_RNA_BRANCHES_OK')
finally:
    addon.unregister()
print('PASS blender_cad_panel_draw')
