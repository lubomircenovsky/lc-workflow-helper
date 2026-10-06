"""Pure tests for deterministic CAD operation selection and bounded recovery."""

import unittest

from cad_mesh_tool.errors import GeometricConflict
from cad_mesh_tool.operations import DEFAULTS, decision, normalize
from cad_mesh_tool.recovery import decisions, recover
from cad_mesh_tool.reporting import explain, skipped_summary


FEATURES = [
    dict(id=0, category='circular_hole', faces=[0], vertices=[0, 1]),
    dict(id=1, category='circular_hole', faces=[1], vertices=[2, 3]),
    dict(id=2, category='concave_arc', faces=[2], vertices=[4, 5]),
]


class OperationTests(unittest.TestCase):
    def test_supplemental_failure_preserves_established_reconstruction(self):
        features=FEATURES+[dict(id=3,category='concave_arc',faces=[3],
                               vertices=[0,4],measured_axis=True)]
        calls=[]
        def attempt(selected):
            calls.append([(f['id'],f['decision']) for f in selected])
            if any(f['id']==3 for f in selected):
                raise GeometricConflict('Conflicting shared analytic endpoint')
            return [f['id'] for f in selected if f['decision']=='REBUILD']
        result,skipped,count=recover(features,DEFAULTS,attempt,lambda _:None,max_attempts=4)
        self.assertEqual(result,[0,1,2])
        self.assertEqual(count,len(calls))
        self.assertEqual(count,2)
        self.assertEqual([r['feature'] for r in skipped],[3])
        self.assertTrue(skipped[0]['detected_not_reconstructed'])

    def test_supplemental_fallback_retains_disabled_and_forced_protection(self):
        features=FEATURES+[dict(id=3,category='outer_cylinder',faces=[3],
                               vertices=[0,4],measured_axis=True),
                           dict(id=4,category='concave_arc',faces=[4],vertices=[5],
                                measured_axis=True,forced_skip_reason='Protected junction'),
                           dict(id=5,category='concave_arc',faces=[5],vertices=[6],
                                measured_axis=True)]
        def attempt(selected):
            choices={f['id']:f['decision'] for f in selected}
            if 5 in choices:raise GeometricConflict('Conflicting shared analytic endpoint')
            self.assertEqual(choices[3],'DISABLED')
            self.assertEqual(choices[4],'SKIP')
            return choices
        _,skipped,count=recover(features,dict(DEFAULTS,outer_cylinders=False),
                                 attempt,lambda _:None,max_attempts=4)
        self.assertEqual({r['feature'] for r in skipped},{4,5})
        self.assertEqual(count,2)

    def test_dependent_bends_can_be_accepted_together(self):
        features=[dict(id=0,category='concave_arc',faces=[0],vertices=[0,1]),
                  dict(id=1,category='convex_arc',faces=[1],vertices=[1,2]),
                  dict(id=2,category='circular_hole',faces=[2],vertices=[3,4])]
        def attempt(selected):
            ids={f['id'] for f in selected if f['decision']=='REBUILD'}
            if 2 in ids or bool(0 in ids)!=bool(1 in ids):
                raise GeometricConflict('Protected dependency conflicts')
            return ids
        result,skipped,_=recover(features,DEFAULTS,attempt,lambda _result:None)
        self.assertEqual(result,{0,1})
        self.assertEqual([row['feature'] for row in skipped],[2])

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
                raise GeometricConflict('UNRESOLVED_PERIMETER: synthetic obstacle')
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
                raise GeometricConflict('UNRESOLVED_PERIMETER: synthetic obstacle')
            return selected

        result, skipped, count = recover(FEATURES, DEFAULTS, attempt, lambda _result: None,
                                         max_attempts=3)
        self.assertEqual(result, (0,))
        self.assertEqual([row['feature'] for row in skipped], [1, 2])
        self.assertEqual(count, 3)


if __name__ == '__main__':
    unittest.main()
