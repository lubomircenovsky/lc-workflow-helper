"""CAD result severity presentation rules (pure, no bpy)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cad_reconstruction import ui_status


class CadResultStatusTests(unittest.TestCase):
    def test_result_status_table(self):
        cases = {
            ("PENDING", False): ("idle", "PENDING"),
            ("RUNNING", False): ("running", "RUNNING"),
            ("PASS", False): ("ok", "PASS"),
            ("REVIEW", False): ("warning", "REVIEW"),
            ("REVIEW", True): ("warning", "PARTIAL / REVIEW"),
            ("FAIL", False): ("error", "FAIL"),
            ("FAIL", True): ("error", "FAIL"),
            ("", False): ("idle", "Unknown status"),
        }
        for (status, partial), expected in cases.items():
            self.assertEqual(ui_status.result_status(status, partial), expected, status)

    def test_unknown_status_keeps_raw_value_in_text(self):
        kind, text = ui_status.result_status("WEIRD", False)
        self.assertEqual(kind, "idle")
        self.assertIn("WEIRD", text)

    def test_analysis_lines(self):
        self.assertEqual(ui_status.analysis_line_status("BLOCKER"), "error")
        self.assertEqual(ui_status.analysis_line_status("NOTE"), "info")
        self.assertEqual(ui_status.analysis_line_status(""), "info")
        self.assertEqual(ui_status.analysis_line_text("BLOCKER", "Cube: Repair."), "BLOCKER: Cube: Repair.")
        self.assertEqual(ui_status.analysis_line_text("NOTE", "Cube: ok."), "Cube: ok.")
        self.assertEqual(ui_status.analysis_summary_status(0), "ok")
        self.assertEqual(ui_status.analysis_summary_status(2), "error")


if __name__ == "__main__":
    unittest.main()
