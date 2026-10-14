"""Read-only preflight. Bake-only dependencies never block existing bake export."""
from collections import Counter
import bpy
from .core import Issue, safe_batch_name
from .materials import find_baked_material
from .plan import (build_bake_plan, has_saved_variant_data, read_mesh_variants,
                   read_scene_variants, variants_ui_enabled)
from .simplebake_adapter import availability, bake_properties
from .exporters import selected_exporter, exporter_filepath, MISSING_EXPORT_PATH
from .selection import has_image_texture


def has_principled(material):
    if not material or not material.use_nodes or not material.node_tree:
        return False
    def upstream(socket, frames=(), visited=frozenset()):
        if len(visited) > 100:
            return False
        for link in socket.links:
            node, output = link.from_node, link.from_socket
            key = (node.as_pointer(), output.identifier, tuple(n.as_pointer() for n in frames))
            if key in visited:
                continue
            trail = visited | {key}
            if node.type == 'BSDF_PRINCIPLED':
                return True
            if node.type == 'GROUP' and node.node_tree:
                index = list(node.outputs).index(output)
                for inner in node.node_tree.nodes:
                    if inner.type == 'GROUP_OUTPUT' and inner.is_active_output and index < len(inner.inputs):
                        if upstream(inner.inputs[index], (*frames, node), trail):
                            return True
            elif node.type == 'GROUP_INPUT' and frames:
                index = list(node.outputs).index(output)
                if index < len(frames[-1].inputs) and upstream(frames[-1].inputs[index], frames[:-1], trail):
                    return True
            else:
                for value in node.inputs:
                    if value.type == 'SHADER' or node.type == 'REROUTE':
                        if upstream(value, frames, trail):
                            return True
        return False
    return any(upstream(node.inputs['Surface']) for node in material.node_tree.nodes
               if node.type == 'OUTPUT_MATERIAL' and node.is_active_output)


def validate(collection, *, for_export=False, settings=None):
    settings = settings or collection.lcw_babylon_export
    issues = []
    def add(level, text, obj=None, mat=None):
        issues.append(Issue(level, text, obj.name if obj else '', mat.name if mat else ''))
    if collection.get('bbe_temp'):
        add('ERROR', 'The target collection is temporary; remove it with Clean Up first.')
    exporter = selected_exporter(collection, settings)
    if not exporter:
        add('ERROR', 'The collection has no glTF Collection Exporter selected.')
    else:
        path = exporter_filepath(exporter)
        if not path:
            add('ERROR', MISSING_EXPORT_PATH)
        elif path.startswith('//') and not bpy.data.filepath:
            add('ERROR', 'The file is not saved; a relative export path cannot be resolved.')
        if exporter.export_properties.export_format != 'GLB':
            add('ERROR', 'The exporter must use the GLB format.')
        if exporter.export_properties.export_materials != 'EXPORT':
            add('ERROR', 'The exporter must export materials (Materials: Export).')
        if exporter.export_properties.export_use_gltfpack:
            add('WARNING', 'gltfpack is enabled; the file may already be compressed.')
    if not settings.bake_uv_name:
        add('ERROR', 'The bake UV name must not be empty.')
    if not settings.baked_suffix:
        add('ERROR', 'The baked material suffix must not be empty.')
    if not for_export:
        module, version = availability()
        if not module:
            add('ERROR', 'SimpleBake is not installed or enabled; baking is unavailable')
        else:
            if version[:2] != (2, 9):
                add('ERROR', f'Unsupported SimpleBake version {version}; 2.9.x is expected.')
            sbp = bake_properties(bpy.context.scene)
            presets = getattr(sbp, 'local_presets_list', ())
            if settings.simplebake_preset and settings.simplebake_preset not in {p.name for p in presets}:
                add('ERROR', 'The selected SimpleBake preset does not exist.')
        if not bpy.data.filepath:
            add('ERROR', 'Save the Blender file before baking.')
        if settings.bake_uv_name != 'SimpleBake':
            add('WARNING', 'SimpleBake looks for a UV map named SimpleBake; another name needs adapter support.')
        if not settings.texture_dir:
            add('ERROR', 'The texture folder is not set.')
    if not variants_ui_enabled() and has_saved_variant_data(collection, include_scene=settings.export_variants):
        # The exporter leaves RNA pointers to unregistered classes behind.
        # Stop before inspecting those collections: accessing them can crash
        # Blender. Enabling the UI restores their RNA, without changing data.
        add('ERROR', 'Enable material variants in the glTF exporter preferences.')
        return issues
    plan = build_bake_plan(collection, export_variants=settings.export_variants)
    baked_objects = plan.baked_objects
    if not plan.objects:
        add('ERROR', 'The collection contains no mesh object.')
    mesh_variants = {o: read_mesh_variants(o.data) for o in plan.objects}
    has_variant_data = any(defaults or mappings for defaults, mappings in mesh_variants.values())
    if (has_variant_data or plan.variant_ids) and not variants_ui_enabled():
        add('ERROR', 'Enable material variants in the glTF exporter preferences.')
    scene_variants = read_scene_variants()
    if settings.export_variants and any(idx != i for i, (idx, _name) in enumerate(scene_variants)):
        add('ERROR', 'glTF variant indices do not match their order in the first scene.')
    for obj in plan.objects:
        if obj in baked_objects and settings.bake_uv_name not in obj.data.uv_layers:
            add('ERROR', f'Object "{obj.name}" has no UV map "{settings.bake_uv_name}".', obj)
        elif for_export and obj not in baked_objects and not obj.data.uv_layers:
            add('ERROR', f'Object "{obj.name}" has no UV map to export.', obj)
        if not obj.material_slots or all(s.material is None for s in obj.material_slots):
            add('WARNING', f'Object "{obj.name}" has no material.', obj)
        if obj.modifiers:
            add('WARNING', f'Object "{obj.name}" has unapplied modifiers; export follows export_apply.', obj)
        if not for_export and obj in baked_objects and safe_batch_name(obj.name) != obj.name:
            add('ERROR', f'Object name "{obj.name}" contains characters not allowed in file names.', obj)
        mesh_defaults, mappings = mesh_variants[obj]
        for index in mesh_defaults:
            if not 0 <= index < len(obj.material_slots):
                add('ERROR', f'Object "{obj.name}" has an invalid default material slot.', obj)
        if not settings.export_variants:
            continue
        seen = {}
        for slot, material, variant_ids in mappings:
            if not 0 <= slot < len(obj.material_slots):
                add('ERROR', f'Object "{obj.name}" has an invalid variant slot.', obj)
            for idx in variant_ids:
                key = (slot, idx)
                if idx not in plan.variant_ids:
                    add('ERROR', f'Object "{obj.name}" references missing variant {idx}.', obj)
                if key in seen and seen[key] != material:
                    add('ERROR', f'Variant {idx} has different materials for slot {key[0]} of object "{obj.name}".', obj)
                seen[key] = material
    if settings.export_variants and plan.variant_ids:
        referenced = {idx for idx, assignments in plan.variants.items() if assignments}
        missing = set(plan.variant_ids) - referenced
        if missing:
            add('WARNING', f'{len(missing)} variant(s) change no material in this collection; they export with the default state.')
    pairs = plan.material_pairs()
    counts = Counter(mat for _obj, mat in pairs)
    for mat, count in counts.items():
        if count > 1:
            add('WARNING', f'Material "{mat.name}" is shared by {count} objects; each gets its own texture set.', mat=mat)
        if not has_principled(mat):
            add('ERROR', f'Material "{mat.name}" has no Principled BSDF connected to the output.', mat=mat)
        if not for_export and safe_batch_name(mat.name) != mat.name:
            add('ERROR', f'Material name "{mat.name}" contains characters not allowed in file names.', mat=mat)
    unbaked_pairs = plan.all_material_pairs() - pairs
    for mat in sorted({mat for _obj, mat in unbaked_pairs}, key=lambda mat: mat.name):
        if not has_principled(mat):
            add('WARNING', f'Unbaked material "{mat.name}" does not end in a Principled BSDF; glTF may not export it faithfully.', mat=mat)
    for obj, mat in sorted(unbaked_pairs, key=lambda pair: (pair[0].name, pair[1].name)):
        if obj in baked_objects and has_image_texture(mat):
            add('WARNING', f'Unbaked material "{mat.name}" on object "{obj.name}" uses an image texture; in the export it gets UV map "{settings.bake_uv_name}".', obj, mat)
    if for_export:
        for obj, mat in sorted(pairs, key=lambda pair: (pair[0].name, pair[1].name)):
            baked = find_baked_material(mat, obj, collection)
            if baked is None:
                add('ERROR', f'Object "{obj.name}": the baked material for "{mat.name}" is missing.', obj, mat)
            elif not baked.name.endswith(settings.baked_suffix):
                add('ERROR', f'Baked material "{baked.name}" does not end with "{settings.baked_suffix}".', obj, mat)
    return issues
