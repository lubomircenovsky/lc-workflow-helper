"""Pure bake planning, naming and GLB inspection (no Blender imports)."""
from dataclasses import dataclass
import json
from pathlib import Path
import re
import struct


@dataclass(frozen=True)
class Issue:
    level: str
    text: str
    object: str = ""
    material: str = ""


@dataclass
class BakePass:
    variant_idx: int | None
    assignments: dict
    to_bake: set

    @property
    def objects(self):
        return {obj for obj, _material in self.to_bake}


def compute_bake_passes(defaults, variants, variant_ids, *, selected_materials=None):
    """Inputs use hashable object/material IDs; variants map ID -> slot overrides.

    Assignments include ALL slots of participating objects, including fallbacks
    to defaults. Only objects with a previously unbaked pair participate.
    """
    seen = set()
    result = []
    for idx in [None, *variant_ids]:
        assignments = dict(defaults)
        if idx is not None:
            assignments.update(variants.get(idx, {}))
        pairs = {(obj, mat) for (obj, _slot), mat in assignments.items() if mat is not None
                 and (selected_materials is None or mat in selected_materials)}
        pending = pairs - seen
        objects = {obj for obj, _mat in pending}
        if pending:
            result.append(BakePass(idx, {key: mat for key, mat in assignments.items()
                                         if key[0] in objects}, pending))
        seen.update(pairs)
    return result


def baked_material_name(material, obj, suffix="_baked", shared=False):
    return f"{material}__{obj}{suffix}" if shared else f"{material}{suffix}"


def safe_batch_name(collection):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', collection).strip(' .') or 'Bake'


def inspect_glb(data, *, expected_variants=None, baked_suffix="_baked", require_variants=False,
                expected_baked_materials=None):
    """Check GLB framing and Babylon invariants; return an inspectable report."""
    errors = []
    if len(data) < 20:
        raise ValueError("GLB je příliš krátký.")
    magic, version, length = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or length != len(data):
        raise ValueError("Neplatná hlavička nebo délka GLB.")
    offset, chunks = 12, []
    while offset < length:
        if offset + 8 > length:
            raise ValueError("Neúplná hlavička chunku GLB.")
        size, kind = struct.unpack_from('<II', data, offset)
        offset += 8
        if size % 4 or offset + size > length:
            raise ValueError("Neplatná délka chunku GLB.")
        chunks.append((kind, data[offset:offset + size]))
        offset += size
    if not chunks or chunks[0][0] != 0x4E4F534A or sum(k == 0x4E4F534A for k, _ in chunks) != 1:
        raise ValueError("GLB musí začínat jedním JSON chunkem.")
    document = json.loads(chunks[0][1].decode('utf-8').rstrip(' \x00'))
    materials = document.get('materials', [])
    expected_names = set(expected_baked_materials or ())
    missing = expected_names - {mat.get('name', '') for mat in materials}
    if missing:
        errors.append(f'GLB neobsahuje očekávané zapečené materiály: {sorted(missing)}.')
    primitives = [p for mesh in document.get('meshes', []) for p in mesh.get('primitives', [])]
    used = set(document.get('extensionsUsed', [])) | set(document.get('extensionsRequired', []))
    if 'KHR_draco_mesh_compression' in used:
        errors.append("GLB obsahuje kompresi Draco.")
    variants = document.get('extensions', {}).get('KHR_materials_variants', {}).get('variants', [])
    if require_variants and (not variants or 'KHR_materials_variants' not in used):
        errors.append("GLB neobsahuje požadované materiálové varianty.")
    if expected_variants is not None and len(variants) != expected_variants:
        errors.append(f"Počet variant {len(variants)} neodpovídá scéně ({expected_variants}).")
    mappings_count = 0
    def check_material(index):
        if not isinstance(index, int) or not 0 <= index < len(materials):
            errors.append("GLB odkazuje na neplatný materiál.")
        elif materials[index].get('name', '') in expected_names and not materials[index].get('name', '').endswith(baked_suffix):
            errors.append(f"Materiál {materials[index].get('name', index)} nemá příponu {baked_suffix}.")
    for primitive in primitives:
        texcoords = {key for key in primitive.get('attributes', {}) if key.startswith('TEXCOORD_')}
        if texcoords != {'TEXCOORD_0'}:
            errors.append(f"UV atributy musí být pouze TEXCOORD_0, nalezeno: {sorted(texcoords)}.")
        extensions = primitive.get('extensions', {})
        if 'KHR_draco_mesh_compression' in extensions:
            errors.append("Primitiva obsahuje kompresi Draco.")
        if 'material' in primitive:
            check_material(primitive['material'])
        for mapping in extensions.get('KHR_materials_variants', {}).get('mappings', []):
            mappings_count += 1
            check_material(mapping.get('material'))
            if not mapping.get('variants') or any(not isinstance(v, int) or not 0 <= v < len(variants)
                                                  for v in mapping['variants']):
                errors.append("Neplatný odkaz na materiálovou variantu.")
    if require_variants and not mappings_count:
        errors.append("GLB nemá mapování materiálových variant.")
    bin_size = sum(len(chunk) for kind, chunk in chunks if kind == 0x004E4942)
    views = document.get('bufferViews', [])
    images = document.get('images', [])
    for img in images:
        view = img.get('bufferView')
        if not isinstance(view, int) or not 0 <= view < len(views):
            errors.append("Obrázek není vložený do GLB.")
            continue
        info = views[view]
        if (info.get('buffer', 0) != 0 or info.get('byteLength', 0) <= 0 or
                info.get('byteOffset', 0) < 0 or
                info.get('byteOffset', 0) + info.get('byteLength', 0) > bin_size):
            errors.append("Obrázek odkazuje mimo binární data GLB.")
        if img.get('mimeType') not in {'image/png', 'image/jpeg', 'image/webp', 'image/ktx2'}:
            errors.append("Obrázek má chybějící nebo neznámý MIME typ.")
    if not primitives:
        errors.append("GLB neobsahuje žádnou mesh primitivu.")
    if not images and expected_names:
        errors.append("GLB neobsahuje zapečené obrázky.")
    return dict(ok=not errors, errors=errors, bytes=len(data), objects=len(document.get('nodes', [])),
                primitives=len(primitives), materials=len(materials), images=len(images),
                image_mimes=[i.get('mimeType') for i in images], variants=len(variants),
                mappings=mappings_count, document=document)


def verify_glb(path, **kwargs):
    return inspect_glb(Path(path).read_bytes(), **kwargs)
