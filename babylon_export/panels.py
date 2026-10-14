import bpy
from textwrap import wrap
from .settings import target_collection
from .exporters import selected_exporter, exporter_filepath, MISSING_EXPORT_PATH


class LCW_UL_babylon_materials(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'bake', text='Péct')
        layout.label(text=item.material.name if item.material else 'Chybějící materiál')
        if item.user_override:
            layout.label(text='Vlastní')


class LCW_PT_babylon_export(bpy.types.Panel):
    bl_label = 'Babylon Bake & Export'
    bl_idname = 'LCW_PT_babylon_export'
    bl_parent_id = 'LCW_PT_project_specific_tools'
    bl_order = 1
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'LC Workflow'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        state = context.scene.lcw_babylon_export
        layout.prop(state, 'target_collection', text='Kolekce')
        collection = target_collection(context)
        layout.label(text=f'Cíl: {collection.name}')
        settings = collection.lcw_babylon_export
        for name in ('simplebake_preset', 'bake_uv_name', 'texture_dir', 'baked_suffix',
                     'exporter_name', 'export_variants'):
            layout.prop(settings, name)
        exporter = selected_exporter(collection, settings)
        if exporter is not None and not exporter_filepath(exporter):
            for line in wrap(MISSING_EXPORT_PATH, width=48):
                layout.label(text=line, icon='ERROR')
        layout.operator('lcw.babylon_refresh_materials', text='Obnovit seznam materiálů')
        layout.template_list('LCW_UL_babylon_materials', '', settings, 'material_selections',
                             settings, 'material_index', rows=5)
        row = layout.row(align=True)
        row.operator('lcw.babylon_check', text='Kontrola')
        row.operator('lcw.babylon_export', text='Exportovat')
        row.operator('lcw.babylon_cleanup', text='Uklidit')
        row = layout.row(align=True)
        row.enabled = False
        row.operator('lcw.babylon_bake_phase2', text='Zapéct')
        row.operator('lcw.babylon_bake_phase2', text='Zapéct a exportovat')
        layout.label(text='Pečení přes SimpleBake – fáze 2', icon='INFO')
        box = layout.box()
        for line in wrap(state.last_report[:180], width=48):
            box.label(text=line)
        # Bound cached-report work; no scanning of objects or material graphs.
        for index in range(min(len(state.issues), 6)):
            item = state.issues[index]
            for line in wrap(item.text[:180], width=48):
                box.label(text=line, icon='ERROR' if item.level == 'ERROR' else 'INFO')
        if len(state.issues) > 6:
            box.label(text=f'Dalších {len(state.issues) - 6} problémů.')
