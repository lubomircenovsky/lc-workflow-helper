"""Build reusable, exporter-compatible materials from adapter image maps."""
import bpy
from .core import baked_material_name
from .plan import build_bake_plan

CHANNELS = {'base_color', 'alpha', 'metallic', 'roughness', 'normal', 'emission', 'ao'}


def find_baked_material(src_mat, obj, collection):
    return next((mat for mat in bpy.data.materials
                 if mat.get('bbe_source_material') == src_mat and mat.get('bbe_object') == obj
                 and mat.get('bbe_collection') == collection), None)


def build_baked_material(src_mat, obj, images, settings):
    unknown = set(images) - CHANNELS
    if unknown:
        raise ValueError(f"Unknown channels: {sorted(unknown)}")
    if not images:
        raise ValueError("Baked images are missing.")
    collection = settings.id_data
    mat = find_baked_material(src_mat, obj, collection)
    shared = sum(source == src_mat for _obj, source in build_bake_plan(collection).material_pairs()) > 1
    name = baked_material_name(src_mat.name, obj.name, settings.baked_suffix, shared)
    if mat is None:
        # Keep the suffix last even when Blender's normal .001 name would collide.
        candidate, index = name, 1
        while candidate in bpy.data.materials:
            stem = name[:-len(settings.baked_suffix)] if settings.baked_suffix else name
            candidate = f"{stem}__{index}{settings.baked_suffix}"
            index += 1
        mat = bpy.data.materials.new(candidate)
    mat.use_nodes = True
    mat.use_fake_user = True
    mat['bbe_source_material'] = src_mat
    mat['bbe_object'] = obj
    mat['bbe_collection'] = collection
    mat['bbe_variant_independent'] = True
    tree = mat.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    output.location = (600, 0)
    bsdf = tree.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (300, 0)
    tree.links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    uv = tree.nodes.new('ShaderNodeUVMap')
    uv.uv_map = settings.bake_uv_name
    uv.location = (-800, 0)
    textures = {}
    for index, (channel, image) in enumerate(images.items()):
        image.colorspace_settings.name = 'sRGB' if channel in {'base_color', 'emission'} else 'Non-Color'
        image.use_fake_user = True
        node = tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        node.label = channel
        node.location = (-550, -index * 230)
        tree.links.new(uv.outputs['UV'], node.inputs['Vector'])
        textures[channel] = node
    sockets = {'base_color': 'Base Color', 'alpha': 'Alpha', 'metallic': 'Metallic',
               'roughness': 'Roughness', 'emission': 'Emission Color'}
    for channel, socket in sockets.items():
        if channel in textures:
            tree.links.new(textures[channel].outputs['Color'], bsdf.inputs[socket])
    if 'emission' in textures:
        bsdf.inputs['Emission Strength'].default_value = 1.0
    if 'alpha' in textures:
        mat.surface_render_method = 'DITHERED'
    if 'normal' in textures:
        normal = tree.nodes.new('ShaderNodeNormalMap')
        normal.space = 'TANGENT'
        normal.uv_map = settings.bake_uv_name
        normal.location = (0, -300)
        tree.links.new(textures['normal'].outputs['Color'], normal.inputs['Color'])
        tree.links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    if 'ao' in textures:
        # Use precisely the group builder supplied by the bundled glTF exporter.
        from io_scene_gltf2.blender.com.material_helpers import get_gltf_node_name, create_settings_group
        group_name = get_gltf_node_name()
        group = bpy.data.node_groups.get(group_name)
        if group is None:
            group = create_settings_group(group_name)
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = group
        group_node.location = (0, -550)
        if 'Occlusion' not in group_node.inputs:
            raise ValueError("The glTF Material Output group has no Occlusion input.")
        tree.links.new(textures['ao'].outputs['Color'], group_node.inputs['Occlusion'])
    return mat
