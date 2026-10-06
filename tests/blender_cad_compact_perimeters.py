"""Compact support boundaries retain exact manual clearance and quality gates."""
import math
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.rebuild import choose_perimeter, annulus_quality, contacts


radius = .1875
theta = np.arange(25)*math.tau/25
hole = radius*np.column_stack((np.cos(theta), np.sin(theta)))
original = hole.copy()
outer = np.array([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.]])
manual, history = choose_perimeter(hole, outer, [], radius, np.zeros(2), .004)
assert manual is not None
assert math.isclose(history[-1]['size']-radius, .004, abs_tol=1e-12)
assert len(manual) < 32, len(manual)
assert annulus_quality(manual, hole) <= 20
auto, history = choose_perimeter(hole, outer, [], radius, np.zeros(2))
assert auto is not None and len(auto) <= 8, len(auto)
assert history[-1]['size']-radius > .004
assert annulus_quality(auto, hole) <= 20
assert np.array_equal(hole, original)

# A fixed clearance that cannot fit must not be silently decreased. Auto can
# find a smaller safe support, and neither mode may cross neighboring features.
narrow = np.array([[-.22, -.22], [.22, -.22], [.22, .22], [-.22, .22]])
blocked, _ = choose_perimeter(hole, narrow, [], radius, np.zeros(2), .04)
assert blocked is None
fitted, _ = choose_perimeter(hole, narrow, [], radius, np.zeros(2))
assert fitted is not None and not contacts(fitted, narrow)
blocked, _ = choose_perimeter(hole, outer, [outer*.9], radius, np.zeros(2))
assert blocked is None

# A topologically rejected proposal has infinite internal quality, but its
# diagnostic must remain serializable by the immutable-artifact writer.
from unittest.mock import patch
import cad_mesh_tool.rebuild as rebuild
quality = rebuild.annulus_quality
calls = 0
def rejected_first(outer_ring, inner_ring):
    global calls
    calls += 1
    return float('inf') if calls == 1 else quality(outer_ring, inner_ring)
with patch.object(rebuild, 'annulus_quality', rejected_first):
    support, history = choose_perimeter(hole, outer, [], radius, np.zeros(2), .004)
assert support is not None and any(a.get('q', 0) is None for a in history)
json.dumps(history, allow_nan=False)

# Optional immutable production fixture: a tilted plane exposed round-trip
# noise that inserted near-zero triangles along otherwise straight supports.
if '--' in sys.argv:
    root=Path(sys.argv[sys.argv.index('--')+1])
    from cad_mesh_tool.rebuild import reconstruct
    from cad_mesh_tool.recovery import decisions
    from cad_mesh_tool.source_repair import repair_collinear_faces
    source=json.loads((root/'source.json').read_text())
    source,_=repair_collinear_faces(source)
    profile=json.loads((root/'profile.json').read_text())
    features=json.loads((root/'plan.json').read_text())['features']
    features=decisions(features,profile['operations'],preserve_curve_segmentation=True)
    candidate=reconstruct(source,features,profile['operations'],
                          preserve_curve_segmentation=True,preferred_clearance_m=.004)
    assert len(candidate['perimeters'])==20
    assert all(not candidate['topology'][k] for k in ('boundary','nonmanifold','winding','duplicates'))
    assert all(math.isclose(p['clearance_m'],.004,abs_tol=1e-12) for p in candidate['perimeters'])
print('CAD_COMPACT_PERIMETERS_OK', len(manual), len(auto))
