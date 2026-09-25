"""Pure tests for deterministic CAD operation selection and bounded recovery."""

import unittest

from cad_mesh_tool.operations import DEFAULTS, decision, normalize
from cad_mesh_tool.recovery import decisions, recover
from cad_mesh_tool.reporting import explain, skipped_summary


FEATURES = [
    dict(id=0, category='circular_hole', faces=[0], vertices=[0, 1]),
    dict(id=1, category='circular_hole', faces=[1], vertices=[2, 3]),
    dict(id=2, category='concave_arc', faces=[2], vertices=[4, 5]),
]


class OperationTests(unittest.TestCase):
    def test_shading_skip_has_actionable_reason(self):
        reason = 'Shading boundary in planar patch'
        self.assertIn('Face directions', explain(reason))
        self.assertIn('custom normals are already ignored', explain(reason))
        self.assertEqual(
            skipped_summary([{'reason': reason}, {'reason': reason}]),
            '2 feature(s) skipped: face directions conflict in a flat region.',
        )
        mixed = skipped_summary([{'reason': reason}, {'reason': 'UNRESOLVED_PERIMETER'}])
        self.assertIn('1 other feature(s)', mixed)

    def test_defaults_and_invalid_options(self):
        self.assertEqual(normalize(), DEFAULTS)
        with self.assertRaises(ValueError):
            normalize({'unknown': True})
        with self.assertRaises(ValueError):
            normalize({name: False for name in DEFAULTS})

    def test_arc_and_outer_cylinder_switches_are_independent(self):
        options = dict(DEFAULTS, arcs=False, outer_cylinders=True, circular_holes=False)
        self.assertEqual(decision('concave_arc', options), 'DISABLED')
        self.assertEqual(decision('convex_arc', options), 'DISABLED')
        self.assertEqual(decision('outer_cylinder', options), 'REBUILD')
        self.assertEqual(decision('circular_hole', options), 'PERIMETER_ONLY')
        self.assertEqual(decisions(FEATURES, options)[2]['decision'], 'DISABLED')

    def test_preserve_curve_segmentation_keeps_only_perimeter_decision(self):
        options = dict(DEFAULTS)
        self.assertEqual(decision('circular_hole', options), 'REBUILD')
        self.assertEqual(decision('circular_hole', options, True), 'PERIMETER_ONLY')
        self.assertEqual(decision('concave_arc', options, True), 'DISABLED')
        self.assertEqual(decision('outer_cylinder', options, True), 'DISABLED')
        options['perimeter_loops'] = False
        self.assertEqual(decision('circular_hole', options, True), 'DISABLED')

    def test_skip_only_conflicting_feature(self):
        calls = []

        def attempt(features):
            selected = tuple(f['id'] for f in features if f['decision'] == 'REBUILD')
            calls.append(selected)
            if 1 in selected:
                raise ValueError('UNRESOLVED_PERIMETER: synthetic obstacle')
            return selected

        result, skipped, count = recover(FEATURES, DEFAULTS, attempt, lambda _result: None)
        self.assertEqual(result, (0, 2))
        self.assertEqual([row['feature'] for row in skipped], [1])
        self.assertEqual(count, len(calls))
        self.assertEqual(calls[0], (0, 1, 2))

    def test_program_error_is_not_a_geometric_skip(self):
        with self.assertRaisesRegex(RuntimeError, 'bug'):
            recover(FEATURES, DEFAULTS, lambda _features: (_ for _ in ()).throw(RuntimeError('bug')),
                    lambda _result: None)

    def test_recovery_limit_keeps_valid_prefix(self):
        def attempt(features):
            selected = tuple(f['id'] for f in features if f['decision'] == 'REBUILD')
            if 1 in selected:
                raise ValueError('UNRESOLVED_PERIMETER: synthetic obstacle')
            return selected

        result, skipped, count = recover(FEATURES, DEFAULTS, attempt, lambda _result: None,
                                         max_attempts=3)
        self.assertEqual(result, (0,))
        self.assertEqual([row['feature'] for row in skipped], [1, 2])
        self.assertEqual(count, 3)


if __name__ == '__main__':
    unittest.main()
