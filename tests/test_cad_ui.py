"""Pure CAD UI copy and run-file ownership tests."""

import json
import tempfile
import unittest
from pathlib import Path

from cad_reconstruction import run_files, ui_text


class RunFileTests(unittest.TestCase):
    def test_delete_only_verified_direct_child(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            base = Path(directory)
            root = base / "runs"
            root.mkdir()
            valid = root / ("a" * 32)
            valid.mkdir()
            profile = {"method": "A", "delivery": "EDITABLE_NGONS",
                       "code_hash": "a" * 64, "source_hash": "b" * 64}
            (valid / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
            (valid / "source.json").write_text("large snapshot need not be parsed", encoding="utf-8")
            (valid / "worker.log").write_text("log", encoding="utf-8")
            foreign = root / ("b" * 32)
            foreign.mkdir()
            (foreign / "source.json").write_text("foreign", encoding="utf-8")
            outside = base / ("c" * 32)
            outside.mkdir()
            (outside / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
            (outside / "source.json").write_text("outside", encoding="utf-8")
            self.assertEqual(run_files.find_owned_runs(root), [valid])
            for path in (root, foreign, outside):
                with self.assertRaises(ValueError):
                    run_files.delete_owned_run(root, path)
            run_files.delete_owned_run(root, valid)
            self.assertFalse(valid.exists())
            self.assertTrue(root.is_dir() and foreign.is_dir() and outside.is_dir())

    def test_wrong_marker_and_uuid_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            root = Path(directory)
            bad = root / ("e" * 32)
            bad.mkdir()
            (bad / "source.json").write_text("{}", encoding="utf-8")
            (bad / "profile.json").write_text(json.dumps({"method": "A"}), encoding="utf-8")
            self.assertFalse(run_files.is_owned_run(root, bad))
            bad.rename(root / "not-a-run-id")
            self.assertEqual(run_files.find_owned_runs(root), [])


class CopyTests(unittest.TestCase):
    def test_short_analysis_text(self):
        issue = "Part: CAD source must be a closed manifold mesh (boundary=2, nonmanifold=1)."
        self.assertIn("2 open edges", ui_text.analysis_issue(issue))
        self.assertIn("Part", ui_text.analysis_issue(issue))
        self.assertIn("Repair mesh first", ui_text.analysis_issue(issue))
        nonmanifold_only = "Part: CAD source must be a closed manifold mesh (nonmanifold=1)."
        self.assertIn("Guarded mode", ui_text.analysis_issue(nonmanifold_only))
        self.assertEqual(ui_text.analysis_issue("Part: unapplied modifiers"),
                         "Part: Apply modifiers first.")
        self.assertIn("negative scale", ui_text.analysis_note("Part: negative scale").lower())


if __name__ == "__main__":
    unittest.main()
