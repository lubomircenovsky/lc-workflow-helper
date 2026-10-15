import json
import bpy
from .core import Issue, verify_glb
from .export import cleanup, export_collection, expected_baked_names
from .plan import build_bake_plan
from .settings import target_collection
from .validation import validate
from .selection import refresh_material_list
from .reporting import issue_outcome, store_outcome
from .bake import CANCELLED, FAILED, FINISHED, RUNNING, BakeJob, active_job, set_active_job


def store_issues(state, issues):
    state.issues.clear()
    for issue in issues:
        item = state.issues.add()
        item.level, item.text = issue.level, issue.text


def refresh_for_operator(operator, collection, state, operation='UNKNOWN'):
    try:
        refresh_material_list(collection)
        return True
    except ValueError as exc:
        state.last_report = str(exc)
        collection.lcw_babylon_export.last_report = str(exc)
        store_issues(state, [Issue('ERROR', str(exc))])
        # A standalone Refresh failure replaces the old report too; invalidate
        # its typed result rather than retaining an unrelated green outcome.
        store_outcome(state, collection, operation, 'ERROR' if operation != 'UNKNOWN' else 'UNKNOWN')
        operator.report({'ERROR'}, str(exc))
        return False


class LCW_OT_babylon_refresh_materials(bpy.types.Operator):
    bl_idname = 'lcw.babylon_refresh_materials'
    bl_label = 'Refresh Material List'
    bl_description = 'Refresh used materials and automatic defaults while preserving user choices'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer) and active_job() is None

    def execute(self, context):
        collection = target_collection(context)
        if not refresh_for_operator(self, collection, context.scene.lcw_babylon_export):
            return {'CANCELLED'}
        self.report({'INFO'}, f'Materials in list: {len(collection.lcw_babylon_export.material_selections)}.')
        return {'FINISHED'}


class LCW_OT_babylon_check(bpy.types.Operator):
    bl_idname = 'lcw.babylon_check'
    bl_label = 'Check'
    bl_description = 'Check bake dependencies and existing baked materials separately'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer) and active_job() is None

    def execute(self, context):
        collection = target_collection(context)
        state = context.scene.lcw_babylon_export
        if not refresh_for_operator(self, collection, state, 'CHECK'):
            return {'CANCELLED'}
        try:
            bake_issues = validate(collection)
            export_issues = validate(collection, for_export=True)
        except Exception as exc:
            state.last_report = f'Check failed: {exc}'
            collection.lcw_babylon_export.last_report = state.last_report
            store_issues(state, [Issue('ERROR', str(exc))])
            store_outcome(state, collection, 'CHECK', 'ERROR')
            self.report({'ERROR'}, state.last_report)
            return {'CANCELLED'}
        # Shared problems appear once; bake-only messages are clearly labelled.
        shared = {(i.level, i.text) for i in export_issues}
        store_issues(state, export_issues)
        for issue in bake_issues:
            if (issue.level, issue.text) not in shared:
                item = state.issues.add()
                item.level, item.text = issue.level, f'Bake: {issue.text}'
        bake_errors = sum(i.level == 'ERROR' for i in bake_issues)
        export_errors = sum(i.level == 'ERROR' for i in export_issues)
        state.last_report = f'Export errors: {export_errors}. Bake errors: {bake_errors}.'
        collection.lcw_babylon_export.last_report = state.last_report
        store_outcome(state, collection, 'CHECK', issue_outcome(state.issues))
        self.report({'WARNING' if export_errors or bake_errors else 'INFO'}, state.last_report)
        return {'FINISHED'}


class LCW_OT_babylon_export(bpy.types.Operator):
    bl_idname = 'lcw.babylon_export'
    bl_label = 'Export'
    bl_description = 'Export existing baked materials and variants as GLB, then verify and clean up'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer) and active_job() is None

    def execute(self, context):
        collection = target_collection(context)
        state = context.scene.lcw_babylon_export
        if not refresh_for_operator(self, collection, state, 'EXPORT'):
            return {'CANCELLED'}
        ok, message = run_export(collection, state)
        self.report({'INFO'} if ok else {'ERROR'}, message)
        return {'FINISHED'} if ok else {'CANCELLED'}


def run_export(collection, state, operation='EXPORT'):
    """Validate, export, verify; store issues and reports. Return (ok, message)."""
    settings = collection.lcw_babylon_export
    issues = []
    try:
        issues = validate(collection, for_export=True)
        store_issues(state, issues)
        if any(i.level == 'ERROR' for i in issues):
            state.last_report = 'Export cannot start: ' + next(i.text for i in issues if i.level == 'ERROR')
            settings.last_report = state.last_report
            store_outcome(state, collection, operation, 'ERROR')
            return False, state.last_report
        plan = build_bake_plan(collection)
        info = {}
        path = export_collection(collection, settings, result_info=info)
        report = verify_glb(path, expected_variants=len(plan.variant_ids),
                            require_variants=bool(plan.variant_ids), baked_suffix=settings.baked_suffix,
                            expected_baked_materials=expected_baked_names(plan))
        for text in report['errors']:
            item = state.issues.add()
            item.level, item.text = 'ERROR', text
        report.pop('document')
        report.update(info)
        settings.last_report = json.dumps(report, ensure_ascii=False)
        state.last_report = (f'{path.name}: {report["bytes"]} B. Objects: {len(plan.objects)}, '
                             f'variants: {report["variants"]}, images: {report["images"]}.')
        if not report['ok']:
            state.last_report = 'GLB failed verification. ' + state.last_report
            store_outcome(state, collection, operation, 'ERROR')
            return False, state.last_report
        store_outcome(state, collection, operation, issue_outcome(state.issues))
        return True, state.last_report
    except Exception as exc:
        state.last_report = f'Export failed: {exc}'
        settings.last_report = state.last_report
        store_issues(state, [*issues, Issue('ERROR', str(exc))])
        store_outcome(state, collection, operation, 'ERROR')
        return False, state.last_report


class LCW_OT_babylon_cleanup(bpy.types.Operator):
    bl_idname = 'lcw.babylon_cleanup'
    bl_label = 'Clean Up'
    bl_description = 'Remove all Babylon temporary datablocks left by an interrupted run'

    @classmethod
    def poll(cls, context):
        return bool(context.scene) and active_job() is None

    def execute(self, context):
        state = context.scene.lcw_babylon_export
        collection = target_collection(context)
        try:
            count = cleanup()
            message = f'Removed temporary datablocks: {count}.'
            state.last_report = message
            store_issues(state, [])
            store_outcome(state, collection, 'CLEANUP', 'OK')
            self.report({'INFO'}, message)
            return {'FINISHED'}
        except Exception as exc:
            state.last_report = f'Cleanup failed: {exc}'
            store_issues(state, [Issue('ERROR', str(exc))])
            store_outcome(state, collection, 'CLEANUP', 'ERROR')
            self.report({'ERROR'}, state.last_report)
            return {'CANCELLED'}


class LCW_OT_babylon_bake(bpy.types.Operator):
    bl_idname = 'lcw.babylon_bake'
    bl_label = 'Bake'
    bl_description = ('Bake the selected materials with SimpleBake (default state and every glTF variant), '
                      'then build the *_baked materials')

    export_after: bpy.props.BoolProperty(name='Export After Bake', default=False, options={'SKIP_SAVE'})

    _timer = None
    _shown_text = ''

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer and context.window) and active_job() is None

    def invoke(self, context, _event):
        collection = target_collection(context)
        state = context.scene.lcw_babylon_export
        operation = 'BAKE_EXPORT' if self.export_after else 'BAKE'
        if not refresh_for_operator(self, collection, state, operation):
            return {'CANCELLED'}
        job = BakeJob(collection)
        try:
            job.start()
        except Exception as exc:  # BakeError or validation failure, nothing changed yet
            state.last_report = f'Bake cannot start: {exc}'
            # List every blocking validation error, not only the summary in exc.
            errors = [i for i in validate(collection) if i.level == 'ERROR']
            store_issues(state, errors or [Issue('ERROR', str(exc))])
            store_outcome(state, collection, operation, 'ERROR')
            self.report({'ERROR'}, state.last_report)
            return {'CANCELLED'}
        self._collection = collection
        self._job = job
        set_active_job(job)
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        job.ui_timer = (context.window_manager, self._timer)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        return self.invoke(context, None)

    def modal(self, context, event):
        job = self._job
        if active_job() is not job:
            # Abandoned (file load or add-on unregister); originals are handled there.
            return self._end(context, {'CANCELLED'})
        # Esc is not handled here and SimpleBake does not handle it either;
        # the panel asks the user not to press it during a bake.
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        try:
            status = job.step()
        except Exception as exc:  # noqa: BLE001 - step() handles its own errors; this is a last resort
            status = job.finish(FAILED, f'Bake failed: {exc}')
        if status == RUNNING:
            # No scene writes and no forced viewport redraws while Blender's
            # bake thread may run: a property write tags the scene in the
            # depsgraph and a redraw evaluates it (crashes in repeated real
            # runs). The panel draws job.progress_text(); it is redrawn only
            # when that text changes, i.e. between passes.
            text = job.progress_text()
            if text != self._shown_text and not job.adapter.bake_job_running():
                self._shown_text = text
                _redraw(context)
            return {'PASS_THROUGH'}
        set_active_job(None)
        if not job.scene_valid():
            # Never publish the old job's result into a different scene.
            return self._end(context, {'CANCELLED'})
        state = job.scene.lcw_babylon_export
        state.last_report = job.message
        operation = 'BAKE_EXPORT' if self.export_after else 'BAKE'
        if status == FINISHED and self.export_after:
            ok, message = run_export(self._collection, state, operation=operation)
            prefix = '' if ok else 'Bake finished; export failed. '
            state.last_report = f'{prefix}{job.message} {message}'
            self.report({'INFO'} if ok else {'ERROR'}, state.last_report)
            return self._end(context, {'FINISHED'} if ok else {'CANCELLED'})
        store_issues(state, [Issue('ERROR', job.message)] if status == FAILED else [])
        outcome = 'OK' if status == FINISHED else 'CANCELLED' if status == CANCELLED else 'ERROR'
        store_outcome(state, self._collection, operation, outcome)
        level = {'INFO'} if status == FINISHED else {'WARNING'} if status == CANCELLED else {'ERROR'}
        self.report(level, job.message)
        return self._end(context, {'FINISHED'} if status == FINISHED else {'CANCELLED'})

    def _end(self, context, result):
        self._job.remove_ui_timer()
        self._timer = None
        _redraw(context)
        return result


class LCW_OT_babylon_bake_cancel(bpy.types.Operator):
    bl_idname = 'lcw.babylon_bake_cancel'
    bl_label = 'Cancel Bake'
    bl_description = 'Stop after the current SimpleBake pass and restore the original materials'

    @classmethod
    def poll(cls, context):
        return active_job() is not None

    def execute(self, context):
        active_job().request_cancel()
        return {'FINISHED'}


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


CLASSES = (LCW_OT_babylon_refresh_materials, LCW_OT_babylon_check, LCW_OT_babylon_export, LCW_OT_babylon_cleanup,
           LCW_OT_babylon_bake, LCW_OT_babylon_bake_cancel)
