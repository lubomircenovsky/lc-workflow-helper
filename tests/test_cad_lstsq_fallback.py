"""The private LAPACK shortcut and the public NumPy fallback give identical fits."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool import geometry


class LstsqFallback(unittest.TestCase):
    def test_probe_accepts_current_numpy_or_falls_back(self):
        # The shortcut stays enabled only when it was verified at import.
        if geometry._lapack is not None:
            self.assertTrue(geometry._private_lstsq_matches())

    def test_fallback_is_bit_identical(self):
        rng = np.random.default_rng(7)
        cases = [(rng.normal(size=(n, k)), rng.normal(size=n)) for n, k in ((5, 3), (40, 3), (12, 2), (3, 3))]
        cases.append((np.array([[1., 2., 3.], [2., 4., 6.], [1., 0., 1.]]), np.array([1., 2., .5])))
        fast = [geometry._lstsq(m, r) for m, r in cases]
        with patch.object(geometry, '_lapack', None):
            slow = [geometry._lstsq(m, r) for m, r in cases]
        for (a, ra), (b, rb) in zip(fast, slow):
            self.assertEqual(int(ra), int(rb))
            self.assertEqual(a.tobytes(), b.tobytes())

    def test_broken_private_api_is_rejected(self):
        class Broken:
            @staticmethod
            def lstsq(*args, **kwargs):
                raise TypeError('signature changed')

        with patch.object(geometry, '_lapack', Broken):
            self.assertFalse(geometry._private_lstsq_matches())


if __name__ == '__main__':
    unittest.main()
