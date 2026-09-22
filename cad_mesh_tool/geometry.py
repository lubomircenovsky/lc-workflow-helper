"""Geometry primitives shared by detection, reconstruction and tests (SI units)."""
import math
from collections import defaultdict, Counter
import numpy as np


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
    result = []
    for f in faces:
        p = v[f]
        n = np.cross(p[1:-1] - p[0], p[2:] - p[0]).sum(0)
        result.append(n / max(np.linalg.norm(n), 1e-30))
    return np.array(result)


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
        raise ValueError('Region boundary branches or is open')
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
            raise ValueError('Non-simple boundary')
        result.append(ring)
    return result


def planar_regions(v, faces, normals, adj, excluded=()):
    used = set(excluded); result = []
    for seed in range(len(faces)):
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
        result.append(sorted(region))
    return result


def circle_fit(points):
    p = np.asarray(points, dtype=float)
    origin = p.mean(0); q = p-origin
    fit, _, rank, singular = np.linalg.lstsq(np.column_stack((2*q, np.ones(len(q)))), (q*q).sum(1), rcond=None)
    if rank < 3:
        raise ValueError('Collinear circle fit')
    c = origin + fit[:2]
    radii = np.linalg.norm(p-c, axis=1); r = float(radii.mean())
    return c, r, float(np.max(abs(radii-r)))


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


def topology(faces):
    ef=defaultdict(list)
    for f in faces:
        for a,b in zip(f,f[1:]+f[:1]):
            ef[tuple(sorted((a,b)))].append(a<b)
    return dict(boundary=sum(len(x)==1 for x in ef.values()),
                nonmanifold=sum(len(x)>2 for x in ef.values()),
                winding=sum(len(x)==2 and x[0]==x[1] for x in ef.values()),
                duplicates=len(faces)-len({tuple(sorted(f)) for f in faces}),edges=len(ef))
