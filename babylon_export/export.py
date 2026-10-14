"""Collection exporter bridge. Originals are never used as export scratch data."""
from pathlib import Path
from uuid import uuid4
import bpy
from .materials import find_baked_material
from .plan import build_bake_plan, read_mesh_variants
from .state import snapshot_state, restore_state
from .validation import validate, selected_exporter, exporter_filepath
from .selection import refresh_material_list


def temporary_datablocks(run_id=None):
    """Enumerate every ID collection, including shape keys/animation datablocks."""
    for prop in bpy.data.bl_rna.properties:
        if prop.type != 'COLLECTION':
            continue
        items = getattr(bpy.data, prop.identifier)
        if not hasattr(items, 'remove'):
            continue
        for item in list(items):
            if hasattr(item, 'get') and item.get('bbe_temp') and (
                    run_id is None or item.get('bbe_run_id') == run_id):
                yield items, item


def cleanup(run_id=None):
    marked = [item for _items, item in temporary_datablocks(run_id)]
    if marked:
        # Blender removes all IDs together, remapping users safely (objects,
        # collections, meshes, keys, materials, images and orphaned helpers).
        bpy.data.batch_remove(ids=marked)
    remaining = list(temporary_datablocks(run_id))
    if remaining:
        raise RuntimeError('Po úklidu zůstala dočasná data Babylon exportu.')
    return len(marked)


def _tag(item, run_id):
    item['bbe_temp'] = True
    item['bbe_run_id'] = run_id


def _export_gltf(props):
    """Small injection seam for integration tests and phase 2 orchestration."""
    return bpy.ops.export_scene.gltf(**props)


def exporter_properties(exporter):
    source = exporter.export_properties
    supported = bpy.ops.export_scene.gltf.get_rna_type().properties
    result = {}
    for prop in source.bl_rna.properties:
        if prop.identifier not in supported or prop.is_readonly or prop.type in {'POINTER', 'COLLECTION'}:
            continue
        value = getattr(source, prop.identifier)
        result[prop.identifier] = tuple(value) if getattr(prop, 'is_array', False) else value
    return result


def expected_baked_names(plan):
    """Names of selected baked materials on slots actually used by faces."""
    pairs = set()
    for obj in plan.objects:
        for index in {polygon.material_index for polygon in obj.data.polygons}:
            materials = [plan.defaults.get((obj, index))]
            materials.extend(plan.variants.get(idx, {}).get((obj, index)) for idx in plan.variant_ids)
            pairs.update((obj, mat) for mat in materials if mat in plan.selected_materials)
    return {material.name for obj, source in pairs
            if (material := find_baked_material(source, obj, plan.collection)) is not None}


def export_collection(collection, settings=None, *, result_info=None):
    settings = settings or collection.lcw_babylon_export
    refresh_material_list(collection)
    problems = validate(collection, for_export=True, settings=settings)
    errors = [i.text for i in problems if i.level == 'ERROR']
    if errors:
        raise ValueError('\n'.join(errors))
    # Remove remnants of an older interrupted run before recording context.
    cleanup()
    plan = build_bake_plan(collection, export_variants=settings.export_variants)
    baked_objects = plan.baked_objects
    state = snapshot_state(plan, include_simplebake=False)
    run_id = uuid4().hex
    first_scene = bpy.data.scenes[0]
    exporter = selected_exporter(collection, settings)
    path = Path(bpy.path.abspath(exporter_filepath(exporter))).with_suffix('.glb')
    props = exporter_properties(exporter)
    prefs = bpy.context.preferences.addons['io_scene_gltf2'].preferences
    variants_enabled = prefs.KHR_materials_variants_ui
    try:
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        temp = bpy.data.collections.new(f'BBE_{run_id}')
        _tag(temp, run_id)
        first_scene.collection.children.link(temp)
        copies, mesh_cache = {}, {}
        sources = list(collection.all_objects)
        # Include ancestors outside the source collection to preserve hierarchy.
        for obj in list(sources):
            parent = obj.parent
            while parent:
                if parent not in sources:
                    sources.append(parent)
                parent = parent.parent
        original_objects = set(collection.all_objects)
        def export_material(obj, source):
            if source in plan.selected_materials:
                return find_baked_material(source, obj, collection)
            return source
        for obj in sources:
            copy = (bpy.data.objects.new(obj.name + '_parent', None)
                    if obj not in original_objects else obj.copy())
            _tag(copy, run_id)
            temp.objects.link(copy)
            copies[obj] = copy
            if copy.type != 'MESH':
                continue
            baked_slots = tuple(export_material(obj, plan.defaults.get((obj, i), slot.material))
                                for i, slot in enumerate(obj.material_slots))
            _defaults, mappings = read_mesh_variants(obj.data)
            variant_materials = tuple(export_material(obj, material)
                                      for _slot, material, _ids in mappings) if settings.export_variants else ()
            if obj in baked_objects:
                uv_name = settings.bake_uv_name
            else:
                render_uv = next((uv for uv in obj.data.uv_layers if uv.active_render), None)
                uv_name = (render_uv or obj.data.uv_layers.active or obj.data.uv_layers[0]).name
            # Per-object textures can require different materials on instances.
            # Share only copies with identical effective slots AND variant maps.
            signature = (obj.data, baked_slots, variant_materials, uv_name)
            if signature not in mesh_cache:
                mesh = obj.data.copy()
                _tag(mesh, run_id)
                if mesh.shape_keys:
                    _tag(mesh.shape_keys, run_id)
                mesh_cache[signature] = mesh
                for uv in list(mesh.uv_layers):
                    if uv.name != uv_name:
                        mesh.uv_layers.remove(uv)
                mesh.uv_layers.active_index = 0
                mesh.uv_layers[0].active_render = True
                for index, mat in enumerate(baked_slots):
                    mesh.materials[index] = mat
                defaults = getattr(mesh, 'gltf2_variant_default_materials', None) if variants_enabled else None
                if defaults is not None:
                    defaults.clear()
                    for index, mat in enumerate(baked_slots):
                        item = defaults.add()
                        item.material_slot_index = index
                        item.default_material = mat
                copied_maps = getattr(mesh, 'gltf2_variant_mesh_data', None) if variants_enabled else None
                if copied_maps is not None:
                    if settings.export_variants:
                        for item, mat in zip(copied_maps, variant_materials):
                            item.material = mat
                    else:
                        copied_maps.clear()
            copy.data = mesh_cache[signature]
            for index, mat in enumerate(baked_slots):
                if copy.material_slots[index].link == 'OBJECT':
                    copy.material_slots[index].material = mat
        for source, copy in copies.items():
            world = source.matrix_world.copy()
            copy.parent = copies.get(source.parent)
            copy.matrix_world = world
            # Constraints and modifiers may point to other exported objects.
            for owner in [*copy.constraints, *copy.modifiers]:
                for prop in owner.bl_rna.properties:
                    if prop.type == 'POINTER' and not prop.is_readonly:
                        value = getattr(owner, prop.identifier)
                        if isinstance(value, bpy.types.Object) and value in copies:
                            setattr(owner, prop.identifier, copies[value])
        if settings.export_variants and plan.variant_ids:
            # The bundled exporter emits only referenced variants. Keep ALL
            # scene variants, including identity variants for this collection,
            # by mapping otherwise-unused ones to one used default baked slot.
            referenced = set()
            anchor = None
            for obj in plan.objects:
                mesh = copies[obj].data
                used_slots = {polygon.material_index for polygon in mesh.polygons}
                for item in mesh.gltf2_variant_mesh_data:
                    if item.material_slot_index in used_slots and item.material:
                        referenced.update(ref.variant.variant_idx for ref in item.variants)
                if anchor is None:
                    anchor = next(((mesh, idx, mesh.materials[idx]) for idx in sorted(used_slots)
                                   if idx < len(mesh.materials) and mesh.materials[idx]), None)
            missing = set(plan.variant_ids) - referenced
            if missing:
                if anchor is None:
                    raise ValueError('Varianty nemají žádný použitý výchozí materiálový slot.')
                mesh, index, material = anchor
                entry = mesh.gltf2_variant_mesh_data.add()
                entry.material_slot_index, entry.material = index, material
                for variant_idx in sorted(missing):
                    entry.variants.add().variant.variant_idx = variant_idx
        props.update(filepath=str(path), collection=temp.name, use_selection=False,
                     use_active_collection=False, export_texcoords=True,
                     export_draco_mesh_compression_enable=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        layer = first_scene.view_layers[0]
        layer.update()
        with bpy.context.temp_override(scene=first_scene, view_layer=layer):
            result = _export_gltf(props)
        if result != {'FINISHED'}:
            raise RuntimeError('Export glTF byl zrušen nebo selhal.')
        if result_info is not None:
            result_info.update(export_settings=props, source_objects=len(plan.objects), path=str(path))
        return path
    finally:
        try:
            cleanup(run_id)
        finally:
            try:
                if prefs.KHR_materials_variants_ui != variants_enabled:
                    prefs.KHR_materials_variants_ui = variants_enabled
            finally:
                restore_state(state)
