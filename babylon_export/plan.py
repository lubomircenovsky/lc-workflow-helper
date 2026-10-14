"""Read glTF variant RNA into a pure, deterministic bake plan."""
from dataclasses import dataclass
import bpy
from .core import compute_bake_passes


def variants_ui_enabled():
    addon = bpy.context.preferences.addons.get('io_scene_gltf2')
    return bool(addon and addon.preferences.KHR_materials_variants_ui)


def read_scene_variants():
    scene = bpy.data.scenes[0]
    if variants_ui_enabled():
        return [(v.variant_idx, v.name) for v in scene.gltf2_KHR_materials_variants_variants]
    return []


def has_saved_variant_data(collection, *, include_scene=True):
    """Check owner flags without dereferencing unregistered variant RNA.

    Blender 5.2 also hides this RNA storage from ID.keys()/get(). The safe
    signal when glTF's UI is off is is_property_set(), not raw ID dictionaries.
    """
    def is_set(owner, name):
        return name in owner.bl_rna.properties and owner.is_property_set(name)
    if include_scene and is_set(bpy.data.scenes[0], 'gltf2_KHR_materials_variants_variants'):
        return True
    return any(is_set(obj.data, name) for obj in collection.all_objects if obj.type == 'MESH'
               for name in ('gltf2_variant_mesh_data', 'gltf2_variant_default_materials'))


def read_mesh_variants(mesh):
    """Return plain defaults and mapping triples only while RNA is registered."""
    if variants_ui_enabled():
        defaults = {item.material_slot_index: item.default_material
                    for item in mesh.gltf2_variant_default_materials}
        mappings = [(item.material_slot_index, item.material,
                     [reference.variant.variant_idx for reference in item.variants])
                    for item in mesh.gltf2_variant_mesh_data]
    else:
        defaults, mappings = {}, []
    return defaults, mappings


@dataclass
class BakePlan:
    collection: object
    objects: list
    defaults: dict
    variants: dict
    variant_ids: list
    passes: list
    selected_materials: set

    def material_pairs(self):
        return set().union(*(p.to_bake for p in self.passes)) if self.passes else set()

    def all_material_pairs(self):
        assignments = [self.defaults, *(self.variants.get(idx, {}) for idx in self.variant_ids)]
        return {(obj, mat) for mapping in assignments for (obj, _slot), mat in mapping.items() if mat is not None}

    @property
    def baked_objects(self):
        return {obj for obj, _mat in self.material_pairs()}


def build_bake_plan(collection, *, export_variants=None):
    if export_variants is None:
        export_variants = collection.lcw_babylon_export.export_variants
    if not variants_ui_enabled() and has_saved_variant_data(collection, include_scene=export_variants):
        raise ValueError('Enable material variants in the glTF exporter preferences.')
    objects = sorted((o for o in collection.all_objects if o.type == 'MESH'), key=lambda o: o.name)
    defaults, variants = {}, {}
    ids = [idx for idx, _name in read_scene_variants()] if export_variants else []
    for obj in objects:
        defaults.update({(obj, i): slot.material for i, slot in enumerate(obj.material_slots)})
        mesh_defaults, mappings = read_mesh_variants(obj.data)
        for index, material in mesh_defaults.items():
            if 0 <= index < len(obj.material_slots):
                defaults[obj, index] = material
        if not export_variants:
            continue
        for slot, material, variant_ids in mappings:
            for idx in variant_ids:
                variants.setdefault(idx, {}).setdefault((obj, slot), material)
    from .selection import selected_materials
    selected = selected_materials(collection)
    return BakePlan(collection, objects, defaults, variants, ids,
                    compute_bake_passes(defaults, variants, ids, selected_materials=selected), selected)
