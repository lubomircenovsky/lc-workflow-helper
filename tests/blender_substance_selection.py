"""Selected source export, restoration, collection compatibility and optional real AO.

blender --background --factory-startup --python tests/blender_substance_selection.py
Add -- --baker-executable <path> to run real Substance info/AO integration too.
"""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.operators import substance_designer_baker as ops
from LC_workflow_addon.utils import substance_designer_baker as baker

arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--baker-executable', default='')
EXE = parser.parse_args(arguments).baker_executable


class SelectedSourceTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in tuple(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        self.temp = tempfile.TemporaryDirectory(prefix='lcw_selected_baker_')
        self.folder = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.state = bpy.context.scene.lcw_scene_state.substance_designer_baker
        self.state.input_mode = 'COLLECTION'
        self.state.target_collection = None
        self.state.use_lowdef_as_highdef = True
        self.state.output_root = str(self.folder / 'outputs')
        self.state.profile_id = ''
        self.prefs = SimpleNamespace(
            substance_baker_executable=EXE or sys.executable,
            substance_baker_workspace_root=str(self.folder / 'workspace'),
            substance_baker_backend_sal=True, substance_baker_backend_sora=True,
            substance_baker_texture_cache_size=4096, substance_baker_keep_meshes_in_cache=False,
            baker_profiles=[], active_baker_profile_index=0,
        )
        self.a = self.mesh('Selected_A')
        self.b = self.mesh('Selected_B')
        self.other = self.mesh('Not_Selected')
        self.empty = bpy.data.objects.new('Selected_Empty', None)
        bpy.context.collection.objects.link(self.empty)
        self.choose(self.a, self.b, self.empty, active=self.empty)

    def mesh(self, name):
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.object
        obj.name = name
        # Give the fixture two material subsets, including an excluded one.
        for name in ('BakeWood', 'occluder'):
            material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
            obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.material_index = polygon.index % 2
        return obj

    def choose(self, *objects, active=None):
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active

    def snapshot(self):
        return (
            tuple(sorted(o.name for o in bpy.context.selected_objects)),
            bpy.context.view_layer.objects.active,
            bpy.context.mode,
            tuple((o.name, o.mode, tuple(o.matrix_world[i][j] for i in range(4) for j in range(4)))
                  for o in sorted(bpy.data.objects, key=lambda o: o.name)),
            tuple((o.name, tuple(p.material_index for p in o.data.polygons),
                   tuple(m.name if m else None for m in o.data.materials),
                   tuple((uv.name, tuple(tuple(v.uv) for v in uv.data)) for uv in o.data.uv_layers))
                  for o in sorted(bpy.data.objects, key=lambda o: o.name) if o.type == 'MESH'),
            tuple(sorted(c.name for c in bpy.data.collections)),
        )

    def test_default_and_profiles_keep_scope_separate(self):
        self.assertEqual(self.state.input_mode, 'COLLECTION')
        self.assertNotIn('input_mode', baker.PROFILE_FIELD_NAMES)
        self.state.input_mode = 'SELECTED'
        profile = SimpleNamespace()
        baker.copy_profile_settings(self.state, profile)
        self.assertFalse(hasattr(profile, 'input_mode'))
        baker.apply_profile_to_bake_state(profile, self.state)
        self.assertEqual(self.state.input_mode, 'SELECTED')

    def test_validation_empty_nonmesh_and_valid_selection(self):
        self.state.input_mode = 'SELECTED'
        for objects in ((), (self.empty,)):
            errors, _ = baker.validate_baker_setup(
                sys.executable, None, state=self.state, selected_objects=objects)
            self.assertTrue(any('Select at least one mesh' in message for message in errors))
        errors, _ = baker.validate_baker_setup(
            sys.executable, None, state=self.state, selected_objects=(self.a, self.empty))
        self.assertEqual(errors, [])
        self.state.input_mode = 'COLLECTION'
        errors, _ = baker.validate_baker_setup(sys.executable, None, state=self.state)
        self.assertIn('No target collection selected.', errors)

    def test_snapshot_is_exact_and_frozen(self):
        self.state.input_mode = 'SELECTED'
        snapshot = baker.get_baker_input_objects(bpy.context, self.state)
        self.assertEqual(snapshot, (self.a, self.b))
        self.choose(self.other, active=self.other)
        self.assertEqual(snapshot, (self.a, self.b))
        self.assertEqual(baker.get_baker_input_objects(bpy.context, self.state), (self.other,))

    def test_collection_exporter_ignored_only_in_selected_mode(self):
        collection = bpy.data.collections.new('Stale_Collection')
        bpy.context.scene.collection.children.link(collection)
        self.state.target_collection = collection
        exporter = SimpleNamespace(name='FBX', filepath=str(self.folder / 'configured.fbx'))
        with patch.object(baker, '_iter_collection_exporters', return_value=[exporter]) as find:
            source = baker.get_baker_export_source(self.state, self.folder / 'internal.fbx')
            self.assertEqual(source['kind'], 'COLLECTION_EXPORTER')
            find.assert_called_once_with(collection)
        self.state.input_mode = 'SELECTED'
        # A real no-collection lookup must not use the stale collection's exporter.
        source = baker.get_baker_export_source(self.state, self.folder / 'internal.fbx')
        self.assertEqual(source['kind'], 'INTERNAL_FBX')
        self.assertIn('Selected Objects', source['label'])

    def test_export_keeps_selection_and_parented_world_transform(self):
        self.a.parent = self.empty
        self.empty.matrix_world = Matrix.Translation((12, -4, 3))
        self.a.location = (2, 1, 0)
        self.b.location = (-3, 2, 5)
        bpy.context.view_layer.update()
        self.state.input_mode = 'SELECTED'
        selected = baker.get_baker_input_objects(bpy.context, self.state)
        before = self.snapshot()
        path = baker.export_objects_to_fbx(bpy.context, selected, self.folder / 'selected.fbx')
        self.assertEqual(self.snapshot(), before)
        original = set(bpy.data.objects)
        bounds = {o.name: sorted(tuple(o.matrix_world @ Vector(v)) for v in o.bound_box)
                  for o in selected}
        bpy.ops.import_scene.fbx(filepath=str(path))
        imported = [o for o in bpy.data.objects if o not in original and o.type == 'MESH']
        self.assertEqual(len(imported), 2)
        for obj in imported:
            original_name = obj.name.rsplit('.', 1)[0]
            imported_bounds = sorted(tuple(obj.matrix_world @ Vector(v)) for v in obj.bound_box)
            for actual, expected in zip(imported_bounds, bounds[original_name]):
                for a, e in zip(actual, expected):
                    self.assertAlmostEqual(a, e, places=4)

    def test_export_without_active_object(self):
        self.choose(self.a, active=None)
        before = self.snapshot()
        baker.export_objects_to_fbx(bpy.context, (self.a,), self.folder / 'no_active.fbx')
        self.assertEqual(self.snapshot(), before)

    def test_edit_mode_restored_on_success_and_failure(self):
        self.choose(self.a, self.b, active=self.a)
        bpy.ops.object.mode_set(mode='EDIT')
        before = self.snapshot()
        baker.export_objects_to_fbx(bpy.context, (self.a, self.b), self.folder / 'edit.fbx')
        self.assertEqual(self.snapshot(), before)

        def fail(*_args, **_kwargs):
            bpy.ops.object.mode_set(mode='OBJECT')
            raise RuntimeError('Injected export failure')

        # bpy.ops creates its wrappers on demand; patch the Python exporter body.
        from io_scene_fbx import export_fbx_bin
        with patch.object(export_fbx_bin, 'save_single', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'Injected'):
                baker.export_objects_to_fbx(bpy.context, (self.a,), self.folder / 'failure.fbx')
        self.assertEqual(self.snapshot(), before)

    def test_selected_preview_bypasses_collection_export_and_uses_current_scope(self):
        self.state.input_mode = 'SELECTED'
        info = 'Mesh: Test\n  Path: /root/Selected_A/Test\n  Material ID: BakeWood\n'
        with patch.object(ops, '_preferences', return_value=self.prefs), \
                patch.object(ops, 'timestamp_job_id', return_value='same-second'), \
                patch.object(ops, 'run_baker_command', return_value=SimpleNamespace(
                    returncode=0, stdout=info, stderr='')), \
                patch.object(ops, 'export_collection_for_baker') as collection_export, \
                patch.object(ops, 'export_objects_to_fbx') as selected_export:
            ops._export_and_collect_preview(bpy.context)
            self.assertEqual(selected_export.call_args.args[1], (self.a, self.b))
            first_path = selected_export.call_args.args[2]
            self.choose(self.other, active=self.other)
            ops._export_and_collect_preview(bpy.context)
            self.assertEqual(selected_export.call_args.args[1], (self.other,))
            self.assertNotEqual(selected_export.call_args.args[2], first_path)
            collection_export.assert_not_called()
            paths = ops._job_paths(bpy.context, 'path_test')
            self.assertEqual(paths['export_path'].name, 'Selected_Objects.fbx')
            self.assertEqual(paths['output_dir'].name, 'Selected_Objects')

    def test_naming_warning_uses_selected_meshes(self):
        self.a.name = 'Chair_low'
        self.state.use_lowdef_as_highdef = False
        self.state.projection_match_mode = 'match_mesh_name'
        high = bpy.data.collections.new('High')
        bpy.context.scene.collection.children.link(high)
        self.b.name = 'Chair_high'
        high.objects.link(self.b)
        self.state.high_poly_collection = high
        self.assertEqual(ops._naming_warnings(self.state, (self.a,)), [])
        self.assertIn('no low meshes', ops._naming_warnings(self.state, (self.other,))[0])

    @unittest.skipUnless(EXE, 'Pass -- --baker-executable to enable real AO')
    def test_real_selected_export_preview_and_ao_all_groupings(self):
        self.state.input_mode = 'SELECTED'
        self.state.output_size_x = self.state.output_size_y = '128'
        self.state.secondary_sample_count = 4
        self.state.uv_set = 0
        self.state.output_format = 'png'
        self.state.use_lowdef_as_highdef = True
        before = self.snapshot()
        with patch.object(ops, '_preferences', return_value=self.prefs):
            for mode, count in [('OBJECTS_TOGETHER', 2), ('MATERIALS_TOGETHER', 2),
                                ('ALL_EXCEPT_EXCLUDED', 1)]:
                self.state.selection_mode = mode
                self.state.excluded_material_pattern = 'occluder'
                path, source, meshes, preview = ops._export_and_collect_preview(bpy.context)
                self.assertEqual(source['kind'], 'INTERNAL_FBX')
                self.assertEqual({m['ObjectName'] for m in meshes}, {'Selected_A', 'Selected_B'})
                plan = baker.build_bake_plan('Selected_Objects', path, self.folder / mode,
                                             self.prefs, self.state, preview['groups'])
                result = baker.execute_bake_plan(plan, EXE, self.folder / f'{mode}.log')
                self.assertTrue(result['success'], result['message'])
                self.assertEqual(len(result['baked_files']), count)
                self.assertEqual(self.snapshot(), before)
                print('REAL_SELECTED_AO', mode, count)


if __name__ == '__main__':
    addon.register()
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelectedSourceTests))
        if not result.wasSuccessful():
            raise SystemExit(1)
    finally:
        addon.unregister()
    print('PASS Substance selected source')
