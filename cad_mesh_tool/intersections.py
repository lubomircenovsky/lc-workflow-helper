"""Triangle narrow phase in float64; positive-area coplanar overlap or proper segment crossing."""

import numpy as np


def candidate_pairs(low, high, tolerance=1e-9):
    """Float64 sweep; exact legacy AABB predicate, with bounded working memory.

    Sweep the axis with the smallest relative average box width. The heap only
    removes boxes that cannot overlap. Its conservative padding handles floating
    rounding; acceptance uses the original predicate in original index order.
    """
    for first, second in candidate_pair_blocks(low, high, tolerance):
        yield from zip(first, second)


def candidate_pair_blocks(low, high, tolerance=1e-9, block_pairs=1 << 20):
    """Same candidate pairs as the legacy heap sweep, generated vectorized.

    Boxes are sorted along the axis with the smallest relative average width.
    A later box is a sweep candidate of an earlier one exactly when the legacy
    sweep kept the earlier box active: its low bound does not exceed
    nextafter(high + 2*tolerance). Candidates are then filtered with the
    original float64 AABB predicate on (min index, max index). The pair set is
    identical; only the emission order differs (callers sort their results).
    """
    if not len(low):
        return
    span = high.max(axis=0) - low.min(axis=0)
    relative = np.divide((high-low).mean(axis=0), span,
                         out=np.full(3, np.inf), where=span > 0)
    axis = int(np.argmin(relative))
    order = np.argsort(low[:, axis], kind='stable')
    lows = low[order, axis]
    limits = np.nextafter(high[order, axis] + 2*tolerance, np.inf)
    ends = np.searchsorted(lows, limits, side='right')
    counts = np.maximum(ends - np.arange(len(order)) - 1, 0)
    start = 0
    while start < len(order):
        # Bound working memory: take whole sweep rows up to ~block_pairs pairs.
        total = np.cumsum(counts[start:])
        stop = start + max(1, int(np.searchsorted(total, block_pairs, side='right')))
        rows = np.arange(start, stop)
        row_counts = counts[start:stop]
        if row_counts.sum():
            s = np.repeat(rows, row_counts)
            offsets = np.arange(len(s)) - np.repeat(np.cumsum(row_counts) - row_counts, row_counts)
            t = s + 1 + offsets
            a = order[s]
            b = order[t]
            first = np.minimum(a, b)
            second = np.maximum(a, b)
            overlap = (np.all(high[second] >= low[first]-tolerance, axis=1)
                       & np.all(low[second] <= high[first]+tolerance, axis=1))
            if overlap.any():
                yield first[overlap], second[overlap]
        start = stop


def cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def clipped_area(a, b):
    if cross2(b[1] - b[0], b[2] - b[0]) < 0:
        b = b[::-1]
    poly = list(a)
    for q, r in zip(b, np.roll(b, -1, axis=0)):
        output = []
        for p, s in zip(poly, poly[1:] + poly[:1]):
            dp = cross2(r - q, p - q)
            ds = cross2(r - q, s - q)
            ip = dp >= 0
            ins = ds >= 0
            if ip:
                output.append(p)
            if ip != ins:
                output.append(p + (s - p) * (dp / (dp - ds)))
        poly = output
        if not poly:
            return 0.0
    return abs(sum(cross2(p, s) for p, s in zip(poly, poly[1:] + poly[:1]))) / 2


def proper_cross(a, b, normal):
    distances = (a - b[0]) @ normal
    for i in range(3):
        j = (i + 1) % 3
        d1 = distances[i]
        d2 = distances[j]
        if (d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9):
            p = a[i] + (a[j] - a[i]) * (d1 / (d1 - d2))
            ab = b[1] - b[0]
            ac = b[2] - b[0]
            ap = p - b[0]
            nn = np.cross(ab, ac)
            den = nn @ nn
            u = np.cross(ap, ac) @ nn / den
            v = np.cross(ab, ap) @ nn / den
            if u > 1e-8 and v > 1e-8 and u + v < 1 - 1e-8:
                return True
    return False


def _proper_cross_many(a, b, normal):
    """Vectorized proper_cross(a[k], b[k], normal[k]) with identical predicates."""
    distances = np.einsum('kij,kj->ki', a - b[:, :1], normal)
    hit = np.zeros(len(a), dtype=bool)
    ab = b[:, 1] - b[:, 0]
    ac = b[:, 2] - b[:, 0]
    nn = np.cross(ab, ac)
    den = np.einsum('ki,ki->k', nn, nn)
    for i in range(3):
        j = (i + 1) % 3
        d1 = distances[:, i]
        d2 = distances[:, j]
        straddle = ((d1 > 1e-9) & (d2 < -1e-9)) | ((d1 < -1e-9) & (d2 > 1e-9))
        rows = np.flatnonzero(straddle & ~hit)
        if not len(rows):
            continue
        d1 = d1[rows]
        d2 = d2[rows]
        p = a[rows, i] + (a[rows, j] - a[rows, i]) * (d1 / (d1 - d2))[:, None]
        ap = p - b[rows, 0]
        u = np.einsum('ki,ki->k', np.cross(ap, ac[rows]), nn[rows]) / den[rows]
        v = np.einsum('ki,ki->k', np.cross(ab[rows], ap), nn[rows]) / den[rows]
        hit[rows[(u > 1e-8) & (v > 1e-8) & (u + v < 1 - 1e-8)]] = True
    return hit


def intersections(vertices, triangles):
    p = vertices[triangles]
    low = p.min(axis=1)
    high = p.max(axis=1)
    cr = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    length = np.linalg.norm(cr, axis=1)
    norm = cr / np.maximum(length[:, None], 1e-30)
    hits = []
    tested = 0
    pending_i = []
    pending_j = []
    pending = 0

    def _edge_neighbours_on_opposite_sides(first, second):
        # Two coplanar triangles that share an edge and lie strictly on its
        # opposite sides overlap only along that edge: their clipped area is
        # zero (the clip of such pairs is numerically ~1e-18). Thin cases
        # below the margin still use the exact polygon clip.
        result = np.zeros(len(first), dtype=bool)
        if not len(first):
            return result
        ta = triangles[first]
        tb = triangles[second]
        equal = ta[:, :, None] == tb[:, None, :]
        shared = equal.sum(axis=(1, 2)) == 2
        if not shared.any():
            return result
        rows = np.flatnonzero(shared)
        in_b = equal[rows].any(axis=2)
        in_a = equal[rows].any(axis=1)
        third_a = np.argmin(in_b, axis=1)
        third_b = np.argmin(in_a, axis=1)
        edge = np.argsort(~in_b, axis=1, kind='stable')[:, :2]
        axis = np.argmax(np.abs(norm[first[rows]]), axis=1)
        keep = np.array([[1, 2], [0, 2], [0, 1]])[axis]
        index = np.arange(len(rows))
        pa = p[first[rows]]
        pb = p[second[rows]]

        def project(points):
            return np.stack((points[index, keep[:, 0]], points[index, keep[:, 1]]), axis=1)

        e0 = project(pa[index, edge[:, 0]])
        e1 = project(pa[index, edge[:, 1]])
        x = project(pa[index, third_a])
        y = project(pb[index, third_b])

        def orient(o, u, w):
            return (u[:, 0]-o[:, 0])*(w[:, 1]-o[:, 1])-(u[:, 1]-o[:, 1])*(w[:, 0]-o[:, 0])

        ox = orient(e0, e1, x)
        oy = orient(e0, e1, y)
        result[rows] = (ox*oy < 0) & (np.abs(ox) > 1e-14) & (np.abs(oy) > 1e-14)
        return result

    def _separated_in_plane(first, second, margin=1e-18):
        # A separating edge with a clear margin proves an empty overlap, so the
        # exact clip could only return (numerically) zero area.
        if not len(first):
            return np.zeros(0, dtype=bool)
        axis = np.argmax(np.abs(norm[first]), axis=1)
        keep = np.array([[1, 2], [0, 2], [0, 1]])[axis]
        rows = np.arange(len(first))[:, None]
        corners = np.arange(3)[None, :]

        def planar(points):
            return np.stack((points[rows, corners, keep[:, :1]], points[rows, corners, keep[:, 1:]]), axis=-1)

        a = planar(p[first])
        b = planar(p[second])
        # Corners shared by index have identical coordinates and lie exactly on
        # the clip edges through them; they may touch the separating line.
        shared_a = (triangles[first][:, :, None] == triangles[second][:, None, :]).any(axis=2)
        shared_b = (triangles[second][:, :, None] == triangles[first][:, None, :]).any(axis=2)

        def ccw(tri):
            area = ((tri[:, 1, 0]-tri[:, 0, 0])*(tri[:, 2, 1]-tri[:, 0, 1])
                    - (tri[:, 1, 1]-tri[:, 0, 1])*(tri[:, 2, 0]-tri[:, 0, 0]))
            return np.where((area < 0)[:, None, None], tri[:, ::-1], tri)

        def separated(clip, subject, subject_shared):
            clip = ccw(clip)
            found = np.zeros(len(clip), dtype=bool)
            for k in range(3):
                q = clip[:, k][:, None]
                r = clip[:, (k+1) % 3][:, None]
                d = (r[..., 0]-q[..., 0])*(subject[..., 1]-q[..., 1]) - (r[..., 1]-q[..., 1])*(subject[..., 0]-q[..., 0])
                outside = (d < -margin) | (subject_shared & (d == 0))
                found |= np.all(outside, axis=1) & ~np.all(subject_shared, axis=1)
            return found

        return separated(b, a, shared_a) | separated(a, b, shared_b)

    def narrow(first, second):
        nonlocal tested
        # Plane-side rejection: each triangle must reach both sides of, or lie
        # on, the other's plane (same 1e-9 tolerance as the scalar test).
        da = np.einsum('kij,kj->ki', p[second] - p[first, :1], norm[first])
        db = np.einsum('kij,kj->ki', p[first] - p[second, :1], norm[second])
        keep = ~((da.min(1) > 1e-9) | (da.max(1) < -1e-9) | (db.min(1) > 1e-9) | (db.max(1) < -1e-9))
        first = first[keep]
        second = second[keep]
        da = da[keep]
        db = db[keep]
        tested += len(first)
        coplanar = (np.abs(da).max(1) < 1e-9) & (np.abs(db).max(1) < 1e-9)
        candidates = np.flatnonzero(coplanar)
        skip = _edge_neighbours_on_opposite_sides(first[candidates], second[candidates])
        skip |= _separated_in_plane(first[candidates], second[candidates])
        coplanar[candidates[skip]] = False
        for i, j in zip(first[coplanar].tolist(), second[coplanar].tolist()):
            axis = int(np.argmax(abs(norm[i])))
            axes = [k for k in range(3) if k != axis]
            area = clipped_area(p[i][:, axes] - p[i, 0, axes], p[j][:, axes] - p[i, 0, axes])
            if area > 1e-12:
                hits.append(
                    {'a': int(i), 'b': int(j), 'type': 'coplanar_positive_area', 'area_projected': area}
                )
        first = first[~coplanar]
        second = second[~coplanar]
        if len(first):
            crossing = _proper_cross_many(p[first], p[second], norm[second])
            rest = ~crossing
            crossing[rest] = _proper_cross_many(p[second[rest]], p[first[rest]], norm[first[rest]])
            for i, j in zip(first[crossing].tolist(), second[crossing].tolist()):
                hits.append({'a': int(i), 'b': int(j), 'type': 'proper_crossing'})

    for first, second in candidate_pair_blocks(low, high):
        pending_i.append(first)
        pending_j.append(second)
        pending += len(first)
        if pending >= 65536:
            narrow(np.concatenate(pending_i), np.concatenate(pending_j))
            pending_i = []
            pending_j = []
            pending = 0
    if pending:
        narrow(np.concatenate(pending_i), np.concatenate(pending_j))
    hits.sort(key=lambda hit: (hit['a'], hit['b']))
    return {
        'intersections': hits,
        'narrow_phase_pairs': tested,
        'tolerance_m': 1e-9,
        'coplanar_area_threshold_m2': 1e-12,
        'method': 'float64 AABB sweep, coplanar convex polygon clipping and strict interior segment-triangle crossings; tangential contacts excluded',
    }
