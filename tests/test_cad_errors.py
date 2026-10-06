"""Recovery decides by exception type; guard against untyped recoverable raises."""
import re
import unittest
from pathlib import Path

from cad_mesh_tool.errors import GeometricConflict, StageRejected
from cad_mesh_tool.recovery import is_geometric_conflict

# Messages that the old prefix matcher treated as recoverable conflicts.
LEGACY_RECOVERABLE = (
    "UNRESOLVED_PERIMETER", "Candidate topology failed", "Protected feature geometry changed",
    "Protected dependency conflicts", "Checkpoint validation failed", "Blender had to repair candidate mesh",
    "Too few independent rim samples", "No ordered rim sample mapping", "Conflicting shared", "Shared retained/deleted",
    "Unmapped nonplanar", "Transition contraction", "Unsupported nonplanar incident patch",
    "Planar boundary contraction", "Collapsed incident patch", "Planar coverage mismatch",
    "Cannot propagate a perimeter subdivision", "CDT created ambiguous", "Branching cylinder", "Expected two cylinder",
    "Cylinder end contour", "Degenerate face", "Protected non-manifold region changed",
    "Material boundary in planar patch", "Shading boundary in planar patch", "Region boundary branches or is open",
    "Non-simple boundary", "Measured cylinder end contours", "Conflicting nested edge subdivisions",
    "Self-touching nested edge subdivisions", "Cannot propagate subdivisions",
)
LEGACY_STAGE = ("Protected faces lost", "Cleanup changed vertices", "Invalid triangulation in protected detail",
                "Local n-gon repair changed topology", "Straight wall")
CORE = Path(__file__).resolve().parents[1]/'cad_mesh_tool'


class ErrorTypeTests(unittest.TestCase):
    def test_type_not_message_decides_recovery(self):
        self.assertTrue(is_geometric_conflict(GeometricConflict('reworded message')))
        self.assertFalse(is_geometric_conflict(ValueError('Conflicting shared analytic endpoint')))
        self.assertFalse(is_geometric_conflict(StageRejected('Straight wall cleanup changed topology')))
        self.assertTrue(issubclass(GeometricConflict, ValueError))
        self.assertTrue(issubclass(StageRejected, ValueError))

    def test_no_untyped_raise_uses_a_recoverable_message(self):
        pattern = re.compile(r"ValueError\(f?['\"]([^'\"]*)")
        offenders = []
        for path in sorted(CORE.glob('*.py')):
            for number, line in enumerate(path.read_text(encoding='utf8').splitlines(), 1):
                for message in pattern.findall(line):
                    if message.startswith(LEGACY_RECOVERABLE + LEGACY_STAGE):
                        offenders.append(f'{path.name}:{number}: {message}')
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
