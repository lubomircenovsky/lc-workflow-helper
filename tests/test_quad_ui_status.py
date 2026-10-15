"""Quad Reconstruction result severity presentation rules (pure, no bpy)."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from quad_reconstruction import ui_status


def item(**overrides):
    """A fully validated reconstruction; tests override single fields."""
    values = dict(
        status="RECONSTRUCTED", details="", classification="MIXED_TRI_QUAD",
        fingerprint_unchanged=True, warning_count=0, validation_passed=True,
        solver_exact=True, relaxation_count=0, unresolved_triangle_count=0,
        confidence_label="HIGH",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class QuadResultStatusTests(unittest.TestCase):
    def kind(self, output_available=True, **overrides):
        return ui_status.result_status(item(**overrides), output_available).kind

    def test_fully_validated_is_ok(self):
        result = ui_status.result_status(item(), True)
        self.assertEqual((result.kind, result.text), ("ok", "Validated"))

    def test_failed_wins_over_everything(self):
        result = ui_status.result_status(item(status="FAILED", details="boom", fingerprint_unchanged=False), False)
        self.assertEqual(result.kind, "error")
        self.assertIn("FAILED", result.text)
        self.assertIn("boom", result.text)

    def test_broken_fingerprint(self):
        for status in ("ANALYZED", "RECONSTRUCTED"):
            result = ui_status.result_status(item(status=status, fingerprint_unchanged=False), True)
            self.assertEqual((result.kind, result.text), ("error", "Source integrity check failed"), status)

    def test_analyzed(self):
        self.assertEqual(self.kind(status="ANALYZED", validation_passed=False), "info")
        result = ui_status.result_status(item(status="ANALYZED", warning_count=3), True)
        self.assertEqual(result.kind, "warning")
        self.assertIn("3 warning", result.text)
        self.assertIn("Mixed Tri Quad", ui_status.result_status(item(status="ANALYZED"), True).text)

    def test_validation_failed_before_missing_output(self):
        self.assertEqual(self.kind(False, validation_passed=False), "error")

    def test_missing_output(self):
        result = ui_status.result_status(item(), False)
        self.assertEqual(result.kind, "warning")
        self.assertIn("Output unavailable", result.text)

    def test_review_reasons(self):
        for overrides, needle in (
            (dict(solver_exact=False), "fallback solver"),
            (dict(relaxation_count=2), "2 relaxation"),
            (dict(unresolved_triangle_count=5), "5 unresolved"),
            (dict(warning_count=1), "1 warning"),
            (dict(confidence_label="MEDIUM"), "MEDIUM confidence"),
            (dict(confidence_label=""), "unknown confidence"),
        ):
            result = ui_status.result_status(item(**overrides), True)
            self.assertEqual(result.kind, "warning", overrides)
            self.assertIn("review", result.text)
            self.assertIn(needle, result.text)

    def test_other_status_is_idle(self):
        for status in ("", "PENDING"):
            self.assertEqual(self.kind(status=status), "idle")

    def test_batch_status(self):
        expected = {
            "IDLE": "idle", "ANALYZING": "running", "RECONSTRUCTING": "running",
            "ANALYZED": "info", "RECONSTRUCTED": "info", "FAILED": "error",
            "CANCELLED": "cancelled",
        }
        for job_status, kind in expected.items():
            self.assertEqual(ui_status.batch_status(job_status)[0], kind, job_status)
        self.assertNotEqual(ui_status.batch_status("RECONSTRUCTED")[0], "ok")
        self.assertEqual(ui_status.batch_status("NEW_STATE"), ("idle", "New State"))


if __name__ == "__main__":
    unittest.main()
