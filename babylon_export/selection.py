"""Material inventory and persisted choices. Called by operators, never draw."""
from .plan import has_saved_variant_data, read_mesh_variants, variants_ui_enabled


def has_image_texture(material):
    visited = set()
    def walk(tree):
        if tree is None or tree in visited:
            return False
        visited.add(tree)
        return any(node.type == 'TEX_IMAGE' or (node.type == 'GROUP' and walk(node.node_tree))
                   for node in tree.nodes)
    return bool(material and walk(material.node_tree))


def material_inventory(collection):
    if not variants_ui_enabled() and has_saved_variant_data(collection, include_scene=False):
        raise ValueError('Enable material variants in the glTF exporter preferences.')
    materials, variant_materials = set(), set()
    for obj in collection.all_objects:
        if obj.type != 'MESH':
            continue
        saved_defaults, mappings = read_mesh_variants(obj.data)
        defaults = {index: saved_defaults.get(index, slot.material)
                    for index, slot in enumerate(obj.material_slots)}
        materials.update(mat for mat in defaults.values() if mat is not None)
        for slot, mat, ids in mappings:
            if not ids or not 0 <= slot < len(obj.material_slots):
                continue
            default = defaults[slot]
            if default is not None:
                variant_materials.add(default)
            if mat is not None:
                materials.add(mat)
                variant_materials.add(mat)
    return {mat: (mat in variant_materials or bool(mat.node_tree and any(
                node.type in {'TEX_IMAGE', 'GROUP'} for node in mat.node_tree.nodes)))
            for mat in sorted(materials, key=lambda material: material.name)}


def selected_materials(collection):
    inventory = material_inventory(collection)
    saved = {item.material: item.bake for item in collection.lcw_babylon_export.material_selections}
    return {mat for mat, default in inventory.items() if saved.get(mat, default)}


def refresh_material_list(collection):
    inventory = material_inventory(collection)
    settings = collection.lcw_babylon_export
    items = settings.material_selections
    for index in range(len(items) - 1, -1, -1):
        if items[index].material not in inventory:
            items.remove(index)
    existing = {item.material: item for item in items}
    for mat, default in inventory.items():
        item = existing.get(mat)
        if item is None:
            item = items.add()
            item.material = mat
        if not item.user_override and item.bake != default:
            item.updating_default = True
            try:
                item.bake = default
            finally:
                item.updating_default = False
    settings.material_index = min(settings.material_index, max(0, len(items) - 1))
    return items
