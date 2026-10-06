"""Exact near-collinear CDT regression and compact contour-support checks."""
import sys
import math
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.rebuild import tessellation, choose_perimeter, annulus_quality, contacts


# Minimal polygon reduced from .057/Solid001. Float32 CDT centroids admitted
# triangle (0,1,2) outside the actual polygon, adding two non-manifold edges.
ring = np.array([[5.217013120651244,.145564948033552],
                 [5.217013120651244,-.004283715025786489],
                 [5.217013120651249,-.2542834062720477],
                 [5.137043449790129,-.2542834062720486],
                 [5.1370434497901245,.1455649480335511]])
_, faces = tessellation([ring])
edges = Counter(tuple(sorted((a,b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
boundary = {tuple(sorted((i,(i+1)%len(ring)))) for i in range(len(ring))}
assert len(faces) == 3, faces
assert {e for e,n in edges.items() if n==1} == boundary
assert all(n==1 if e in boundary else n==2 for e,n in edges.items())

# A narrow round domain cannot contain a square but can contain a valid ring.
theta = np.arange(16)*math.tau/16
hole = .02*np.column_stack((np.cos(theta), np.sin(theta)))
outer = .023*np.column_stack((np.cos(theta), np.sin(theta)))
support, attempts = choose_perimeter(hole, outer, [], .02, np.zeros(2), .0015)
assert support is not None and attempts[-1]['shape']=='contour', attempts
assert annulus_quality(support,hole)<=20 and not contacts(support,outer)
assert math.isclose(attempts[-1]['size']-.02,.0015)
# An obstacle occupying the available ring cannot be silently crossed.
blocked, attempts = choose_perimeter(hole, outer, [outer*.98], .02, np.zeros(2), .0015)
assert blocked is None
# A narrow elongated cutout needs an offset contour rather than a bounding square.
theta = np.arange(32)*math.tau/32
compound = np.column_stack((.02*np.cos(theta), .006*np.sin(theta)))
domain = np.column_stack((.024*np.cos(theta), .009*np.sin(theta)))
support, attempts = choose_perimeter(compound, domain, [], None, np.zeros(2), .0015)
assert support is not None and attempts[-1]['shape']=='contour', attempts
assert annulus_quality(support,compound)<=20 and not contacts(support,domain)
print('CAD_REGION_BOUNDARIES_OK')
print('PASS blender_cad_region_boundaries')
