import json
import bpy
from .core import Issue, verify_glb
from .export import cleanup, export_collection, expected_baked_names
from .plan import build_bake_plan
from .settings import target_collection
from .validation import validate
from .selection import refresh_material_list


def store_issues(state, issues):
    state.issues.clear()
    for issue in issues:
        item = state.issues.add()
        item.level, item.text = issue.level, issue.text


def refresh_for_operator(operator, collection, state):
    try:
        refresh_material_list(collection)
        return True
    except ValueError as exc:
        state.last_report = str(exc)
        collection.lcw_babylon_export.last_report = str(exc)
        store_issues(state, [Issue('ERROR', str(exc))])
        operator.report({'ERROR'}, str(exc))
        return False


class LCW_OT_babylon_refresh_materials(bpy.types.Operator):
    bl_idname = 'lcw.babylon_refresh_materials'
    bl_label = 'Obnovit seznam materiálů'
    bl_description = 'Refresh used materials and automatic defaults while preserving user choices'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer)

    def execute(self, context):
        collection = target_collection(context)
        if not refresh_for_operator(self, collection, context.scene.lcw_babylon_export):
            return {'CANCELLED'}
        self.report({'INFO'}, f'Materiály v seznamu: {len(collection.lcw_babylon_export.material_selections)}.')
        return {'FINISHED'}


class LCW_OT_babylon_check(bpy.types.Operator):
    bl_idname = 'lcw.babylon_check'
    bl_label = 'Kontrola'
    bl_description = 'Check bake dependencies and existing baked materials separately'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer)

    def execute(self, context):
        collection = target_collection(context)
        state = context.scene.lcw_babylon_export
        if not refresh_for_operator(self, collection, state):
            return {'CANCELLED'}
        bake_issues = validate(collection)
        export_issues = validate(collection, for_export=True)
        # Shared problems appear once; bake-only messages are clearly labelled.
        shared = {(i.level, i.text) for i in export_issues}
        store_issues(state, export_issues)
        for issue in bake_issues:
            if (issue.level, issue.text) not in shared:
                item = state.issues.add()
                item.level, item.text = issue.level, f'Pečení: {issue.text}'
        bake_errors = sum(i.level == 'ERROR' for i in bake_issues)
        export_errors = sum(i.level == 'ERROR' for i in export_issues)
        state.last_report = f'Chyby exportu: {export_errors}. Chyby pečení: {bake_errors}.'
        collection.lcw_babylon_export.last_report = state.last_report
        self.report({'WARNING' if export_errors or bake_errors else 'INFO'}, state.last_report)
        return {'FINISHED'}


class LCW_OT_babylon_export(bpy.types.Operator):
    bl_idname = 'lcw.babylon_export'
    bl_label = 'Exportovat'
    bl_description = 'Export existing baked materials and variants as GLB, then verify and clean up'

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.view_layer)

    def execute(self, context):
        collection = target_collection(context)
        settings = collection.lcw_babylon_export
        state = context.scene.lcw_babylon_export
        if not refresh_for_operator(self, collection, state):
            return {'CANCELLED'}
        issues = validate(collection, for_export=True)
        store_issues(state, issues)
        if any(i.level == 'ERROR' for i in issues):
            state.last_report = 'Export nelze spustit: ' + next(i.text for i in issues if i.level == 'ERROR')
            settings.last_report = state.last_report
            self.report({'ERROR'}, state.last_report)
            return {'CANCELLED'}
        try:
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
            state.last_report = (f'{path.name}: {report["bytes"]} B. Objekty: {len(plan.objects)}, '
                                 f'varianty: {report["variants"]}, obrázky: {report["images"]}.')
            if not report['ok']:
                state.last_report = 'GLB neprošlo kontrolou. ' + state.last_report
                self.report({'ERROR'}, state.last_report)
                return {'CANCELLED'}
            self.report({'INFO'}, state.last_report)
            return {'FINISHED'}
        except Exception as exc:
            state.last_report = f'Export selhal: {exc}'
            settings.last_report = state.last_report
            self.report({'ERROR'}, state.last_report)
            return {'CANCELLED'}


class LCW_OT_babylon_cleanup(bpy.types.Operator):
    bl_idname = 'lcw.babylon_cleanup'
    bl_label = 'Uklidit'
    bl_description = 'Remove all Babylon temporary datablocks left by an interrupted run'

    @classmethod
    def poll(cls, context):
        return bool(context.scene)

    def execute(self, context):
        try:
            count = cleanup()
            message = f'Odstraněné dočasné datové bloky: {count}.'
            context.scene.lcw_babylon_export.last_report = message
            self.report({'INFO'}, message)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f'Úklid selhal: {exc}')
            return {'CANCELLED'}


class LCW_OT_babylon_bake_phase2(bpy.types.Operator):
    bl_idname = 'lcw.babylon_bake_phase2'
    bl_label = 'Zapéct'
    bl_description = 'SimpleBake baking will be implemented in phase 2'

    @classmethod
    def poll(cls, context):
        return False

    def execute(self, context):
        return {'CANCELLED'}


CLASSES = (LCW_OT_babylon_refresh_materials, LCW_OT_babylon_check, LCW_OT_babylon_export, LCW_OT_babylon_cleanup,
           LCW_OT_babylon_bake_phase2)
