"""Bake job end to end with a simulated SimpleBake.

Only SimpleBake itself is simulated (its asynchronous bake cannot run in
--background). The real adapter configures settings and collects tagged
images; the real job assigns variant materials, builds *_baked materials and
restores originals; the real exporter writes and verifies a GLB. Saving and
restoring SimpleBake settings through its preset mechanism is covered by the
real SimpleBake end-to-end run, not here.

blender --background --factory-startup --python tests/blender_babylon_bake.py
"""
import copy
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.babylon_export import bake as bake_module
from LC_workflow_addon.babylon_export import simplebake_adapter as real_adapter
from LC_workflow_addon.babylon_export import validation as validation_module
from LC_workflow_addon.babylon_export.bake import CANCELLED, FAILED, FINISHED, RUNNING, BakeJob
from LC_workflow_addon.babylon_export.core import verify_glb
from LC_workflow_addon.babylon_export.materials import find_baked_material
from LC_workflow_addon.babylon_export.operators import run_export
from LC_workflow_addon.babylon_export.selection import refresh_material_list

SNAPSHOT_FIELDS = ('global_mode', 'tex_per_mat', 'expand_mat_uvs', 'new_uv_option', 'copy_and_apply',
                   'hide_source_objects', 'auto_detect_udims', 'export_path', 'batch_name')


class FakeCollection(list):
    def __init__(self, factory):
        super().__init__()
        self.factory = factory

    def add(self):
        item = self.factory()
        self.append(item)
        return item

    def remove(self, index):
        del self[index]


def make_sbp():
    """SimpleBake_Props stand-in with non-forced starting values."""
    sbp = SimpleNamespace(
        selected_col=True, selected_rough=True, selected_normal=True, selected_metal=False,
        selected_bump=False, fake_background=False,
        global_mode='CYCLES', tex_per_mat=False, merged_bake=False, new_uv_option=True,
        prefer_existing_sbmap=True, expand_mat_uvs=True, restore_orig_uv_map=False,
        copy_and_apply=True, hide_source_objects=True, auto_detect_udims=True,
        save_bakes_external=False, keep_internal_after_export=False, export_path='//old/',
        batch_name='Bake1', imgwidth=1024, imgheight=1024,
        objects_list=FakeCollection(lambda: SimpleNamespace(obj_point=None, name='', expanded=False)),
        mat_bake_list=FakeCollection(lambda: SimpleNamespace(obj_name='', mat_name='', enabled=True)))
    # Every other forced setting starts at a value different from the forced one.
    for name, value in real_adapter.FORCED_SETTINGS.items():
        if not hasattr(sbp, name):
            setattr(sbp, name, (not value) if isinstance(value, bool) else f'user_{value}')
    sbp.objects_list.add().name = 'Someone else'
    entry = sbp.mat_bake_list.add()
    entry.obj_name, entry.mat_name, entry.enabled = 'Someone else', 'Old', False
    return sbp


def sb_values(sbp):
    return ({name: getattr(sbp, name) for name in SNAPSHOT_FIELDS},
            [r.name for r in sbp.objects_list],
            [(e.obj_name, e.mat_name, e.enabled) for e in sbp.mat_bake_list])


class FakeAdapter:
    """Real configure/collect/expected channels; simulated SimpleBake bake."""

    def __init__(self, sbp, *, fail_on_start=None, never_finish=False, channels=('Diffuse', 'Roughness', 'Normal')):
        self.sbp = sbp
        self.fail_on_start = fail_on_start
        self.never_finish = never_finish
        self.channels = channels
        self.bake_running = False
        self.starts = []
        self.baking_ticks = 0
        self.prefs = {'saveonbake': True, 'purge_after_bake': True, 'solidshadingonbake': True}
        self.saved = None
        self.restored_settings = False
        self.stuck_cleared = False

    def bake_properties(self, scene):
        return self.sbp

    def save_settings(self, sbp):
        self.saved = (copy.deepcopy({n: getattr(sbp, n) for n in SNAPSHOT_FIELDS}),
                      [copy.copy(r) for r in sbp.objects_list], [copy.copy(e) for e in sbp.mat_bake_list])
        return 'token'

    def restore_settings(self, sbp, token):
        assert token == 'token'
        values, objects, materials = self.saved
        for name, value in values.items():
            setattr(sbp, name, value)
        sbp.objects_list[:] = objects
        sbp.mat_bake_list[:] = materials
        self.restored_settings = True

    def suspend_preferences(self):
        previous = {name: value for name, value in self.prefs.items() if value}
        for name in previous:
            self.prefs[name] = False
        return previous

    def restore_preferences(self, previous):
        self.prefs.update(previous)

    def configure_simplebake(self, sbp, **kwargs):
        real_adapter.configure_simplebake(sbp, **kwargs)

    def expected_channels(self, sbp):
        return real_adapter.expected_channels(sbp)

    def bake_job_running(self):
        return self.bake_running

    def clear_stuck_bake(self):
        self.stuck_cleared = True

    def start_bake(self, operation_id):
        number = len(self.starts) + 1
        if self.fail_on_start == number:
            raise RuntimeError('simulated SimpleBake refusal')
        sbp = self.sbp
        self.starts.append(dict(
            enabled={(e.obj_name, e.mat_name) for e in sbp.mat_bake_list if e.enabled},
            disabled={(e.obj_name, e.mat_name) for e in sbp.mat_bake_list if not e.enabled},
            objects=[row.obj_point.name for row in sbp.objects_list],
            forced={name: getattr(sbp, name) for name in real_adapter.FORCED_SETTINGS if hasattr(sbp, name)},
            slots={row.obj_point.name: [s.material.name if s.material else None
                                        for s in row.obj_point.material_slots] for row in sbp.objects_list},
            active_uv={row.obj_point.name: row.obj_point.data.uv_layers.active.name for row in sbp.objects_list},
            prefs=dict(self.prefs)))
        for obj_name, mat_name in self.starts[-1]['enabled']:
            for this_bake in self.channels:
                image = bpy.data.images.new(f'{obj_name}_{mat_name}_{this_bake}', 4, 4)
                image['SB_bake_operation_id'] = operation_id
                image['SB_bake_object'] = obj_name
                image['SB_bake_material'] = mat_name
                image['SB_this_bake'] = this_bake
        self.baking_ticks = 2

    def is_baking(self):
        if self.never_finish:
            return True
        if self.baking_ticks:
            self.baking_ticks -= 1
            return True
        return False

    def collect_bake_images(self, operation_id, pairs):
        return real_adapter.collect_bake_images(operation_id, pairs)


def patch_validation(sbp, prefs=None):
    """Make bake validation see an enabled SimpleBake 2.9.11."""
    validation_module.availability = lambda: ('SimpleBake', (2, 9, 11))
    validation_module.bake_properties = lambda scene: sbp
    validation_module.simplebake_preferences = lambda: prefs or SimpleNamespace(
        disable_other_addons2=False, img_name_format='%OBJ%_%BATCH%_%BAKEMODE%_%BAKETYPE%')


def new_job(collection, sbp=None, **adapter_kwargs):
    sbp = sbp or make_sbp()
    patch_validation(sbp)
    adapter = FakeAdapter(sbp, **adapter_kwargs)
    return BakeJob(collection, adapter=adapter), adapter, sbp


def build_scene(root):
    """User-like scene: door slots 0+1 with three variants, plain slots, glass."""
    scene = bpy.context.scene
    collection = bpy.data.collections.new('V2_Export')
    scene.collection.children.link(collection)
    exporter = collection.exporters.new('IO_FH_gltf2')
    props = exporter.export_properties
    props.export_format, props.export_materials = 'GLB', 'EXPORT'
    props.filepath = str(root / 'door_export.glb')
    scene.gltf2_KHR_materials_variants_variants.clear()
    for idx, name in enumerate(('Drasany', 'Lazura', 'Hlinik')):
        variant = scene.gltf2_KHR_materials_variants_variants.add()
        variant.variant_idx, variant.name = idx, name
    texture = bpy.data.images.new('Wood source', 4, 4)
    materials = {}
    for name in ('Wood_A', 'Wood_B', 'Wood_C', 'Aluminium', 'Rubber', 'Glass_Panel'):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        materials[name] = mat
    for name in ('Wood_A', 'Wood_B', 'Wood_C'):
        tree = materials[name].node_tree
        node = tree.nodes.new('ShaderNodeTexImage')
        node.image = texture
        tree.links.new(node.outputs['Color'], tree.nodes['Principled BSDF'].inputs['Base Color'])
    objects = {}
    for name, slots in (('door', ['Wood_A', 'Wood_A', 'Aluminium', 'Rubber']), ('glass', ['Glass_Panel'])):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = name
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
        obj.data.materials.clear()
        for slot in slots:
            obj.data.materials.append(materials[slot])
        for index, polygon in enumerate(obj.data.polygons):
            polygon.material_index = index % len(slots)
        obj.data.uv_layers.active.name = 'UVMap'
        objects[name] = obj
    door = objects['door']
    bake_uv = door.data.uv_layers.new(name='SimpleBake')
    for source, target in zip(door.data.uv_layers['UVMap'].data, bake_uv.data):
        target.uv = source.uv
    door.data.uv_layers.active_index = 0  # user keeps UVMap active
    for slot in (0, 1):
        for idx, name in enumerate(('Wood_A', 'Wood_B', 'Wood_C')):
            entry = door.data.gltf2_variant_mesh_data.add()
            entry.material_slot_index, entry.material = slot, materials[name]
            entry.variants.add().variant.variant_idx = idx
    bpy.ops.wm.save_as_mainfile(filepath=str(root / 'bake_fixture.blend'))
    return collection, door, objects['glass'], materials


def run(job, limit=400):
    for _ in range(limit):
        status = job.step()
        if status != RUNNING:
            return status
    raise AssertionError('job did not finish')


def slot_names(obj):
    return [s.material.name if s.material else None for s in obj.material_slots]


def faces(obj):
    return [p.material_index for p in obj.data.polygons]


def assert_restored(door, before, sbp, sb_before, adapter):
    slots, face_ids, uv = before
    assert slot_names(door) == slots, slot_names(door)
    assert faces(door) == face_ids, faces(door)
    assert door.data.uv_layers.active.name == uv
    assert sb_values(sbp) == sb_before, sb_values(sbp)
    assert adapter.restored_settings
    assert adapter.prefs == {'saveonbake': True, 'purge_after_bake': True, 'solidshadingonbake': True}


addon.register()
prefs = bpy.context.preferences.addons['io_scene_gltf2'].preferences
old_variants_ui = prefs.KHR_materials_variants_ui
prefs.KHR_materials_variants_ui = True
originals = (validation_module.availability, validation_module.bake_properties,
             validation_module.simplebake_preferences)
try:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        collection, door, glass, mats = build_scene(root)
        refresh_material_list(collection)
        selected = {item.material.name for item in collection.lcw_babylon_export.material_selections if item.bake}
        assert selected == {'Wood_A', 'Wood_B', 'Wood_C'}, selected
        before = (slot_names(door), faces(door), door.data.uv_layers.active.name)
        assert before[1] == [0, 1, 2, 3, 0, 1]

        # --- validation of SimpleBake setup and user data protection
        sbp = make_sbp()
        patch_validation(sbp, SimpleNamespace(disable_other_addons2=True, img_name_format='%BAKETYPE%'))
        errors = [i.text for i in validation_module.validate(collection) if i.level == 'ERROR']
        assert any('Disable other add-ons' in t for t in errors), errors
        assert any('%OBJ% and %BATCH%' in t for t in errors), errors
        sbp.selected_col = sbp.selected_rough = sbp.selected_normal = False
        sbp.selected_bump, sbp.fake_background = True, True
        patch_validation(sbp)
        issues = validation_module.validate(collection)
        assert any('at least one SimpleBake channel' in i.text for i in issues if i.level == 'ERROR')
        assert any('fake background' in i.text for i in issues if i.level == 'ERROR')
        assert any('Bump' in i.text for i in issues if i.level == 'WARNING')
        foreign = bpy.data.images.new('door_LCW_V2_Export_PBR_Diffuse_Wood_A', 4, 4)
        patch_validation(make_sbp())
        assert any('were not made by this tool' in i.text for i in validation_module.validate(collection)
                   if i.level == 'ERROR')
        foreign['bbe_owner'] = 'V2_Export'  # an image from an earlier run of this collection may be replaced
        assert not any('were not made by this tool' in i.text for i in validation_module.validate(collection))
        bpy.data.images.remove(foreign)
        mats['Rubber'].name = 'SBW_Rubber'
        assert any('SBW_' in i.text for i in validation_module.validate(collection) if i.level == 'ERROR')
        mats['Rubber'].name = 'Rubber'
        print('PASS babylon_bake_validation_protects_data')

        # --- full successful bake: three passes, only wood materials
        job, adapter, sbp = new_job(collection)
        sb_before = sb_values(sbp)
        job.start()
        assert job.total_passes == 3, job.total_passes
        assert run(job) == FINISHED, job.message
        assert [s['enabled'] for s in adapter.starts] == [
            {('door', 'Wood_A')}, {('door', 'Wood_B')}, {('door', 'Wood_C')}], adapter.starts
        assert all(s['objects'] == ['door'] for s in adapter.starts)
        assert {('door', 'Aluminium'), ('door', 'Rubber')} <= adapter.starts[0]['disabled']
        assert adapter.starts[1]['slots']['door'][:2] == ['Wood_B', 'Wood_B']
        assert adapter.starts[2]['slots']['door'][:2] == ['Wood_C', 'Wood_C']
        assert all(s['active_uv']['door'] == 'SimpleBake' for s in adapter.starts)
        assert all(not any(s['prefs'].values()) for s in adapter.starts), 'save/purge/shading suspended'
        forced = adapter.starts[0]['forced']
        assert forced['tex_per_mat'] and not forced['expand_mat_uvs'] and not forced['new_uv_option']
        assert not forced['copy_and_apply'] and not forced['auto_detect_udims']
        assert forced['keep_internal_after_export'] and forced['rough_glossy_switch'] == 'Roughness'
        for name in ('Wood_A', 'Wood_B', 'Wood_C'):
            baked = find_baked_material(mats[name], door, collection)
            assert baked is not None and baked.name == f'{name}_baked', name
            images = [n.image for n in baked.node_tree.nodes if n.type == 'TEX_IMAGE']
            assert {i['SB_this_bake'] for i in images} == {'Diffuse', 'Roughness', 'Normal'}
            assert all(i.get('bbe_owner') == 'V2_Export' for i in images)
        assert find_baked_material(mats['Aluminium'], door, collection) is None
        assert find_baked_material(mats['Glass_Panel'], glass, collection) is None
        assert 'texture(s) in' in job.message
        assert_restored(door, before, sbp, sb_before, adapter)
        print('PASS babylon_bake_three_variant_passes_restore')

        # --- export after bake: GLB with baked variants, plain materials original
        state = bpy.context.scene.lcw_babylon_export
        ok, message = run_export(collection, state)
        assert ok, (message, [i.text for i in state.issues])
        report = verify_glb(root / 'door_export.glb', expected_variants=3, require_variants=True)
        assert report['ok'], report['errors']
        names = {m.get('name') for m in report['document']['materials']}
        assert {'Wood_A_baked', 'Wood_B_baked', 'Wood_C_baked', 'Aluminium', 'Rubber', 'Glass_Panel'} <= names, names
        assert 'Wood_A' not in names
        assert not any(o.get('bbe_temp') for o in bpy.data.objects)
        print('PASS babylon_bake_then_export_glb')

        # --- second bake reuses materials, no duplicates
        material_count = len(bpy.data.materials)
        job, adapter, sbp = new_job(collection)
        job.start()
        assert run(job) == FINISHED, job.message
        assert len(bpy.data.materials) == material_count
        print('PASS babylon_bake_repeat_no_duplicate_materials')

        # --- SimpleBake refuses the second pass: failure, everything restored
        job, adapter, sbp = new_job(collection, fail_on_start=2)
        sb_before = sb_values(sbp)
        job.start()
        assert run(job) == FAILED and 'simulated SimpleBake refusal' in job.message, job.message
        assert_restored(door, before, sbp, sb_before, adapter)
        print('PASS babylon_bake_failure_restores')

        # --- a channel is missing from the bake result
        job, adapter, sbp = new_job(collection, channels=('Diffuse', 'Normal'))
        sb_before = sb_values(sbp)
        job.start()
        assert run(job) == FAILED and 'roughness' in job.message, job.message
        assert_restored(door, before, sbp, sb_before, adapter)
        print('PASS babylon_bake_missing_channel_fails')

        # --- cancel after the first pass
        job, adapter, sbp = new_job(collection)
        sb_before = sb_values(sbp)
        job.start()
        assert job.step() == RUNNING  # first pass started
        job.request_cancel()
        assert run(job) == CANCELLED, job.message
        assert len(adapter.starts) == 1
        assert_restored(door, before, sbp, sb_before, adapter)
        print('PASS babylon_bake_cancel_after_pass')

        # --- SimpleBake keeps "baking" while Blender bakes; then aborts silently
        now = [0.0]
        sbp = make_sbp()
        patch_validation(sbp)
        adapter = FakeAdapter(sbp, never_finish=True)
        job = BakeJob(collection, adapter=adapter, stall_seconds=30, clock=lambda: now[0])
        sb_before = sb_values(sbp)
        job.start()
        assert job.step() == RUNNING
        adapter.bake_running = True  # a real bake is rendering: never a stall
        now[0] = 500.0
        assert job.step() == RUNNING and slot_names(door)[:2] == ['Wood_A', 'Wood_A']
        adapter.bake_running = False  # macro aborted, flag stuck
        assert job.step() == RUNNING  # idle timer starts
        now[0] = 520.0
        assert job.step() == RUNNING
        now[0] = 531.0
        assert run(job) == FAILED and 'stopped during pass 1' in job.message, job.message
        assert adapter.stuck_cleared
        assert_restored(door, before, sbp, sb_before, adapter)
        print('PASS babylon_bake_watchdog_restores_after_stall')

        # --- add-on unregistered mid-job: originals restored; file load: prefs only
        job, adapter, sbp = new_job(collection)
        sb_before = sb_values(sbp)
        job.start()
        assert job.step() == RUNNING and slot_names(door)[:2] == ['Wood_A', 'Wood_A']
        assert job.step() == RUNNING  # still baking
        adapter.baking_ticks = 0
        bake_module.set_active_job(job)
        bake_module.abandon_active_job(restore_data=True)
        assert bake_module.active_job() is None and job.result == CANCELLED
        assert_restored(door, before, sbp, sb_before, adapter)
        job, adapter, sbp = new_job(collection)
        job.start()
        job.step()
        job.step()  # pass 2: variant material Wood_B assigned
        bake_module.set_active_job(job)
        bake_module.abandon_active_job(restore_data=False)
        assert adapter.prefs['saveonbake'] and adapter.prefs['purge_after_bake']
        job.finish(CANCELLED, 'test cleanup')  # emulate nothing left behind for later checks
        print('PASS babylon_bake_abandon_on_unregister_and_load')

        # --- nothing selected
        for item in collection.lcw_babylon_export.material_selections:
            item.bake = False
        job, adapter, sbp = new_job(collection)
        try:
            job.start()
            raise AssertionError('empty selection was accepted')
        except bake_module.BakeError as exc:
            assert 'No material is selected' in str(exc), exc
        assert adapter.saved is None, 'nothing may be touched before validation passes'
        print('PASS babylon_bake_requires_selection')
    print('PASS blender_babylon_bake')
finally:
    (validation_module.availability, validation_module.bake_properties,
     validation_module.simplebake_preferences) = originals
    bake_module.set_active_job(None)
    prefs.KHR_materials_variants_ui = old_variants_ui
    addon.unregister()
