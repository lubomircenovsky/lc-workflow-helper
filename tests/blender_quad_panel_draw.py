"""Draw the Quad Reconstruction panel against registered RNA, incl. the progress bar.

blender --background --factory-startup --python tests/blender_quad_panel_draw.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.icons import status_icon
from LC_workflow_addon.quad_reconstruction.panels import (
    LCW_PT_quad_reconstruction,
    LCW_UL_quad_analysis_results,
)

FUNCTIONS = bpy.types.UILayout.bl_rna.functions


class Layout:
    def __init__(self, calls):
        self.calls = calls
        self.scale_y = 1.0

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

    def separator(self, **kwargs):
        self._check('separator', kwargs)
        self.calls.append(('separator', kwargs.get('type', 'AUTO'), kwargs))

    def operator(self, name, **kwargs):
        self._check('operator', kwargs)
        namespace, operator = name.split('.')
        getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        # 4th item: scale_y of the row the operator sits in (primary-action size).
        self.calls.append(('operator', name, kwargs, self.scale_y))
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
    print('QUAD_PANEL_PROGRESS_OK')

    def draw():
        calls = []
        LCW_PT_quad_reconstruction.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
        return calls

    def icon_of(call):
        return {key: value for key, value in call[2].items() if key != 'text'}

    def label(calls, text):
        return next(c for c in calls if c[0] == 'label' and c[1] == text)

    # Phase 2: line before the action box, primary row enlarged, Cancel normal height.
    state.active_run_id = ''
    calls = draw()
    first_line = next(i for i, c in enumerate(calls) if c[:2] == ('separator', 'LINE'))
    analyze = next(i for i, c in enumerate(calls) if c[:2] == ('operator', 'lcw.quad_reconstruction_analyze_modal'))
    assert first_line < analyze, (first_line, analyze)
    assert calls[analyze][3] == 1.3
    state.active_run_id = 'test-run'
    cancel = next(c for c in draw() if c[:2] == ('operator', 'lcw.quad_reconstruction_cancel'))
    assert cancel[3] == 1.0, cancel
    state.active_run_id = ''

    # Phase 4: batch Status line per job_status; a finished batch is never green.
    for job_status, kind, text in (
            ('IDLE', 'idle', 'Idle'), ('ANALYZING', 'running', 'Analyzing'),
            ('RECONSTRUCTING', 'running', 'Reconstructing'), ('ANALYZED', 'info', 'Analysis finished'),
            ('RECONSTRUCTED', 'info', 'Run finished'), ('FAILED', 'error', 'Run failed'),
            ('CANCELLED', 'cancelled', 'Run cancelled')):
        state.job_status = job_status
        assert icon_of(label(draw(), f'Status: {text}')) == status_icon(kind), job_status
    state.job_status = 'IDLE'

    # Phase 4: per-object rules in Codex's order, list row and details box.
    bpy.ops.mesh.primitive_cube_add()
    output = bpy.context.object
    base = dict(status='RECONSTRUCTED', fingerprint_unchanged=True, validation_passed=True,
                solver_exact=True, relaxation_count=0, unresolved_triangle_count=0,
                warning_count=0, confidence_label='HIGH', classification='MIXED_TRI_QUAD',
                details='ok')
    cases = (
        ('validated', dict(), True, 'ok', 'Validated'),
        ('failed', dict(status='FAILED', fingerprint_unchanged=False, details='boom'), False, 'error', 'FAILED: boom'),
        ('fingerprint', dict(fingerprint_unchanged=False), True, 'error', 'Source integrity check failed'),
        ('analyzed', dict(status='ANALYZED', validation_passed=False), False, 'info', 'ANALYZED: Mixed Tri Quad'),
        ('analyzed_warn', dict(status='ANALYZED', warning_count=2), False, 'warning', 'ANALYZED: 2 warning(s)'),
        ('invalid', dict(validation_passed=False), True, 'error', 'Validation failed'),
        ('no_output', dict(), False, 'warning', 'Output unavailable: last result retained'),
        ('fallback', dict(solver_exact=False), True, 'warning', 'Validated, review: fallback solver'),
        ('relaxed', dict(relaxation_count=1, confidence_label='MEDIUM'), True, 'warning',
         'Validated, review: 1 relaxation(s), MEDIUM confidence'),
        ('unknown', dict(status=''), False, 'idle', 'Result unavailable'),
    )
    state.results.clear()
    state.results_section_open = True
    for index, (name, overrides, has_output, kind, text) in enumerate(cases):
        item = state.results.add()
        item.source_object_name = name
        item.source_mesh_name = name
        for key, value in {**base, **overrides}.items():
            setattr(item, key, value)
        item.output_object = output if has_output else None
        row_calls = []
        LCW_UL_quad_analysis_results.draw_item(
            None, bpy.context, Layout(row_calls), state, item, 0, state, 'active_result_index', index)
        assert icon_of(label(row_calls, name)) == status_icon(kind), (name, row_calls)
        state.active_result_index = index
        calls = draw()
        assert icon_of(label(calls, text)) == status_icon(kind), (name, [c[1] for c in calls if c[0] == 'label'])
        # Source integrity line keeps its own meaning, independent of result severity.
        integrity = 'Source unchanged' if item.fingerprint_unchanged else 'Source fingerprint verification failed'
        assert icon_of(label(calls, integrity)) == status_icon('ok' if item.fingerprint_unchanged else 'error')
        lines = [i for i, c in enumerate(calls) if c[:2] == ('separator', 'LINE')]
        if has_output:
            runtime = next(i for i, c in enumerate(calls) if c[0] == 'label' and c[1].startswith('Runtime:'))
            coverage = next(i for i, c in enumerate(calls) if c[0] == 'label' and c[1].startswith('Coverage:'))
            assert any(runtime < i < coverage for i in lines), (runtime, coverage, lines)
        else:
            assert len(lines) == 1, lines
    print('QUAD_PANEL_RESULT_SEVERITY_OK')
    print('PASS blender_quad_panel_draw')
finally:
    addon.unregister()
