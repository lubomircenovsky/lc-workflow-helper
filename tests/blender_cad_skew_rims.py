"""Measured skew cuts: distinct rim intervals, strict boundary ownership."""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.rebuild import (
    _cylinder_rim_data, cylinder_rims, trimmed_level_rims,
)


def fixture():
    lower = np.linspace(.046, 2.463, 16)
    upper = np.linspace(0., 2.394, 31)
    angles = np.concatenate((lower, upper))
    points = np.array([[.08*math.cos(a), .08*math.sin(a), z]
                       for row, z in ((lower, 0.), (upper, .04)) for a in row])
    # One simple cycle, with no axial edge; the two closing rails are skew.
    ring = list(range(16)) + list(reversed(range(16, 47)))
    boundary = list(zip(ring, ring[1:]+ring[:1]))
    cy = dict(id=0, boundary=boundary, center=[0., 0.], radius=.08,
              start=0., span=2.463, full=False, lo=0., hi=.04)
    return cy, points, dict(enumerate(angles))


cy, points, angles = fixture()
expected = [list(range(16)), list(range(16, 47))]
assert trimmed_level_rims(cy, points, angles) == expected
assert [r[0] for r in cylinder_rims(cy, points)] == expected
assert _cylinder_rim_data(cy, points)[1]
# A measured subdivision on a skew rail is not a third end contour.
subdivided = np.vstack((points, (points[0]+points[16])*.5))
split = dict(cy, boundary=cy['boundary'][:-1]+[(16, 47), (47, 0)])
split_angles = dict(angles)
split_angles[47] = .023
assert trimmed_level_rims(split, subdivided, split_angles) == expected
assert [r[0] for r in cylinder_rims(split, subdivided)] == expected
# Reject a rail that doubles back axially, even though the cycle is connected.
folded = np.vstack((points, (points[0]+points[16])*.5,
                    (points[0]+points[16])*.5))
folded[47, 2], folded[48, 2] = .03, .01
split = dict(cy, boundary=cy['boundary'][:-1]+[(16, 48), (48, 47), (47, 0)])
split_angles[48] = .02
assert trimmed_level_rims(split, folded, split_angles) is None
# Edge order and orientation do not encode ownership or chain direction.
cy['boundary'] = [(b, a) for a, b in reversed(cy['boundary'])]
assert [r[0] for r in cylinder_rims(cy, points)] == expected

# A missing edge, branch, crossed rails, interior axial level or nonmonotone
# end chain must not turn an arbitrary boundary into a reconstructed strip.
cy, points, angles = fixture()
cy['boundary'].pop()
assert trimmed_level_rims(cy, points, angles) is None
cy, points, angles = fixture()
cy['boundary'].append((0, 2))
assert trimmed_level_rims(cy, points, angles) is None
cy, points, angles = fixture()
cy['boundary'][-1] = (16, 15)
cy['boundary'][15] = (0, 46)
assert trimmed_level_rims(cy, points, angles) is None
cy, points, angles = fixture()
points[5, 2] = .01
assert trimmed_level_rims(cy, points, angles) is None
cy, points, angles = fixture()
angles[3], angles[4] = angles[4], angles[3]
assert trimmed_level_rims(cy, points, angles) is None

# Conventional axial rails keep their original two-ring interpretation.
cy, points, angles = fixture()
lower = np.linspace(0., 2.394, 16)
points[:16, :2] = .08*np.column_stack((np.cos(lower), np.sin(lower)))
cy['span'] = 2.394
assert [r[0] for r in cylinder_rims(cy, points)] == expected
assert not _cylinder_rim_data(cy, points)[1]
print('CAD_SKEW_RIMS_OK')
