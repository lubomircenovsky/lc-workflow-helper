import bpy
from .core import safe_batch_name
from .exporters import is_gltf_exporter, exporter_filepath

# Blender retains pointers to strings returned by dynamic enum callbacks.
_exporter_items = {}


def texture_dir_get(self):
    collection_name = self.id_data.name if self.id_data else 'collection'
    return self.get('texture_dir', f'//bakes/{safe_batch_name(collection_name)}/')


def texture_dir_set(self, value):
    self['texture_dir'] = value


def target_collection(context):
    state = context.scene.lcw_babylon_export
    return state.target_collection or context.view_layer.active_layer_collection.collection


def exporter_items(self, context):
    collection = self.id_data
    items = []
    for index, exporter in enumerate(collection.exporters):
        if is_gltf_exporter(exporter):
            label = f'{exporter.name or "glTF"} ({index + 1})'
            path = exporter_filepath(exporter)
            if path:
                label += f' – {path}'
            items.append((str(index), label, 'Collection glTF exporter', len(items)))
    _exporter_items[collection.as_pointer()] = items or [('NONE', 'No glTF exporter', '', 0)]
    return _exporter_items[collection.as_pointer()]


def material_choice_update(self, context):
    if not self.updating_default:
        self.user_override = True


class LCW_PG_babylon_material(bpy.types.PropertyGroup):
    material: bpy.props.PointerProperty(type=bpy.types.Material)
    bake: bpy.props.BoolProperty(name='Bake', update=material_choice_update)
    user_override: bpy.props.BoolProperty(options={'HIDDEN'})
    updating_default: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'})


class LCW_PG_babylon_settings(bpy.types.PropertyGroup):
    simplebake_preset: bpy.props.StringProperty(name="SimpleBake Preset (optional)",
                                             description="Optional local preset; empty uses current SimpleBake settings")
    bake_uv_name: bpy.props.StringProperty(name="Bake UV", default="SimpleBake")
    texture_dir: bpy.props.StringProperty(name="Texture Folder", subtype='DIR_PATH',
                                        get=texture_dir_get, set=texture_dir_set)
    baked_suffix: bpy.props.StringProperty(name="Baked Suffix", default="_baked")
    exporter_name: bpy.props.EnumProperty(name="Collection Exporter", items=exporter_items)
    export_variants: bpy.props.BoolProperty(name="Export Variants", default=True)
    last_report: bpy.props.StringProperty()
    material_selections: bpy.props.CollectionProperty(type=LCW_PG_babylon_material)
    material_index: bpy.props.IntProperty()


class LCW_PG_babylon_issue(bpy.types.PropertyGroup):
    level: bpy.props.StringProperty()
    text: bpy.props.StringProperty()


class LCW_PG_babylon_state(bpy.types.PropertyGroup):
    target_collection: bpy.props.PointerProperty(name="Target Collection", type=bpy.types.Collection)
    last_report: bpy.props.StringProperty(default="Not checked yet.")
    issues: bpy.props.CollectionProperty(type=LCW_PG_babylon_issue)
    last_operation: bpy.props.EnumProperty(
        name='Last Operation', default='UNKNOWN', items=[
            ('UNKNOWN', 'Unknown', 'No typed operation result is available'),
            ('CHECK', 'Check', 'Bake and export checks'),
            ('BAKE', 'Bake', 'Bake materials'),
            ('BAKE_EXPORT', 'Bake & Export', 'Bake materials and export GLB'),
            ('EXPORT', 'Export', 'Export and verify GLB'),
            ('CLEANUP', 'Clean Up', 'Remove temporary datablocks'),
        ])
    last_outcome: bpy.props.EnumProperty(
        name='Last Outcome', default='UNKNOWN', items=[
            ('UNKNOWN', 'Unknown', 'No typed result is available'),
            ('OK', 'OK', 'The last operation completed successfully'),
            ('WARNING', 'Warning', 'The last operation reported warnings'),
            ('ERROR', 'Error', 'The last operation failed or reported errors'),
            ('CANCELLED', 'Cancelled', 'The last operation was cancelled'),
        ])
    report_collection: bpy.props.PointerProperty(name='Report Collection', type=bpy.types.Collection)
    # The scene's master collection is embedded data and cannot be stored in a
    # pointer property, so a report about it is flagged instead.
    report_scene_collection: bpy.props.BoolProperty(name='Report Scene Collection', default=False)


CLASSES = (LCW_PG_babylon_material, LCW_PG_babylon_settings, LCW_PG_babylon_issue, LCW_PG_babylon_state)


def register_properties():
    bpy.types.Collection.lcw_babylon_export = bpy.props.PointerProperty(type=LCW_PG_babylon_settings)
    bpy.types.Scene.lcw_babylon_export = bpy.props.PointerProperty(type=LCW_PG_babylon_state)


def unregister_properties():
    for owner in (bpy.types.Scene, bpy.types.Collection):
        if hasattr(owner, 'lcw_babylon_export'):
            delattr(owner, 'lcw_babylon_export')
    _exporter_items.clear()
