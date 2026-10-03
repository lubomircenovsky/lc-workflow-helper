import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cad_mesh_tool.artifacts import publish_json


class CheckpointTests(unittest.TestCase):
    def test_sharing_conflict_retries_without_losing_previous_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'progress.json'
            path.write_text('{"previous": true}')
            original = Path.replace
            attempts = []

            def sharing_conflict(temporary, target):
                attempts.append(target)
                if len(attempts) < 3:
                    self.assertEqual(json.loads(path.read_text()), {'previous': True})
                    raise PermissionError('Reader holds old checkpoint')
                return original(temporary, target)

            with patch.object(Path, 'replace', sharing_conflict), patch('cad_mesh_tool.artifacts.time.sleep'):
                publish_json(path, {'completed': 4})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(json.loads(path.read_text()), {'completed': 4})

    def test_persistent_failure_is_reported_and_keeps_previous_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'progress.json'
            path.write_text('{"previous": true}')
            with patch.object(Path, 'replace', side_effect=PermissionError), patch('cad_mesh_tool.artifacts.time.sleep'):
                with self.assertRaises(PermissionError):
                    publish_json(path, {'completed': 4})
            self.assertEqual(json.loads(path.read_text()), {'previous': True})
            self.assertEqual(json.loads(path.with_suffix('.tmp').read_text()), {'completed': 4})


if __name__ == '__main__':
    unittest.main()
