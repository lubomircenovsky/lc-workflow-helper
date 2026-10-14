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
        add('ERROR', 'Cílová kolekce je dočasná; nejprve ji odstraňte tlačítkem Uklidit.')
    exporter = selected_exporter(collection, settings)
    if not exporter:
        add('ERROR', 'Kolekce nemá vybraný exportér glTF 2.0.')
    else:
        path = exporter_filepath(exporter)
        if not path:
            add('ERROR', MISSING_EXPORT_PATH)
        elif path.startswith('//') and not bpy.data.filepath:
            add('ERROR', 'Soubor není uložený; relativní cesta exportu není dostupná.')
        if exporter.export_properties.export_format != 'GLB':
            add('ERROR', 'Exportér musí používat formát GLB.')
        if exporter.export_properties.export_materials != 'EXPORT':
            add('ERROR', 'Exportér musí exportovat materiály (volba Export).')
        if exporter.export_properties.export_use_gltfpack:
            add('WARNING', 'gltfpack je zapnutý; soubor může být již komprimovaný.')
    if not settings.bake_uv_name:
        add('ERROR', 'Název UV pro pečení nesmí být prázdný.')
    if not settings.baked_suffix:
        add('ERROR', 'Přípona zapečených materiálů nesmí být prázdná.')
    if not for_export:
        module, version = availability()
        if not module:
            add('ERROR', 'SimpleBake není nainstalovaný nebo zapnutý – pečení nebude dostupné')
        else:
            if version[:2] != (2, 9):
                add('ERROR', f'SimpleBake má nepodporovanou verzi {version}; očekává se 2.9.x.')
            sbp = bake_properties(bpy.context.scene)
            presets = getattr(sbp, 'local_presets_list', ())
            if settings.simplebake_preset and settings.simplebake_preset not in {p.name for p in presets}:
                add('ERROR', 'Vybraný preset SimpleBake neexistuje.')
        if not bpy.data.filepath:
            add('ERROR', 'Před pečením uložte soubor Blenderu.')
        if settings.bake_uv_name != 'SimpleBake':
            add('WARNING', 'SimpleBake hledá UV jménem SimpleBake; zvolený název vyžaduje adaptér.')
        if not settings.texture_dir:
            add('ERROR', 'Složka textur není nastavená.')
    if not variants_ui_enabled() and has_saved_variant_data(collection, include_scene=settings.export_variants):
        # The exporter leaves RNA pointers to unregistered classes behind.
        # Stop before inspecting those collections: accessing them can crash
        # Blender. Enabling the UI restores their RNA, without changing data.
        add('ERROR', 'Zapněte materiálové varianty v nastavení exportéru glTF.')
        return issues
    plan = build_bake_plan(collection, export_variants=settings.export_variants)
    baked_objects = plan.baked_objects
    if not plan.objects:
        add('ERROR', 'Kolekce neobsahuje žádný mesh objekt.')
    mesh_variants = {o: read_mesh_variants(o.data) for o in plan.objects}
    has_variant_data = any(defaults or mappings for defaults, mappings in mesh_variants.values())
    if (has_variant_data or plan.variant_ids) and not variants_ui_enabled():
        add('ERROR', 'Zapněte materiálové varianty v nastavení exportéru glTF.')
    scene_variants = read_scene_variants()
    if settings.export_variants and any(idx != i for i, (idx, _name) in enumerate(scene_variants)):
        add('ERROR', 'Indexy glTF variant neodpovídají pořadí v první scéně.')
    for obj in plan.objects:
        if obj in baked_objects and settings.bake_uv_name not in obj.data.uv_layers:
            add('ERROR', f'Objekt „{obj.name}“ nemá UV „{settings.bake_uv_name}“.', obj)
        elif for_export and obj not in baked_objects and not obj.data.uv_layers:
            add('ERROR', f'Objekt „{obj.name}“ nemá žádnou UV vrstvu pro export.', obj)
        if not obj.material_slots or all(s.material is None for s in obj.material_slots):
            add('WARNING', f'Objekt „{obj.name}“ nemá materiál.', obj)
        if obj.modifiers:
            add('WARNING', f'Objekt „{obj.name}“ má neaplikované modifikátory; export respektuje export_apply.', obj)
        if not for_export and obj in baked_objects and safe_batch_name(obj.name) != obj.name:
            add('ERROR', f'Název objektu „{obj.name}“ obsahuje znaky nevhodné pro soubory.', obj)
        mesh_defaults, mappings = mesh_variants[obj]
        for index in mesh_defaults:
            if not 0 <= index < len(obj.material_slots):
                add('ERROR', f'Objekt „{obj.name}“ má neplatný výchozí materiálový slot.', obj)
        if not settings.export_variants:
            continue
        seen = {}
        for slot, material, variant_ids in mappings:
            if not 0 <= slot < len(obj.material_slots):
                add('ERROR', f'Objekt „{obj.name}“ má neplatný slot varianty.', obj)
            for idx in variant_ids:
                key = (slot, idx)
                if idx not in plan.variant_ids:
                    add('ERROR', f'Objekt „{obj.name}“ odkazuje na neexistující variantu {idx}.', obj)
                if key in seen and seen[key] != material:
                    add('ERROR', f'Varianta {idx} má různé materiály pro slot {key[0]} objektu „{obj.name}“.', obj)
                seen[key] = material
    if settings.export_variants and plan.variant_ids:
        referenced = {idx for idx, assignments in plan.variants.items() if assignments}
        missing = set(plan.variant_ids) - referenced
        if missing:
            add('WARNING', f'{len(missing)} variant v kolekci nemění materiál; exportují se s výchozím stavem.')
    pairs = plan.material_pairs()
    counts = Counter(mat for _obj, mat in pairs)
    for mat, count in counts.items():
        if count > 1:
            add('WARNING', f'Materiál „{mat.name}“ sdílí {count} objektů; každý má vlastní sadu textur.', mat=mat)
        if not has_principled(mat):
            add('ERROR', f'Materiál „{mat.name}“ nemá Principled BSDF napojený na výstup.', mat=mat)
        if not for_export and safe_batch_name(mat.name) != mat.name:
            add('ERROR', f'Název materiálu „{mat.name}“ obsahuje znaky nevhodné pro soubory.', mat=mat)
    unbaked_pairs = plan.all_material_pairs() - pairs
    for mat in sorted({mat for _obj, mat in unbaked_pairs}, key=lambda mat: mat.name):
        if not has_principled(mat):
            add('WARNING', f'Nepečený materiál „{mat.name}“ nekončí v Principled BSDF; glTF jej nemusí exportovat věrně.', mat=mat)
    for obj, mat in sorted(unbaked_pairs, key=lambda pair: (pair[0].name, pair[1].name)):
        if obj in baked_objects and has_image_texture(mat):
            add('WARNING', f'Nepečený materiál „{mat.name}“ na objektu „{obj.name}“ používá texturu; v exportu dostane UV „{settings.bake_uv_name}“.', obj, mat)
    if for_export:
        for obj, mat in sorted(pairs, key=lambda pair: (pair[0].name, pair[1].name)):
            baked = find_baked_material(mat, obj, collection)
            if baked is None:
                add('ERROR', f'Objekt „{obj.name}“: chybí zapečený materiál pro „{mat.name}“.', obj, mat)
            elif not baked.name.endswith(settings.baked_suffix):
                add('ERROR', f'Zapečený materiál „{baked.name}“ nemá příponu „{settings.baked_suffix}“.', obj, mat)
    return issues
