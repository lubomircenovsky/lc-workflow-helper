"""Geometry primitives shared by detection, reconstruction and tests (SI units)."""
import math
from collections import defaultdict, Counter
import numpy as np
from .errors import GeometricConflict


def unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    if n < 1e-15:
        raise ValueError('Degenerate direction')
    return v / n


def basis(axis):
    z = unit(axis)
    u = np.eye(3)[np.argmin(abs(z))]
    u = unit(u - (u @ z) * z)
    return np.array([u, np.cross(z, u), z])


def face_normals(v, faces):
    """Unit Newell-style fan normals. Triangles are batched; the per-face
    arithmetic (cross product, x.dot(x) norm, division) is unchanged."""
    v = np.asarray(v, dtype=float)
    result = np.empty((len(faces), 3))
    triangles = [index for index, f in enumerate(faces) if len(f) == 3]
    if triangles:
        p = v[np.asarray([faces[index] for index in triangles])]
        # '+ 0.0' matches the reference .sum(0), which turns -0.0 into +0.0.
        normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]) + 0.0
        for row, index in zip(normals, triangles):
            result[index] = row / max(np.sqrt(row.dot(row)), 1e-30)
    for index, f in enumerate(faces):
        if len(f) == 3:
            continue
        p = v[f]
        n = np.cross(p[1:-1] - p[0], p[2:] - p[0]).sum(0)
        result[index] = n / max(np.linalg.norm(n), 1e-30)
    return result


def adjacency(faces):
    ef = defaultdict(list)
    for fi, f in enumerate(faces):
        for a, b in zip(f, f[1:] + f[:1]):
            ef[tuple(sorted((a, b)))].append(fi)
    adj = [set() for _ in faces]
    for fs in ef.values():
        for a in fs:
            adj[a].update(set(fs) - {a})
    return ef, adj


def loops(faces):
    counts = Counter(tuple(sorted((a, b))) for f in faces for a,b in zip(f,f[1:]+f[:1]))
    graph = defaultdict(list)
    for (a,b), count in counts.items():
        if count == 1:
            graph[a].append(b); graph[b].append(a)
    if any(len(v) != 2 for v in graph.values()):
        raise GeometricConflict('Region boundary branches or is open')
    used, result = set(), []
    for start in sorted(graph):
        if start in used:
            continue
        prev, cur, ring = None, start, []
        while cur not in used:
            ring.append(cur); used.add(cur)
            nxt = next(x for x in sorted(graph[cur]) if x != prev)
            prev, cur = cur, nxt
        if cur != start:
            raise GeometricConflict('Non-simple boundary')
        result.append(ring)
    return result


def planar_regions(v, faces, normals, adj, excluded=(), stable_seeds=False):
    used = set(excluded); result = []
    seeds = range(len(faces))
    if stable_seeds:
        # Thin CAD triangles have noisy normals. Start with the largest face
        # and retain that reference throughout growth; tolerances stay fixed.
        def area2(index):
            p = v[faces[index]]
            return float(np.linalg.norm(np.cross(p[1:-1]-p[0], p[2:]-p[0]).sum(0)))
        seeds = sorted(seeds, key=lambda index: (-area2(index), index))
    for seed in seeds:
        if seed in used:
            continue
        normal, origin = normals[seed], v[faces[seed][0]]
        region, stack = [seed], [seed]; used.add(seed)
        while stack:
            f = stack.pop()
            for g in sorted(adj[f] - used):
                if normals[g] @ normal < math.cos(math.radians(.1)):
                    continue
                if np.max(abs((v[faces[g]] - origin) @ normal)) > 1e-6:
                    continue
                used.add(g); region.append(g); stack.append(g)
        result.append([seed] + sorted(set(region)-{seed}) if stable_seeds else sorted(region))
    return result


try:
    from numpy.linalg import _umath_linalg as _lapack
except ImportError:  # pragma: no cover - other NumPy layouts
    _lapack = None


def _private_lstsq_matches():
    """The gufunc is private NumPy API. Use it only if it exists with the
    expected signature and reproduces np.linalg.lstsq bit for bit on probes
    (full rank, rank deficient, overdetermined); otherwise use the public call."""
    if _lapack is None:
        return False
    probes = [
        (np.array([[1., 2., 1.], [3., -1., 1.], [0.5, 4., 1.], [2., 2., 1.]]), np.array([1., -2., 3., .25])),
        (np.array([[1., 2., 3.], [2., 4., 6.], [1., 0., 1.]]), np.array([1., 2., .5])),
        (np.array([[1e-3, 1.], [2e-3, 1.], [3.5e-3, 1.]]), np.array([-0.0, 1e-9, 2.])),
    ]
    try:
        for matrix, rhs in probes:
            rcond = np.finfo(np.float64).eps * max(matrix.shape)
            with np.errstate(all='ignore'):
                fit, _, rank, _ = _lapack.lstsq(matrix, rhs[:, None], rcond, signature='ddd->ddid')
            ref, _, ref_rank, _ = np.linalg.lstsq(matrix, rhs, rcond=None)
            if int(rank) != int(ref_rank) or fit[:, 0].tobytes() != ref.tobytes():
                return False
    except Exception:
        return False
    return True


if not _private_lstsq_matches():
    _lapack = None


def _lstsq(matrix, rhs):
    """np.linalg.lstsq(matrix, rhs, rcond=None) for real 2-D input via the same
    LAPACK gufunc, without the generic wrapper overhead (detection calls it
    ~10^5 times). Returns (solution, rank)."""
    if _lapack is None:
        fit, _, rank, _ = np.linalg.lstsq(matrix, rhs, rcond=None)
        return fit, rank
    rcond = np.finfo(np.float64).eps * max(matrix.shape)
    with np.errstate(over='ignore', divide='ignore', under='ignore', invalid='ignore'):
        fit, _, rank, _ = _lapack.lstsq(matrix, rhs[:, None], rcond, signature='ddd->ddid')
    return fit[:, 0], int(rank)


def circle_fit(points):
    p = np.asarray(points, dtype=float)
    origin = p.mean(0); q = p-origin
    fit, rank = _lstsq(np.column_stack((2*q, np.ones(len(q)))), (q*q).sum(1))
    if rank < 3:
        raise ValueError('Collinear circle fit')
    c = origin + fit[:2]
    radii = np.linalg.norm(p-c, axis=1); r = float(radii.mean())
    return c, r, float(np.max(abs(radii-r)))


def measured_cylinder_ends(boundary, p, center, radius, start, span):
    """Two simple angularly monotone end chains separated by axial rails.

    Unlike axial extrema, measured paths also describe oblique and curved
    sheet corners. Reject holes, branches, folded chains and crossing ends.
    This is a boundary classification, never permission to skip validation.
    """
    edges = {tuple(sorted(edge)) for edge in boundary}
    degree = Counter(i for edge in edges for i in edge)
    if len(edges) != len(boundary) or not degree or any(n != 2 for n in degree.values()):
        return None
    angle = {i: float((math.atan2(p[i, 1]-center[1], p[i, 0]-center[0])-start)
                      % (2*math.pi)) for i in degree}
    tolerance = max(1e-4, 2e-6/radius)
    angle = {i: 0. if abs(a-2*math.pi) < tolerance else a for i, a in angle.items()}
    rails = set()
    graph = defaultdict(set)
    for a, b in edges:
        axial = abs(p[a, 2]-p[b, 2])
        radial = np.linalg.norm(p[a, :2]-p[b, :2])
        if (axial > max(1e-12, 10*radial) and
                any(abs(angle[a]-t) < tolerance and abs(angle[b]-t) < tolerance
                    for t in (0., span))):
            rails.add((a, b))
        else:
            graph[a].add(b)
            graph[b].add(a)
    pending = set(graph)
    rows = []
    while pending:
        seed = min(pending)
        component, stack = {seed}, [seed]
        pending.remove(seed)
        while stack:
            fresh = graph[stack.pop()] & pending
            pending -= fresh
            component |= fresh
            stack.extend(fresh)
        if (len(component) < 3 or sum(len(graph[i]) == 1 for i in component) != 2
                or any(len(graph[i]) > 2 for i in component)):
            return None
        row = sorted(component, key=lambda i: (angle[i], i))
        if (angle[row[0]] > tolerance or abs(angle[row[-1]]-span) > tolerance
                or any(angle[b]-angle[a] <= 1e-9 or b not in graph[a]
                       for a, b in zip(row, row[1:]))):
            return None
        rows.append(row)
    if len(rows) != 2:
        return None
    rows.sort(key=lambda row: float(p[row, 2].mean()))
    rail_graph = defaultdict(set)
    for a, b in rails:
        rail_graph[a].add(b)
        rail_graph[b].add(a)
    visited = set()
    for k in (0, -1):
        current, end = rows[0][k], rows[1][k]
        previous, path = None, set()
        while current != end:
            if current in path:
                return None
            path.add(current)
            following = rail_graph[current] - {previous}
            if len(following) != 1:
                return None
            nxt = next(iter(following))
            if p[nxt, 2] <= p[current, 2]:
                return None
            visited.add(tuple(sorted((current, nxt))))
            previous, current = current, nxt
        if rail_graph[end] != {previous}:
            return None
    if visited != rails:
        return None
    knots = sorted({angle[i] for row in rows for i in row})
    heights = [np.interp(knots, [angle[i] for i in row], p[row, 2]) for row in rows]
    if np.min(heights[1]-heights[0]) <= 1e-6:
        return None
    return rows


def expanded_edge_chain(splits, a, b, path=frozenset()):
    """Resolve nested measured subdivisions without losing intermediate cuts."""
    edge=(a,b)
    chain=splits.get(edge,[a,b])
    if chain==[a,b]:return chain
    if edge in path or chain[0]!=a or chain[-1]!=b or len(set(chain))!=len(chain):
        raise GeometricConflict('Conflicting nested edge subdivisions')
    result=[]
    for x,y in zip(chain,chain[1:]):
        result.extend(expanded_edge_chain(splits,x,y,path|{edge})[:-1])
    result.append(b)
    if len(set(result))!=len(result):
        raise GeometricConflict('Self-touching nested edge subdivisions')
    return result


def segment_count(r, span, full=False, epsilon=.0004, residual=0., bend=True):
    e = epsilon-residual
    if e <= 0 or r <= 0:
        raise ValueError('No approximation budget')
    n = 9 if full else max(2 if bend else 1, math.ceil(span/math.radians(37.5)))
    if e < r:
        n = max(n, math.ceil(span/(2*math.acos(1-e/r))))
    while r*(1-math.cos(span/(2*n))) > e:
        n += 1
    return n


def hole_segment_count(radius, original_segments, epsilon, residual=0.,
                       detail_factor=1., hole_epsilon=None):
    """Scale the old target, bounded by the hole's own chord-error budget."""
    if not math.isfinite(detail_factor) or not .1 <= detail_factor <= 2.:
        raise ValueError('Hole detail factor must be between 0.1 and 2.0')
    budget = epsilon if hole_epsilon is None else hole_epsilon
    if not math.isfinite(budget) or budget <= residual:
        raise ValueError('Hole deviation limit must exceed the fitted residual')
    baseline = min(segment_count(radius, 2*math.pi, True, epsilon, residual), original_segments)
    target = max(3, math.ceil(baseline * detail_factor))
    error = budget-residual
    minimum = 3 if error >= radius else max(3, math.ceil(math.pi/math.acos(1-error/radius)))
    return min(original_segments, max(target, minimum))


def topology(faces):
    ef=defaultdict(list)
    for f in faces:
        for a,b in zip(f,f[1:]+f[:1]):
            ef[tuple(sorted((a,b)))].append(a<b)
    return dict(boundary=sum(len(x)==1 for x in ef.values()),
                nonmanifold=sum(len(x)>2 for x in ef.values()),
                winding=sum(len(x)==2 and x[0]==x[1] for x in ef.values()),
                duplicates=len(faces)-len({tuple(sorted(f)) for f in faces}),edges=len(ef))
