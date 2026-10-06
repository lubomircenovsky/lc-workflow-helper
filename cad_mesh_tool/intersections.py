"""Triangle narrow phase in float64; positive-area coplanar overlap or proper segment crossing."""

import numpy as np
import heapq


def candidate_pairs(low, high, tolerance=1e-9):
    """Float64 sweep; exact legacy AABB predicate, with bounded working memory.

    Sweep the axis with the smallest relative average box width. The heap only
    removes boxes that cannot overlap. Its conservative padding handles floating
    rounding; acceptance uses the original predicate in original index order.
    """
    for first, second in candidate_pair_blocks(low, high, tolerance):
        yield from zip(first, second)


def candidate_pair_blocks(low, high, tolerance=1e-9):
    """Same pairs and order as candidate_pairs(), as (first, second) index arrays."""
    if not len(low):
        return
    span = high.max(axis=0) - low.min(axis=0)
    relative = np.divide((high - low).mean(axis=0), span, out=np.full(3, np.inf), where=span > 0)
    axis = int(np.argmin(relative))
    active = set()
    expiry = []
    for index in np.argsort(low[:, axis], kind='stable'):
        index = int(index)
        while expiry and expiry[0][0] < low[index, axis]:
            _, expired = heapq.heappop(expiry)
            active.remove(expired)
        if active:
            others = np.fromiter(active, dtype=np.int64, count=len(active))
            first = np.minimum(others, index)
            second = np.maximum(others, index)
            overlap = np.all(high[second] >= low[first] - tolerance, axis=1) & np.all(
                low[second] <= high[first] + tolerance, axis=1
            )
            if overlap.any():
                yield first[overlap], second[overlap]
        active.add(index)
        limit = np.nextafter(high[index, axis] + 2 * tolerance, np.inf)
        heapq.heappush(expiry, (limit, index))


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
