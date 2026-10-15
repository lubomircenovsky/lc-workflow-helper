import bpy
from textwrap import wrap
from ..icons import draw_header_icon, status_icon
from .reporting import last_operation_status
from .settings import target_collection
from .bake import active_job
from .simplebake_adapter import settings_summary
from .exporters import selected_exporter, exporter_filepath, MISSING_EXPORT_PATH


class LCW_UL_babylon_materials(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'bake', text='Bake')
        layout.label(text=item.material.name if item.material else 'Missing material')
        if item.user_override:
            layout.label(text='Custom')


class LCW_PT_babylon_export(bpy.types.Panel):
    bl_label = 'Babylon Bake & Export'
    bl_idname = 'LCW_PT_babylon_export'
    bl_parent_id = 'LCW_PT_project_specific_tools'
    bl_order = 1
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'LC Workflow'
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        draw_header_icon(self.layout, 'babylon_export')

    def draw(self, context):
        layout = self.layout
        state = context.scene.lcw_babylon_export
        layout.prop(state, 'target_collection', text='Collection')
        collection = target_collection(context)
        if state.target_collection is None:
            # Only the fallback needs spelling out; a picked collection is already shown.
            layout.label(text=f'Active collection: {collection.name}', icon='OUTLINER_COLLECTION')
        settings = collection.lcw_babylon_export
        layout.label(text='Bake Settings', icon='RENDER_STILL')
        for name in ('simplebake_preset', 'bake_uv_name', 'texture_dir', 'baked_suffix'):
            layout.prop(settings, name)
        layout.label(text='Export Settings', icon='EXPORT')
        for name in ('exporter_name', 'export_variants'):
            layout.prop(settings, name)
        exporter = selected_exporter(collection, settings)
        if exporter is not None and not exporter_filepath(exporter):
            for line in wrap(MISSING_EXPORT_PATH, width=48):
                layout.label(text=line, **status_icon('error'))
        layout.label(text='Materials to Bake', icon='MATERIAL')
        layout.operator('lcw.babylon_refresh_materials', text='Refresh Material List')
        layout.template_list('LCW_UL_babylon_materials', '', settings, 'material_selections',
                             settings, 'material_index', rows=5)
        job = active_job()
        sbp = getattr(context.scene, 'SimpleBake_Props', None)  # cheap; no add-on scan in draw()
        if sbp is not None and job is None:
            layout.label(text=f'SimpleBake: {settings_summary(sbp)}', icon='TEXTURE')
        layout.separator(type='LINE')
        if job is not None:
            box = layout.box()
            box.label(text='Baking with SimpleBake...', icon='RENDER_STILL')
            if job.total_passes:
                box.progress(factor=max(0, job.pass_index) / job.total_passes,
                             text=f'Pass {max(1, job.pass_index + 1)}/{job.total_passes}', type='BAR')
            warning = box.column(align=True)
            warning.alert = True
            warning.label(text='Do not edit or save the file,', **status_icon('warning'))
            warning.label(text='switch scenes or press Esc until it finishes.')
            box.operator('lcw.babylon_bake_cancel', text='Cancel After This Pass', icon='CANCEL')
        else:
            row = layout.row(align=True)
            row.scale_y = 1.3
            row.operator('lcw.babylon_bake', text='Bake', icon='RENDER_STILL').export_after = False
            row.operator('lcw.babylon_bake', text='Bake & Export', icon='EXPORT').export_after = True
        row = layout.row(align=True)
        row.enabled = job is None
        row.operator('lcw.babylon_check', text='Check', icon='VIEWZOOM')
        row.operator('lcw.babylon_export', text='Export', icon='EXPORT')
        row.operator('lcw.babylon_cleanup', text='Clean Up', icon='TRASH')
        box = layout.box()
        box.label(text='Current Operation' if job is not None else 'Last Operation',
                  icon='TIME' if job is not None else 'TEXT')
        # While baking, progress comes from Python state: writing it into the
        # scene would tag the depsgraph while Blender's bake thread runs.
        if job is not None:
            status = 'cancelled' if job.cancel_requested else 'running'
            text = 'Cancelling after this pass' if job.cancel_requested else job.progress_text()
            lines = wrap(text[:400], width=48)
            box.label(text=lines[0] if lines else '', **status_icon(status))
            for line in lines[1:]:
                box.label(text=line)
            if job.cancel_requested:
                for line in wrap(job.progress_text()[:400], width=48):
                    box.label(text=line)
            return  # Cached issues belong to the previous operation, not this bake.
        status, text = last_operation_status(state, collection)
        box.label(text=text, **status_icon(status))
        for line in wrap(state.last_report[:400], width=48):
            box.label(text=line)
        # Bound cached-report work; no scanning of objects or material graphs.
        for index in range(min(len(state.issues), 6)):
            item = state.issues[index]
            line_row = box.row()
            line_row.alert = item.level == 'ERROR'
            column = line_row.column(align=True)
            for line in wrap(item.text[:180], width=48):
                severity = {'ERROR': 'error', 'WARNING': 'warning'}.get(item.level, 'info')
                column.label(text=line, **status_icon(severity))
        if len(state.issues) > 6:
            box.label(text=f'{len(state.issues) - 6} more issue(s).')
