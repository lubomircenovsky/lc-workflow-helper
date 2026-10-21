"""Substance info parsing and truthful bake completion (Blender 5.2)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from LC_workflow_addon.utils import substance_designer_baker as baker


INFO = '''Mesh: Frame
  Path: /root/door/Frame
  GeomSubset "/root/door/Frame/Frame_sub0"
    Material ID: Wood
  GeomSubset "/root/door/Frame/Frame_sub1"
    Material ID: Occluder
Mesh: Pane
  Path: /root/glass/Pane
  Material ID: Glass
'''


class SubstanceBakerTests(unittest.TestCase):
    def test_subsets_and_single_material_mesh(self):
        rows = baker.parse_baker_info(INFO)
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['MaterialId'] for r in rows], ['Wood', 'Occluder', 'Glass'])
        self.assertEqual(rows[0]['MeshPath'], '/root/door/Frame/Frame_sub0')
        self.assertEqual(rows[1]['ObjectName'], 'door')
        self.assertEqual(rows[2]['MeshPath'], '/root/glass/Pane')

    def test_all_selection_modes_keep_correct_paths(self):
        rows = baker.parse_baker_info(INFO)
        for mode, count in [('OBJECTS_TOGETHER', 2), ('MATERIALS_TOGETHER', 3),
                            ('ALL_EXCEPT_EXCLUDED', 2)]:
            with self.subTest(mode=mode):
                state = SimpleNamespace(selection_mode=mode, excluded_material_pattern='occluder')
                preview = baker.build_preview_data(rows, state)
                self.assertEqual(preview['group_count'], count)
                paths = [p for g in preview['groups'] for p in g['selected_meshes']]
                self.assertIn('/root/door/Frame/Frame_sub0', paths)
                self.assertEqual('/root/door/Frame/Frame_sub1' in paths, mode != 'ALL_EXCEPT_EXCLUDED')

    def execute(self, folder, result, *, create=False):
        plan = {'Common': {'output_dir': str(folder), 'output_format': 'png'},
                'Bakers': [{'Label': 'AO', 'GroupName': 'door', 'OutputName': 'door_ao'}]}

        def run(*_args, **_kwargs):
            if isinstance(result, Exception):
                raise result
            if create:
                (folder / 'door_ao.png').write_bytes(b'new PNG data')
            return result

        with patch.object(baker, '_bake_command_from_plan', return_value=['AO']), \
                patch.object(baker, 'run_baker_command', side_effect=run):
            return baker.execute_bake_plan(plan, 'baker.exe', folder / 'bake.log')

    def test_error_with_zero_returncode_is_failure(self):
        for channel in ('stdout', 'stderr'):
            with tempfile.TemporaryDirectory() as root, self.subTest(channel=channel):
                result = subprocess.CompletedProcess([], 0, '', '')
                setattr(result, channel, '[ERROR][Bakers]No mesh found in the usd stage with the given selection')
                outcome = self.execute(Path(root), result)
                self.assertFalse(outcome['success'])
                self.assertIn('No mesh found', outcome['message'])

    def test_no_output_and_stale_output_are_failures(self):
        for stale in (False, True):
            with tempfile.TemporaryDirectory() as root, self.subTest(stale=stale):
                folder = Path(root)
                if stale:
                    (folder / 'door_ao.png').write_bytes(b'old output')
                outcome = self.execute(folder, subprocess.CompletedProcess([], 0, '', ''))
                self.assertFalse(outcome['success'])
                self.assertIn('No new or updated output', outcome['message'])

    def test_fresh_output_succeeds(self):
        with tempfile.TemporaryDirectory() as root:
            outcome = self.execute(Path(root), subprocess.CompletedProcess([], 0, '', ''), create=True)
            self.assertTrue(outcome['success'])
            self.assertEqual(len(outcome['baked_files']), 1)

    def test_process_exception_is_logged(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            outcome = self.execute(folder, FileNotFoundError('Executable missing'))
            self.assertFalse(outcome['success'])
            self.assertIn('Executable missing', (folder / 'bake.log').read_text())

    def test_missing_uv_diagnostic_is_visible(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.CompletedProcess([], 0, '',
                '[WARNING][Bakers]mesh is missing some mandatory attribute(s): UV1, skipping it\n'
                '[ERROR][Bakers]No mesh in the scene is meeting the requirements.')
            outcome = self.execute(Path(root), result)
            self.assertIn('UV1', outcome['message'])

    def test_partially_skipped_uvs_do_not_report_success(self):
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.CompletedProcess([], 0, '',
                '[WARNING][Bakers]mesh is missing some mandatory attribute(s): UV1, skipping it')
            outcome = self.execute(Path(root), result, create=True)
            self.assertFalse(outcome['success'])
            self.assertIn('UV1', outcome['message'])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SubstanceBakerTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    print('PASS Substance baker regression')
