"""Real GLB export, repeatability, context restoration and failure cleanup."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import addon_utils
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.babylon_export import export as exporting
from LC_workflow_addon.babylon_export import simplebake_adapter, state as export_state
from LC_workflow_addon.babylon_export.core import verify_glb
from LC_workflow_addon.babylon_export.materials import build_baked_material, find_baked_material
from LC_workflow_addon.babylon_export.panels import LCW_PT_babylon_export
from LC_workflow_addon.babylon_export.plan import build_bake_plan
from LC_workflow_addon.babylon_export.state import snapshot_state, restore_state
from LC_workflow_addon.babylon_export.validation import validate, has_principled
from LC_workflow_addon.babylon_export.exporters import is_gltf_exporter, selected_exporter, MISSING_EXPORT_PATH
from LC_workflow_addon.babylon_export.settings import exporter_items
from LC_workflow_addon.babylon_export.selection import refresh_material_list


simplebake_updates = []


def count_simplebake_update(self, context):
    simplebake_updates.append(self.as_pointer())


class BBE_TestSimpleBakeObject(bpy.types.PropertyGroup):
    obj_point: bpy.props.PointerProperty(type=bpy.types.Object, update=count_simplebake_update)
    name: bpy.props.StringProperty(update=count_simplebake_update)
    expanded: bpy.props.BoolProperty(update=count_simplebake_update)


class BBE_TestSimpleBakeProps(bpy.types.PropertyGroup):
    global_mode: bpy.props.StringProperty(default='PBR', update=count_simplebake_update)
    tex_per_mat: bpy.props.BoolProperty(update=count_simplebake_update)
    selected_col: bpy.props.BoolProperty(update=count_simplebake_update)
    bgbake: bpy.props.BoolProperty(update=count_simplebake_update)
    objects_list: bpy.props.CollectionProperty(type=BBE_TestSimpleBakeObject)


class BBE_TestUnnamedGltfHandler(bpy.types.FileHandler):
    bl_idname = 'BBE_FH_unnamed_gltf'
    bl_label = ''
    bl_export_operator = 'export_scene.gltf'
    bl_file_extensions = '.glb'

    @classmethod
    def poll_drop(cls, context):
        return False


def fake_simplebake_values(group):
    return (group.global_mode, group.tex_per_mat, group.selected_col, group.bgbake,
            [(item.obj_point, item.name, item.expanded) for item in group.objects_list])


class Layout:
    def __init__(self, calls):
        self.calls = calls
        self.enabled = True

    def row(self, **kwargs):
        return Layout(self.calls)

    column = row
    box = row

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self.calls.append(('prop', name))

    def label(self, **kwargs):
        if 'icon' in kwargs:
            assert kwargs['icon'] in icons
        self.calls.append(('label', kwargs.get('text')))

    def operator(self, name, **kwargs):
        namespace, operator = name.split('.')
        getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        self.calls.append(('operator', name, self.enabled))

    def template_list(self, name, identifier, data, propname, active_data, active_propname, **kwargs):
        assert name == 'LCW_UL_babylon_materials'
        assert propname in data.bl_rna.properties
        assert active_propname in active_data.bl_rna.properties
        self.calls.append(('list', propname))


def original_state(objects):
    return [(o, [(s.link, s.material) for s in o.material_slots], o.data,
             [uv.name for uv in o.data.uv_layers], o.data.uv_layers.active_index,
             [uv.active_render for uv in o.data.uv_layers], o.parent,
             tuple(tuple(row) for row in o.matrix_world)) for o in objects]


def context_state():
    return (set(bpy.context.selected_objects), bpy.context.view_layer.objects.active, bpy.context.mode)


def assert_clean():
    assert not list(exporting.temporary_datablocks()), 'Leaked temporary IDs'


def round3_fixture(root=None):
    """User-like six-slot door, plain glass, three variants and explicit opt-out."""
    scene = bpy.data.scenes[0]
    previous_variants = [(v.variant_idx, v.name) for v in scene.gltf2_KHR_materials_variants_variants]
    previous_target = scene.lcw_babylon_export.target_collection
    saved_context = snapshot_state(SimpleNamespace(objects=[]))
    collection = bpy.data.collections.new('Round3 Export')
    scene.collection.children.link(collection)
    scene.lcw_babylon_export.target_collection = collection
    settings = collection.lcw_babylon_export
    exporter = collection.exporters.new('BBE_FH_unnamed_gltf')
    assert exporter.name == ''
    assert exporter.export_properties.bl_rna.identifier == 'EXPORT_SCENE_OT_gltf'
    assert selected_exporter(collection) == exporter
    assert exporter_items(settings, bpy.context)[0][1].startswith('glTF (1)')
    props = exporter.export_properties
    props.export_format, props.export_materials = 'GLB', 'EXPORT'
    props.export_animations = False
    props.export_draco_mesh_compression_enable = True
    materials, objects, images, baked_materials, meshes = [], [], [], [], []
    try:
        scene.gltf2_KHR_materials_variants_variants.clear()
        for idx, name in enumerate(('Drasany', 'Lazura', 'Hlinik')):
            variant = scene.gltf2_KHR_materials_variants_variants.add()
            variant.variant_idx, variant.name = idx, name
        source_image = bpy.data.images.new('Round3 source texture', width=4, height=4)
        source_image.pixels = [0.2, 0.4, 0.6, 1.0] * 16
        images.append(source_image)
        for name in ('Round3_A', 'Round3_B', 'Round3_C', 'Round3 Plain0', 'Round3 Plain1',
                     'Round3 Plain2', 'Round3 Plain3', 'Round3 Glass0', 'Round3 Glass1'):
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            materials.append(mat)
        for mat in materials[:3]:
            texture = mat.node_tree.nodes.new('ShaderNodeTexImage')
            texture.image = source_image
            mat.node_tree.links.new(texture.outputs['Color'],
                                    mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
        for name, slots in (('Round3 Door', [materials[0], materials[0], *materials[3:7]]),
                            ('Round3 Glass', materials[7:])):
            bpy.ops.mesh.primitive_cube_add()
            obj = bpy.context.object
            obj.name = name
            for owner in list(obj.users_collection):
                owner.objects.unlink(obj)
            collection.objects.link(obj)
            obj.data.materials.clear()
            for mat in slots:
                obj.data.materials.append(mat)
            obj.data.uv_layers.active.name = 'UVMap'
            for index, polygon in enumerate(obj.data.polygons):
                polygon.material_index = index % len(slots)
            objects.append(obj)
            meshes.append(obj.data)
        door, glass = objects
        uv = door.data.uv_layers.new(name='SimpleBake')
        for source, target in zip(door.data.uv_layers['UVMap'].data, uv.data):
            target.uv = source.uv
        door.data.uv_layers.active_index = 0
        door.data.uv_layers[1].active_render = True
        for slot in (0, 1):
            default = door.data.gltf2_variant_default_materials.add()
            default.material_slot_index, default.default_material = slot, materials[0]
            for idx, mat in enumerate(materials[:3]):
                entry = door.data.gltf2_variant_mesh_data.add()
                entry.material_slot_index, entry.material = slot, mat
                entry.variants.add().variant.variant_idx = idx
        assert bpy.ops.lcw.babylon_check() == {'FINISHED'}
        choices = {item.material: item for item in settings.material_selections}
        assert {mat for mat, item in choices.items() if item.bake} == set(materials[:3])
        assert not any(item.user_override for item in choices.values())
        plan = build_bake_plan(collection)
        assert plan.material_pairs() == {(door, mat) for mat in materials[:3]}
        assert all(glass not in bake_pass.objects for bake_pass in plan.passes)
        errors = [i for i in validate(collection, for_export=True) if i.level == 'ERROR']
        assert MISSING_EXPORT_PATH in [i.text for i in errors]
        assert not any(i.object == glass.name for i in errors)
        try:
            exporting.export_collection(collection)
            raise AssertionError('Missing output path was accepted')
        except ValueError as exc:
            assert MISSING_EXPORT_PATH in str(exc)
        before_choices = [(item.material, item.bake, item.user_override) for item in settings.material_selections]
        draw_calls = []
        LCW_PT_babylon_export.draw(SimpleNamespace(layout=Layout(draw_calls)), bpy.context)
        assert 'Collection Exporter' in ' '.join(call[1] for call in draw_calls if call[0] == 'label')
        assert before_choices == [(item.material, item.bake, item.user_override) for item in settings.material_selections]
        with patch.object(simplebake_adapter, 'availability', return_value=('FakeSimpleBake', (2, 9, 11))), \
                patch('LC_workflow_addon.babylon_export.validation.availability', return_value=('FakeSimpleBake', (2, 9, 11))):
            settings.simplebake_preset = ''
            assert not any('preset' in i.text.lower() for i in validate(collection))
            settings.simplebake_preset = 'Missing preset'
            assert any('preset' in i.text.lower() and i.level == 'ERROR' for i in validate(collection))
            settings.simplebake_preset = ''
        # Automatic choices follow changed graphs; explicit user choices do not.
        extra = materials[4].node_tree.nodes.new('ShaderNodeTexImage')
        refresh_material_list(collection)
        assert choices[materials[4]].bake and not choices[materials[4]].user_override
        materials[4].node_tree.nodes.remove(extra)
        refresh_material_list(collection)
        assert not choices[materials[4]].bake
        choices[materials[3]].bake = True
        refresh_material_list(collection)
        assert choices[materials[3]].bake and choices[materials[3]].user_override
        choices[materials[3]].bake = False
        choices[materials[2]].bake = False
        door.data.materials[5] = None
        refresh_material_list(collection)
        assert materials[6] not in {item.material for item in settings.material_selections}
        door.data.materials[5] = materials[6]
        refresh_material_list(collection)
        choices = {item.material: item for item in settings.material_selections}
        # Opt out of a textured variant to cover original variant materials.
        # This row shifted after deletion; its explicit choice must survive.
        refresh_material_list(collection)
        assert not choices[materials[2]].bake and choices[materials[2]].user_override
        assert any(i.level == 'WARNING' and 'it gets UV map' in i.text for i in validate(collection, for_export=True))
        print('PASS babylon_round3_exporter_selection_preflight')
        if root is None:
            # Exercise copy/restore in memory before the filesystem fixture.
            # The patched exporter writes no file and uses the existing temp
            # directory, so this also checks logic in restricted environments.
            exporter.filepath = str(Path(tempfile.gettempdir()) / 'babylon_round3_not_written.glb')
            plan = build_bake_plan(collection)
            for obj, mat in plan.material_pairs():
                baked_materials.append(build_baked_material(mat, obj, {'base_color': source_image}, settings))
            before, before_context = original_state(objects), context_state()
            def inspect_copies(props):
                temp = bpy.data.collections[props['collection']]
                copied_door = next(o for o in temp.objects if o.name.startswith(door.name))
                copied_glass = next(o for o in temp.objects if o.name.startswith(glass.name))
                assert [uv.name for uv in copied_door.data.uv_layers] == ['SimpleBake']
                assert [uv.name for uv in copied_glass.data.uv_layers] == ['UVMap']
                assert copied_door.material_slots[0].material in baked_materials
                assert copied_door.material_slots[2].material == materials[3]
                assert copied_glass.material_slots[0].material == materials[7]
                assert any(item.material == materials[2] for item in copied_door.data.gltf2_variant_mesh_data)
                assert props['export_texcoords'] and not props['export_draco_mesh_compression_enable']
                return {'FINISHED'}
            with patch.object(exporting, '_export_gltf', inspect_copies), \
                    patch.object(export_state, 'bake_properties', side_effect=AssertionError('Export read SimpleBake')):
                exporting.export_collection(collection)
            assert original_state(objects) == before and context_state() == before_context
            assert_clean()
            print('PASS babylon_round3_unbaked_copies_uv_restore')
            return
        exporter.filepath = str(root / 'round3.glb')
        source_image.filepath_raw, source_image.file_format = str(root / 'round3_source.png'), 'PNG'
        source_image.save()
        assert 'round3.glb' in exporter_items(settings, bpy.context)[0][1]
        plan = build_bake_plan(collection)
        channel_maps = {}
        for obj, mat in plan.material_pairs():
            image = bpy.data.images.new(mat.name + '_round3_bake', width=4, height=4)
            image.pixels = [0.7, 0.5, 0.3, 1.0] * 16
            image.filepath_raw, image.file_format = str(root / (image.name + '.png')), 'PNG'
            image.save()
            images.append(image)
            channel_maps[obj, mat] = {'base_color': image}
            baked_materials.append(build_baked_material(mat, obj, channel_maps[obj, mat], settings))
        assert not [i for i in validate(collection, for_export=True) if i.level == 'ERROR']
        before, before_context = original_state(objects), context_state()
        counts = len(bpy.data.materials), len(bpy.data.images)
        path = exporting.export_collection(collection)
        report = verify_glb(path, expected_variants=3, require_variants=True,
                            expected_baked_materials=exporting.expected_baked_names(plan))
        assert report['ok'], report['errors']
        doc = report['document']
        names = {mat['name'] for mat in doc['materials']}
        assert {mat.name for mat in materials[2:]} <= names
        assert materials[0].name not in names and materials[1].name not in names
        assert {mat.name for mat in baked_materials} <= names
        mapped_names = {doc['materials'][mapping['material']]['name']
                        for mesh in doc['meshes'] for primitive in mesh['primitives']
                        for mapping in primitive.get('extensions', {}).get('KHR_materials_variants', {}).get('mappings', [])}
        assert materials[2].name in mapped_names
        assert original_state(objects) == before and context_state() == before_context
        assert_clean()
        for (obj, mat), channels in channel_maps.items():
            assert build_baked_material(mat, obj, channels, settings) == find_baked_material(mat, obj, collection)
        assert bpy.ops.lcw.babylon_refresh_materials() == {'FINISHED'}
        exporting.export_collection(collection)
        assert (len(bpy.data.materials), len(bpy.data.images)) == counts
        assert not next(item for item in settings.material_selections if item.material == materials[2]).bake
        def fail(props):
            raise RuntimeError('Round3 injected failure')
        with patch.object(exporting, '_export_gltf', fail):
            try:
                exporting.export_collection(collection)
                raise AssertionError('Export failure was swallowed')
            except RuntimeError as exc:
                assert str(exc) == 'Round3 injected failure'
        assert original_state(objects) == before and context_state() == before_context
        assert_clean()
        print('PASS babylon_round3_mixed_glb_repeat_restore')
    finally:
        scene.lcw_babylon_export.target_collection = previous_target
        scene.gltf2_KHR_materials_variants_variants.clear()
        for idx, name in previous_variants:
            variant = scene.gltf2_KHR_materials_variants_variants.add()
            variant.variant_idx, variant.name = idx, name
        bpy.data.batch_remove(ids=[*objects, *meshes, *baked_materials, *materials, *images, collection])
        restore_state(saved_context)


addon.register()
# Prove re-registration and partial-registration cleanup work without SimpleBake.
addon.register()
assert not any('simplebake' in item.module.lower() for item in bpy.context.preferences.addons)
calls = []
icons = {item.identifier for item in bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items}
LCW_PT_babylon_export.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
assert all(not enabled for kind, name, enabled in (c for c in calls if c[0] == 'operator')
           if name == 'lcw.babylon_bake_phase2')
print('PASS babylon_panel_factory_startup')
addon_utils.enable('io_scene_gltf2')
prefs = bpy.context.preferences.addons['io_scene_gltf2'].preferences
old_variants = prefs.KHR_materials_variants_ui
prefs.KHR_materials_variants_ui = True

fake_classes = []
try:
    assert not hasattr(bpy.types.Scene, 'SimpleBake_Props')
    for cls in (BBE_TestSimpleBakeObject, BBE_TestSimpleBakeProps, BBE_TestUnnamedGltfHandler):
        bpy.utils.register_class(cls)
        fake_classes.append(cls)
    bpy.types.Scene.SimpleBake_Props = bpy.props.PointerProperty(type=BBE_TestSimpleBakeProps)
    fake_sb = bpy.context.scene.SimpleBake_Props
    fake_sb.global_mode = 'USER_MODE'
    fake_sb.tex_per_mat = True
    fake_sb.selected_col = True
    fake_sb.bgbake = True
    item = fake_sb.objects_list.add()
    item.obj_point, item.name, item.expanded = bpy.context.object, 'Original row', True
    empty_plan = SimpleNamespace(objects=[])
    with patch.object(simplebake_adapter, 'availability', return_value=('FakeSimpleBake', (2, 9, 11))):
        simplebake_updates.clear()
        with patch.object(export_state, 'bake_properties', side_effect=AssertionError('Unexpected SimpleBake read')):
            default_snapshot = snapshot_state(empty_plan)
            assert default_snapshot.simplebake is None
            restore_state(default_snapshot)
        assert simplebake_updates == []
        phase2_snapshot = snapshot_state(empty_plan, include_simplebake=True)
        assert set(phase2_snapshot.simplebake_values) == {
            'global_mode', 'tex_per_mat', 'selected_col', 'objects_list'}
        row_pointer = fake_sb.objects_list[0].as_pointer()
        restore_state(phase2_snapshot)
        assert simplebake_updates == [], simplebake_updates
        fake_sb.global_mode = 'CHANGED'
        fake_sb.selected_col = False
        fake_sb.objects_list[0].name = 'Changed row'
        fake_sb.objects_list.add()
        fake_sb.bgbake = False  # unrelated setting must not be restored
        simplebake_updates.clear()
        restore_state(phase2_snapshot)
        assert len(simplebake_updates) == 3, simplebake_updates
        assert fake_sb.global_mode == 'USER_MODE' and fake_sb.selected_col is True
        assert fake_sb.bgbake is False
        assert len(fake_sb.objects_list) == 1
        assert fake_sb.objects_list[0].name == 'Original row'
        assert fake_sb.objects_list[0].as_pointer() == row_pointer
        # Exercise list growth as well; only fields differing from new defaults
        # should be assigned when recreating a removed bake-list entry.
        fake_sb.objects_list.remove(0)
        simplebake_updates.clear()
        restore_state(phase2_snapshot)
        assert len(simplebake_updates) == 3, simplebake_updates
        assert fake_sb.objects_list[0].obj_point == phase2_snapshot.simplebake_values['objects_list'][0]['obj_point']
        assert fake_sb.objects_list[0].name == 'Original row' and fake_sb.objects_list[0].expanded is True
        simplebake_updates.clear()
        restore_state(phase2_snapshot)
        assert simplebake_updates == [], simplebake_updates
    print('PASS babylon_simplebake_explicit_snapshot_restore')

    round3_fixture()

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bpy.ops.wm.save_as_mainfile(filepath=str(root / 'fixture.blend'))
        scene = bpy.data.scenes[0]
        collection = bpy.data.collections.new('Babylon Fixture')
        scene.collection.children.link(collection)
        child = bpy.data.collections.new('Nested')
        collection.children.link(child)
        bpy.context.scene.lcw_babylon_export.target_collection = collection
        settings = collection.lcw_babylon_export
        assert settings.texture_dir == '//bakes/Babylon Fixture/'
        settings.texture_dir = str(root / 'textures')
        assert settings.texture_dir == str(root / 'textures')
        exporter = collection.exporters.new('IO_FH_gltf2')
        assert is_gltf_exporter(exporter)
        exporter.filepath = str(root / 'fixture.glb')
        props = exporter.export_properties
        props.export_format = 'GLB'
        props.export_animations = False
        props.export_texcoords = False  # bridge must force UV on
        props.export_draco_mesh_compression_enable = True  # bridge must force it off
        props.export_apply = False
        props.use_selection = True
        props.use_active_collection = True
        props.export_cameras = True
        materials = []
        for name in ('Oak', 'Blue', 'Red'):
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            assert has_principled(mat)
            materials.append(mat)
        for index, name in enumerate(('Blue Variant', 'Red Variant')):
            variant = scene.gltf2_KHR_materials_variants_variants.add()
            variant.variant_idx = index
            variant.name = name
        objects = []
        parent = bpy.data.objects.new('Export Parent', None)
        collection.objects.link(parent)
        parent.location = (2, 1, 0)
        camera_data = bpy.data.cameras.new('External Parent Camera')
        camera_parent = bpy.data.objects.new('External Camera Parent', camera_data)
        scene.collection.objects.link(camera_parent)
        camera_parent.location = (4, -3, 2)
        parent.parent = camera_parent
        for index in range(2):
            bpy.ops.mesh.primitive_cube_add(location=(index * 3, 0, 0))
            obj = bpy.context.object
            obj.name = f'Fixture {index}'
            for owner in list(obj.users_collection):
                owner.objects.unlink(obj)
            (collection if index == 0 else child).objects.link(obj)
            obj.parent = parent
            obj.data.uv_layers.active.name = 'OriginalUV'
            uv = obj.data.uv_layers.new(name='SimpleBake')
            for old, new in zip(obj.data.uv_layers['OriginalUV'].data, uv.data):
                new.uv = old.uv
            obj.data.uv_layers.active_index = 0
            obj.data.uv_layers[0].active_render = True
            obj.data.materials.append(materials[0])
            if index == 0:
                default = obj.data.gltf2_variant_default_materials.add()
                default.material_slot_index = 0
                default.default_material = materials[0]
                for idx in range(2):
                    entry = obj.data.gltf2_variant_mesh_data.add()
                    entry.material_slot_index = 0
                    entry.material = materials[idx + 1]
                    ref = entry.variants.add()
                    ref.variant.variant_idx = idx
                # Current visible variant differs from the saved default.
                obj.material_slots[0].link = 'OBJECT'
                obj.material_slots[0].material = materials[1]
            objects.append(obj)
        bpy.context.view_layer.update()
        objects[0].shape_key_add(name='Basis')
        shape = objects[0].shape_key_add(name='Shape')
        shape.data[0].co.z += 0.1
        source_keys = objects[0].data.shape_keys
        plan = build_bake_plan(collection)
        assert len(plan.passes) == 3
        assert plan.passes[1].objects == {objects[0]}
        images = {}
        bpy.data.materials.new('Blue_baked')  # unrelated name collision must not be reused
        for obj, source in sorted(plan.material_pairs(), key=lambda pair: (pair[0].name, pair[1].name)):
            channels = {}
            for channel in ('base_color', 'metallic', 'roughness', 'normal', 'emission', 'alpha', 'ao'):
                image = bpy.data.images.new(f'{obj.name}_{source.name}_{channel}', width=4, height=4)
                rgba = (0.5, 0.5, 1.0, 1.0) if channel == 'normal' else (0.7, 0.3, 0.1, 1.0)
                image.pixels = list(rgba) * 16
                image.filepath_raw = str(root / (image.name + '.png'))
                image.file_format = 'PNG'
                image.save()
                channels[channel] = image
            images[obj, source] = channels
            baked = build_baked_material(source, obj, channels, settings)
            assert baked.use_fake_user
            for channel, image in channels.items():
                assert image.colorspace_settings.name == ('sRGB' if channel in {'base_color', 'emission'} else 'Non-Color')
            assert baked['bbe_source_material'] == source
        errors = [i for i in validate(collection, for_export=True) if i.level == 'ERROR']
        assert errors == [], errors
        prefs.KHR_materials_variants_ui = False
        try:
            disabled_errors = [i.text for i in validate(collection, for_export=True) if i.level == 'ERROR']
            assert disabled_errors == ['Enable material variants in the glTF exporter preferences.'], disabled_errors
        finally:
            prefs.KHR_materials_variants_ui = True
        assert len(scene.gltf2_KHR_materials_variants_variants) == 2
        print('PASS babylon_variants_preference_validation')
        bake_errors = [i.text for i in validate(collection) if i.level == 'ERROR']
        assert bake_errors == ['SimpleBake is not installed or enabled; baking is unavailable'], bake_errors
        before, context_before = original_state(objects), context_state()
        material_count, image_count = len(bpy.data.materials), len(bpy.data.images)
        sb_before = fake_simplebake_values(fake_sb)
        simplebake_updates.clear()
        real_export = exporting._export_gltf

        def inspect_external_parent(props):
            temp = bpy.data.collections[props['collection']]
            proxy = next(obj for obj in temp.objects if obj.name.startswith(camera_parent.name + '_parent'))
            assert proxy.type == 'EMPTY' and proxy.data is None
            assert tuple(tuple(row) for row in proxy.matrix_world) == tuple(
                tuple(row) for row in camera_parent.matrix_world)
            return real_export(props)

        with patch.object(simplebake_adapter, 'availability', return_value=('FakeSimpleBake', (2, 9, 11))), \
                patch.object(export_state, 'bake_properties', side_effect=AssertionError('Export read SimpleBake')), \
                patch.object(exporting, '_export_gltf', inspect_external_parent):
            path = exporting.export_collection(collection, settings)
        assert simplebake_updates == [], simplebake_updates
        assert fake_simplebake_values(fake_sb) == sb_before
        print('PASS babylon_export_simplebake_untouched')
        report = verify_glb(path, expected_variants=2, require_variants=True)
        assert report['ok'], report['errors']
        assert not report['document'].get('cameras')
        assert all('camera' not in node for node in report['document']['nodes'])
        assert camera_parent.type == 'CAMERA' and camera_parent.data == camera_data
        print('PASS babylon_external_camera_parent_empty')
        assert report['mappings'] == 2
        assert report['images'] > 0
        assert all('occlusionTexture' in m for m in report['document']['materials'])
        assert all(m['name'] != 'Blue_baked' for m in report['document']['materials'])
        assert original_state(objects) == before
        assert objects[0].data.shape_keys == source_keys
        assert not source_keys.get('bbe_temp')
        assert context_state() == context_before
        assert_clean()
        print('PASS babylon_glb_uv_variants_ao_cleanup')
        for (obj, source), channels in images.items():
            old = find_baked_material(source, obj, collection)
            assert build_baked_material(source, obj, channels, settings) == old
        exporting.export_collection(collection, settings)
        assert (len(bpy.data.materials), len(bpy.data.images)) == (material_count, image_count)
        assert original_state(objects) == before
        assert_clean()
        print('PASS babylon_repeat_no_duplicates')

        bpy.ops.object.mode_set(mode='EDIT')
        edit_before = context_state()
        exporting.export_collection(collection)
        assert context_state() == edit_before
        assert original_state(objects) == before
        assert_clean()
        bpy.ops.object.mode_set(mode='OBJECT')
        print('PASS babylon_edit_mode_restore')

        def fail(props):
            assert list(exporting.temporary_datablocks())
            assert bpy.data.collections[props['collection']]['bbe_temp']
            scene.frame_set(7)  # exporter failures can leave the frame changed
            raise RuntimeError('Injected exporter failure')

        with patch.object(exporting, '_export_gltf', fail):
            try:
                exporting.export_collection(collection, settings)
                raise AssertionError('Exception was swallowed')
            except RuntimeError as exc:
                assert str(exc) == 'Injected exporter failure'
        assert original_state(objects) == before
        assert context_state() == context_before
        assert scene.frame_current == 1
        assert_clean()
        print('PASS babylon_exception_cleanup_restore')

        saved = snapshot_state(plan)
        underlying = list(objects[0].data.materials)
        objects[0].data.materials[0] = materials[2]
        objects[0].data.materials.append(materials[2])
        objects[0].material_slots[0].material = materials[2]
        objects[0].data.uv_layers.active_index = 1
        objects[0].data.uv_layers[1].active_render = True
        bpy.ops.object.select_all(action='DESELECT')
        restore_state(saved)
        assert original_state(objects) == before
        assert list(objects[0].data.materials) == underlying
        assert context_state() == context_before
        print('PASS babylon_snapshot_restore')

        unused = scene.gltf2_KHR_materials_variants_variants.add()
        unused.variant_idx, unused.name = 2, 'Identity Variant'
        identity_path = exporting.export_collection(collection)
        identity_report = verify_glb(identity_path, expected_variants=3, require_variants=True)
        assert identity_report['ok'], identity_report['errors']
        assert original_state(objects) == before
        scene.gltf2_KHR_materials_variants_variants.remove(2)
        assert_clean()
        print('PASS babylon_all_scene_variants')

        replica = objects[0].copy()
        replica.name = 'Linked Mesh Fixture'
        child.objects.link(replica)
        replica_state = original_state([objects[0], replica])
        replica_bakes = []
        try:
            for source in materials:
                replica_bakes.append(build_baked_material(source, replica, images[objects[0], source], settings))
            linked_path = exporting.export_collection(collection)
            linked_report = verify_glb(linked_path, expected_variants=2, require_variants=True)
            assert linked_report['ok'], linked_report['errors']
            assert original_state([objects[0], replica]) == replica_state
            assert replica.data is objects[0].data
            assert not source_keys.get('bbe_temp')
            assert_clean()
        finally:
            bpy.data.objects.remove(replica, do_unlink=True)
            for material in replica_bakes:
                bpy.data.materials.remove(material)
        print('PASS babylon_linked_mesh_originals_preserved')

        settings.export_variants = False
        no_variants = exporting.export_collection(collection)
        report = verify_glb(no_variants, expected_variants=0)
        assert report['ok'], report['errors']
        assert prefs.KHR_materials_variants_ui is True
        assert len(scene.gltf2_KHR_materials_variants_variants) == 2
        settings.export_variants = True
        assert bpy.ops.lcw.babylon_check() == {'FINISHED'}
        assert bpy.ops.lcw.babylon_export() == {'FINISHED'}
        stored = json.loads(settings.last_report)
        assert stored['ok'] and stored['variants'] == 2
        assert stored['export_settings']['export_draco_mesh_compression_enable'] is False
        assert props.export_draco_mesh_compression_enable is True
        assert_clean()

        # Check Principled traversal through a group and reroute, including a
        # disconnected Principled node that must not count as a valid shader.
        shader_test = bpy.data.materials.new('Group Validation')
        shader_test.use_nodes = True
        tree = shader_test.node_tree
        tree.nodes.clear()
        output = tree.nodes.new('ShaderNodeOutputMaterial')
        disconnected = tree.nodes.new('ShaderNodeBsdfPrincipled')
        assert not has_principled(shader_test)
        group = bpy.data.node_groups.new('Shader Test Group', 'ShaderNodeTree')
        group.interface.new_socket('Shader', in_out='OUTPUT', socket_type='NodeSocketShader')
        group_out = group.nodes.new('NodeGroupOutput')
        group_bsdf = group.nodes.new('ShaderNodeBsdfPrincipled')
        group.links.new(group_bsdf.outputs['BSDF'], group_out.inputs['Shader'])
        group_node = tree.nodes.new('ShaderNodeGroup')
        group_node.node_tree = group
        reroute = tree.nodes.new('NodeReroute')
        tree.links.new(group_node.outputs['Shader'], reroute.inputs[0])
        tree.links.new(reroute.outputs[0], output.inputs['Surface'])
        assert has_principled(shader_test)
        print('PASS babylon_principled_groups_reroutes')

        round3_fixture(root)

        objects[1].data.uv_layers.remove(objects[1].data.uv_layers['SimpleBake'])
        errors = [i.text for i in validate(collection, for_export=True) if i.level == 'ERROR']
        assert errors == ['Object "Fixture 1" has no UV map "SimpleBake".'], errors
        print('PASS babylon_validation_exact_missing_uv')

        for items, factory in ((bpy.data.meshes, lambda: bpy.data.meshes.new('Orphan')),
                               (bpy.data.images, lambda: bpy.data.images.new('OrphanImage', width=1, height=1))):
            factory()['bbe_temp'] = True
        assert bpy.ops.lcw.babylon_cleanup() == {'FINISHED'}
        assert_clean()
finally:
    if fake_classes and hasattr(bpy.types.Scene, 'SimpleBake_Props'):
        del bpy.types.Scene.SimpleBake_Props
    for cls in reversed(fake_classes):
        bpy.utils.unregister_class(cls)
    prefs.KHR_materials_variants_ui = old_variants
    addon.unregister()
    assert not hasattr(bpy.types.Collection, 'lcw_babylon_export')
    assert not hasattr(bpy.types.Scene, 'lcw_babylon_export')
print('PASS blender_babylon_export')
