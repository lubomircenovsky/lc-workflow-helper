"""Babylon panel RNA, persisted outcomes and modal write boundaries (Blender 5.2)."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.icons import status_icon
from LC_workflow_addon.babylon_export import operators, panels
from LC_workflow_addon.babylon_export.bake import RUNNING, FINISHED, FAILED, CANCELLED
from LC_workflow_addon.babylon_export.core import Issue
from LC_workflow_addon.babylon_export.reporting import store_outcome

FUNCTIONS = bpy.types.UILayout.bl_rna.functions
META = ('last_operation', 'last_outcome', 'report_collection')


class OperatorProperties:
    def __init__(self, rna):
        object.__setattr__(self, 'rna', rna)

    def __setattr__(self, name, value):
        assert name in self.rna.properties, name
        object.__setattr__(self, name, value)


class Layout:
    def __init__(self, calls):
        object.__setattr__(self, 'calls', calls)

    def __setattr__(self, name, value):
        assert name in bpy.types.UILayout.bl_rna.properties, name
        self.calls.append(('attribute', name, value))

    def _check(self, method, kwargs):
        params = FUNCTIONS[method].parameters
        for name, value in kwargs.items():
            assert name in params, (method, name)
            if params[name].type == 'ENUM':
                assert value in {i.identifier for i in params[name].enum_items}, (method, name, value)
        if 'icon_value' in kwargs:
            assert isinstance(kwargs['icon_value'], int) and kwargs['icon_value'] > 0

    def _child(self, **kwargs):
        return Layout(self.calls)

    row = column = box = _child

    def label(self, **kwargs):
        self._check('label', kwargs)
        self.calls.append(('label', kwargs.get('text'), kwargs))

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self._check('prop', kwargs)
        self.calls.append(('prop', name, kwargs))

    def operator(self, name, **kwargs):
        self._check('operator', kwargs)
        namespace, identifier = name.split('.')
        rna = getattr(getattr(bpy.ops, namespace), identifier).get_rna_type()
        self.calls.append(('operator', name, kwargs))
        return OperatorProperties(rna)

    def separator(self, **kwargs):
        self._check('separator', kwargs)
        self.calls.append(('separator', kwargs))

    def progress(self, **kwargs):
        self._check('progress', kwargs)
        self.calls.append(('progress', kwargs))

    def template_list(self, name, identifier, data, prop, active_data, active_prop, **kwargs):
        assert name == 'LCW_UL_babylon_materials'
        assert prop in data.bl_rna.properties and active_prop in active_data.bl_rna.properties
        self._check('template_list', kwargs)
        self.calls.append(('list', name))


class ReadOnlyState:
    def __init__(self, state):
        object.__setattr__(self, 'state', state)

    def __getattr__(self, name):
        return getattr(self.state, name)

    def __setattr__(self, name, value):
        raise AssertionError(f'Unexpected scene write while running/drawing: {name}')


def snapshot(state):
    return tuple(getattr(state, name) for name in META) + (state.last_report,)


def draw(state, job=None):
    calls, statuses = [], []
    context = SimpleNamespace(scene=SimpleNamespace(lcw_babylon_export=ReadOnlyState(state)),
                              view_layer=bpy.context.view_layer)
    before = snapshot(state)

    def icon(value):
        statuses.append(value)
        return status_icon(value)

    with patch.object(panels, 'active_job', return_value=job), patch.object(panels, 'status_icon', icon):
        panels.LCW_PT_babylon_export.draw(SimpleNamespace(layout=Layout(calls)), context)
    assert snapshot(state) == before
    assert ('separator', {'type': 'LINE'}) in calls
    return calls, statuses


def fake_operator(**kwargs):
    return SimpleNamespace(report=lambda *_: None, **kwargs)


def modal(state, collection, status, export_after=False, failure=None):
    job = SimpleNamespace(
        scene=bpy.context.scene, scene_valid=lambda: True, message='Bake result',
        step=lambda: status, progress_text=lambda: 'Pass 1/2',
        adapter=SimpleNamespace(bake_job_running=lambda: True))
    if failure:
        def step():
            raise RuntimeError(failure)
        job.step = step
        job.finish = lambda result, message: setattr(job, 'message', message) or FAILED
    op = fake_operator(_job=job, _collection=collection, export_after=export_after,
                       _shown_text='', _end=lambda context, result: result)
    with patch.object(operators, 'active_job', return_value=job), \
            patch.object(operators, 'set_active_job'), patch.object(operators, '_redraw'):
        return operators.LCW_OT_babylon_bake.modal(op, bpy.context, SimpleNamespace(type='TIMER'))


addon.register()
try:
    collection = bpy.data.collections.new('Report target')
    other = bpy.data.collections.new('Other target')
    bpy.context.scene.collection.children.link(collection)
    bpy.context.scene.collection.children.link(other)
    state = bpy.context.scene.lcw_babylon_export
    state.target_collection = collection
    assert state.last_operation == state.last_outcome == 'UNKNOWN'
    calls, statuses = draw(state)
    assert 'idle' in statuses
    labels = [c[1] for c in calls if c[0] == 'label']
    for title in ('Bake Settings', 'Export Settings', 'Materials to Bake', 'Last Operation'):
        assert title in labels, title
    assert ('attribute', 'scale_y', 1.3) in calls

    for outcome, expected in (('OK', 'ok'), ('WARNING', 'warning'), ('ERROR', 'error'),
                               ('CANCELLED', 'cancelled'), ('UNKNOWN', 'idle')):
        store_outcome(state, collection, 'BAKE', outcome)
        assert expected in draw(state)[1]
    store_outcome(state, collection, 'CHECK', 'OK')
    state.target_collection = other
    calls, statuses = draw(state)
    assert 'info' in statuses and 'ok' not in statuses
    assert any(c[:2] == ('label', 'Last report: Report target') for c in calls)
    state.target_collection = collection
    state.report_collection = None
    assert 'info' in draw(state)[1]

    operators.store_issues(state, [Issue('ERROR', 'Stale issue must stay hidden')])
    for cancel in (False, True):
        job = SimpleNamespace(cancel_requested=cancel, progress_text=lambda: 'Pass 1/2',
                              total_passes=2, pass_index=0)
        calls, statuses = draw(state, job)
        assert ('cancelled' if cancel else 'running') in statuses
        assert 'error' not in statuses
        assert not any('Stale issue' in str(c) for c in calls)
        assert not any(c[:2] == ('operator', 'lcw.babylon_bake') for c in calls)
    print('PASS babylon_panel_rna_and_status_branches')

    # Check, including warnings and material-list refresh failure.
    for issues, outcome in (([], 'OK'), ([Issue('WARNING', 'Review')], 'WARNING'),
                             ([Issue('ERROR', 'Blocked')], 'ERROR')):
        with patch.object(operators, 'refresh_material_list'), patch.object(operators, 'validate', return_value=issues):
            operators.LCW_OT_babylon_check.execute(fake_operator(), bpy.context)
        assert snapshot(state)[:3] == ('CHECK', outcome, collection)
    with patch.object(operators, 'refresh_material_list', side_effect=ValueError('Refresh failed')):
        assert operators.LCW_OT_babylon_check.execute(fake_operator(), bpy.context) == {'CANCELLED'}
        assert state.last_outcome == 'ERROR'
        operators.LCW_OT_babylon_refresh_materials.execute(fake_operator(), bpy.context)
        assert state.last_outcome == 'UNKNOWN', 'Refresh must invalidate the replaced report'
    with patch.object(operators, 'refresh_material_list'), \
            patch.object(operators, 'validate', side_effect=RuntimeError('Check exception')):
        operators.LCW_OT_babylon_check.execute(fake_operator(), bpy.context)
        assert state.last_operation == 'CHECK' and state.last_outcome == 'ERROR'
        operators.run_export(collection, state)
        assert state.last_operation == 'EXPORT' and state.last_outcome == 'ERROR'

    # Export validation, actual export exception, GLB verification and warnings.
    for issues, verified, error, outcome in (
            ([Issue('ERROR', 'Blocked')], True, None, 'ERROR'),
            ([], True, RuntimeError('Export failed'), 'ERROR'),
            ([], False, None, 'ERROR'), ([], True, None, 'OK'),
            ([Issue('WARNING', 'Review')], True, None, 'WARNING')):
        report = dict(ok=verified, errors=[] if verified else ['Bad GLB'], document={},
                      bytes=20, variants=0, images=0)
        with patch.object(operators, 'validate', return_value=issues), \
                patch.object(operators, 'build_bake_plan', return_value=SimpleNamespace(variant_ids=[], objects=[])), \
                patch.object(operators, 'expected_baked_names', return_value=[]), \
                patch.object(operators, 'export_collection', return_value=Path('out.glb'), side_effect=error), \
                patch.object(operators, 'verify_glb', return_value=report):
            operators.run_export(collection, state)
        assert snapshot(state)[:3] == ('EXPORT', outcome, collection)

    # Running modal must not write ANY state; even writing the same value fails.
    before = snapshot(state)
    guarded_context = SimpleNamespace(scene=SimpleNamespace(lcw_babylon_export=ReadOnlyState(state)))
    job = SimpleNamespace(step=lambda: RUNNING, progress_text=lambda: 'Pass 1/2',
                          adapter=SimpleNamespace(bake_job_running=lambda: True))
    op = fake_operator(_job=job, _shown_text='')
    with patch.object(operators, 'active_job', return_value=job), \
            patch.object(operators, 'store_outcome', side_effect=AssertionError('Running metadata write')):
        assert operators.LCW_OT_babylon_bake.modal(op, guarded_context, SimpleNamespace(type='TIMER')) == {'PASS_THROUGH'}
    assert snapshot(state) == before

    for status, outcome in ((FINISHED, 'OK'), (CANCELLED, 'CANCELLED'), (FAILED, 'ERROR')):
        modal(state, collection, status)
        assert snapshot(state)[:3] == ('BAKE', outcome, collection)
        if status == FINISHED:
            assert not state.issues, 'old check issues must not accompany a completed bake'
    modal(state, collection, FAILED, failure='Restore failed')
    assert state.last_outcome == 'ERROR' and 'Restore failed' in state.last_report
    for ok in (False, True):
        def export_result(target, result_state, operation):
            store_outcome(result_state, target, operation, 'OK' if ok else 'ERROR')
            return ok, 'Export result'
        with patch.object(operators, 'run_export', side_effect=export_result):
            modal(state, collection, FINISHED, export_after=True)
        assert snapshot(state)[:3] == ('BAKE_EXPORT', 'OK' if ok else 'ERROR', collection)
        if not ok:
            assert 'Bake finished; export failed' in state.last_report

    with patch.object(operators, 'refresh_material_list'), \
            patch.object(operators, 'BakeJob', return_value=SimpleNamespace(start=lambda: None)), \
            patch.object(operators, 'set_active_job'):
        # Successful invoke must not even read progress into scene state.
        context = SimpleNamespace(scene=SimpleNamespace(lcw_babylon_export=ReadOnlyState(state)),
                                  view_layer=bpy.context.view_layer, window=None,
                                  window_manager=SimpleNamespace(event_timer_add=lambda *a, **k: None,
                                                                 modal_handler_add=lambda op: None))
        before = snapshot(state)
        assert operators.LCW_OT_babylon_bake.invoke(fake_operator(export_after=False), context, None) == {'RUNNING_MODAL'}
        assert snapshot(state) == before
    with patch.object(operators, 'refresh_material_list'), \
            patch.object(operators, 'BakeJob', return_value=SimpleNamespace(start=lambda: (_ for _ in ()).throw(ValueError('Start refused')))), \
            patch.object(operators, 'validate', return_value=[]):
        operators.LCW_OT_babylon_bake.invoke(fake_operator(export_after=True), bpy.context, None)
        assert snapshot(state)[:3] == ('BAKE_EXPORT', 'ERROR', collection)

    for failure in (None, RuntimeError('Cleanup refused')):
        with patch.object(operators, 'cleanup', return_value=0, side_effect=failure):
            operators.LCW_OT_babylon_cleanup.execute(fake_operator(), bpy.context)
        assert snapshot(state)[:3] == ('CLEANUP', 'ERROR' if failure else 'OK', collection)
    print('PASS babylon_operation_writers_and_running_write_guard')

    deleted = bpy.data.collections.new('Deleted report target')
    bpy.data.collections.remove(deleted)
    store_outcome(state, deleted, 'BAKE', 'ERROR')
    assert state.report_collection is None

    # New properties survive save/load; old scenes require no migration writes.
    store_outcome(state, collection, 'EXPORT', 'WARNING')
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / 'report.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        state = bpy.context.scene.lcw_babylon_export
        assert state.last_operation == 'EXPORT' and state.last_outcome == 'WARNING'
        assert state.report_collection.name == 'Report target'
    print('PASS babylon_outcome_persistence')
finally:
    addon.unregister()
print('PASS blender_babylon_panel_draw')
