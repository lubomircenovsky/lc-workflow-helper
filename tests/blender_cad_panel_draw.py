"""Exercise panel draw branches against registered Blender RNA and icon enums."""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.icons import status_icon
from LC_workflow_addon.cad_reconstruction.panels import LCW_PT_cad_reconstruction, draw_uv_preparation


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

    def separator(self, **kwargs):
        params = bpy.types.UILayout.bl_rna.functions['separator'].parameters
        for key, value in kwargs.items():
            assert key in params, ('separator', key)
            if params[key].type == 'ENUM':
                assert value in {item.identifier for item in params[key].enum_items}, ('separator', key, value)
        self.calls.append(('separator', kwargs.get('type', 'AUTO'), self.path, kwargs))

    def label(self, **kwargs):
        self._icon(kwargs)
        self.calls.append(('label', kwargs.get('text', ''), self.path, kwargs))

    def operator(self, name, **kwargs):
        self._icon(kwargs)
        namespace, operator = name.split('.')
        rna = getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        # 5th item: scale_y of the layout the operator sits in (primary-action size).
        self.calls.append(('operator', name, self.path, kwargs, getattr(self, 'scale_y', 1.0)))
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

    # The primary action stays visible when every settings section is collapsed.
    for mode in ('AUTO', 'POWER_USER'):
        state.workflow_mode = mode
        state.run_section_open = False
        state.auto_run_settings_open = False
        state.uv_prep_section_open = True
        calls = []
        with bpy.context.temp_override(area=area):
            LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(calls, icons)), bpy.context)
        assert any(c[:2] == ('operator', 'lcw.cad_reconstruct') for c in calls), mode
        assert not any(c[0] == 'prop' and c[1].startswith('uv_prep') for c in calls), 'UV prep moved to UV panel'
        assert any(c[:2] == ('operator', 'lcw.cad_object_colors') for c in calls)
        assert any(c[:2] == ('operator', 'lcw.cad_hide_object_colors') for c in calls)
    calls = []
    with bpy.context.temp_override(area=area):
        draw_uv_preparation(Layout(calls, icons), bpy.context)
    assert {'uv_prep_map_name', 'uv_prep_margin', 'uv_prep_angle_degrees'} <= {c[1] for c in calls if c[0] == 'prop'}
    assert any(c[:2] == ('operator', 'lcw.cad_prepare_uv') for c in calls)
    print('CAD_PANEL_PRIMARY_ACTION_AND_UV_PREP_OK')

    def draw(layout_calls):
        with bpy.context.temp_override(area=area):
            LCW_PT_cad_reconstruction.draw(SimpleNamespace(layout=Layout(layout_calls, icons)), bpy.context)

    def label_icon(layout_calls, text):
        return {key: value for key, value in next(
            c for c in layout_calls if c[0] == 'label' and c[1] == text)[3].items() if key != 'text'}

    # Phase 2 orientation: section headings and the line before Results.
    state.analysis_running = False
    for mode in ('AUTO', 'POWER_USER'):
        state.workflow_mode = mode
        calls = []
        draw(calls)
        texts = [c[1] for c in calls if c[0] == 'label']
        assert ('Objective & Limits' in texts) == (mode == 'AUTO'), (mode, texts)
        run_index = next(i for i, c in enumerate(calls) if c[:2] == ('label', 'Run'))
        assert calls[run_index][3].get('icon') == 'PLAY'
        line_index = next(i for i, c in enumerate(calls) if c[:2] == ('separator', 'LINE'))
        results_index = next(i for i, c in enumerate(calls) if c[:2] == ('label', 'Results'))
        assert run_index < line_index < results_index, (run_index, line_index, results_index)
        if mode == 'AUTO':
            assert label_icon(calls, 'Objective & Limits') == {'icon': 'PREFERENCES'}
        reconstruct = next(c for c in calls if c[:2] == ('operator', 'lcw.cad_reconstruct'))
        assert reconstruct[4] == 1.3, reconstruct
    print('CAD_PANEL_SECTION_HEADINGS_OK')

    # Phase 4 severity: each result status maps to its own status icon.
    state.workflow_mode = 'POWER_USER'
    state.results_section_open = True
    state.results_visible = max(state.results_visible, 10)
    state.results.clear()
    expected = {}
    for status, partial, kind, text in (
            ('PENDING', False, 'idle', 'PENDING'),
            ('RUNNING', False, 'running', 'RUNNING'),
            ('PASS', False, 'ok', 'PASS'),
            ('REVIEW', False, 'warning', 'REVIEW'),
            ('REVIEW', True, 'warning', 'PARTIAL / REVIEW'),
            ('FAIL', False, 'error', 'FAIL'),
            ('', False, 'idle', 'Unknown status')):
        result = state.results.add()
        result.source = source
        result.source_label = f'Cube {status or "blank"} {partial}'
        result.status = status
        result.partial = partial
        result.details_open = True
        result.reason = 'Skipped region.'
        expected[f'{result.source_label}: {text}'] = kind
    # Analysis lines: blocker is an error in words and icon, a note is info.
    state.analysis_lines.clear()
    for severity, message in (('BLOCKER', 'Cube: Repair mesh first.'), ('NOTE', 'Cube: Negative scale.')):
        line = state.analysis_lines.add()
        line.source = source
        line.severity = severity
        line.message = message
    for blockers in (0, 1):
        state.analysis_ready = True
        state.analysis_blockers = blockers
        calls = []
        draw(calls)
        for text, kind in expected.items():
            assert label_icon(calls, text) == status_icon(kind), (text, kind)
        assert label_icon(calls, 'BLOCKER: Cube: Repair mesh first.') == status_icon('error')
        assert label_icon(calls, 'Cube: Negative scale.') == status_icon('info')
        summary = next(c for c in calls if c[0] == 'label' and ' blocked | ' in c[1])
        assert {k: v for k, v in summary[3].items() if k != 'text'} == status_icon('error' if blockers else 'ok')
    print('CAD_PANEL_RESULT_SEVERITY_OK')

    calls = []
    with bpy.context.temp_override(area=area):
        draw_uv_preparation(Layout(calls, icons), bpy.context)
    assert all(c[4] == 1.15 for c in calls if c[:2] in {('operator', 'lcw.cad_analyze_uv'),
                                                         ('operator', 'lcw.cad_prepare_uv')}), calls
    assert any(c[:2] == ('operator', 'lcw.cad_analyze_uv') for c in calls)
finally:
    addon.unregister()
print('PASS blender_cad_panel_draw')
