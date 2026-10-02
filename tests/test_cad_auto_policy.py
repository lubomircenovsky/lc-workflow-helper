import unittest
from cad_mesh_tool.auto_policy import variants, fallback_variant, winner, completed_bodies


class AutoPolicyTests(unittest.TestCase):
    def test_timeout_keeps_validated_checkpoint_and_marks_unfinished_solids(self):
        done = dict(component_index=0, status='PASS', winner='done')
        active = dict(component_index=1, status='PASS', winner='best', reason='Valid geometry')
        report = dict(bodies=[done], active_body=active, partitions=[{}, {}, {}])
        self.assertEqual(completed_bodies(report), [done])
        results = completed_bodies(report, timed_out=True)
        self.assertEqual([r['status'] for r in results], ['PASS', 'REVIEW', 'FAIL'])
        self.assertEqual(results[1]['winner'], 'best')
        self.assertEqual(active['status'], 'PASS')
        report['selected_components'] = [1]
        report['bodies'] = []
        self.assertEqual(len(completed_bodies(report, True)), 1)
        report['active_body'] = dict(active, winner=None)
        self.assertEqual(completed_bodies(report, True)[0]['status'], 'FAIL')

    def test_bounded_relevant_variants(self):
        self.assertEqual(len(variants([])), 1)
        hole = dict(category='circular_hole')
        bend = dict(category='convex_arc')
        self.assertEqual(len(variants([bend])), 2)
        self.assertEqual(len(variants([hole,bend])), 3)
        self.assertIsNone(fallback_variant([hole,bend], [dict(variant='full',status='PASS',skipped=0)]))
        self.assertEqual(fallback_variant([hole,bend], [dict(variant='full',status='FAIL')])[0], 'holes_only')
        self.assertIsNone(fallback_variant([hole], [dict(variant='full',status='FAIL')]))

    def test_only_valid_final_geometry_can_win(self):
        small = dict(status='REVIEW', triangles=50, reduced=1, accepted=2, order=0)
        large = dict(status='PASS', triangles=100, reduced=10, accepted=10, order=1)
        failed = dict(status='FAIL', triangles=1)
        self.assertIs(winner([large,failed,small]), small)
        self.assertIsNone(winner([failed]))
        tied = dict(small, reduced=2, order=2)
        self.assertIs(winner([small,tied]), tied)
        accepted = dict(tied, accepted=3, order=3)
        self.assertIs(winner([small,tied,accepted]), accepted)


if __name__ == '__main__':unittest.main()
