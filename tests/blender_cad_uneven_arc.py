"""Regression for strongly uneven rim angles and stable alias ordering."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.rebuild import rim_aliases, select_rim_samples


ids = [10, 11, 12, 13]
angles = [0., .07102548, math.pi, 3.21261814]
theta = dict(zip(ids, angles))
row = select_rim_samples(ids, theta, 4, angles[-1], False)
assert row == ids
assert rim_aliases(ids, row, theta, False) == {i: i for i in ids}

# Unselected vertices choose the nearest actual retained sample, not an
# artificial uniform target. The resulting map is monotonic along the rim.
ids = [10, 20, 30, 40, 50, 60]
theta = dict(zip(ids, [0., .071, .08, 1.8, math.pi, 3.2126]))
row = [10, 20, 50, 60]
aliases = rim_aliases(ids, row, theta, False)
assert all(aliases[i] == i for i in row)
assert [row.index(aliases[i]) for i in ids] == sorted(row.index(aliases[i]) for i in ids)
assert aliases[30] == 20
assert aliases[40] == 50
print('CAD_UNEVEN_ARC_ALIAS_OK')
