"""Float64 closest point to a batch of triangles, including edges; avoids skinny-triangle float32 loss."""
import numpy as np

def point_triangles_squared(point,triangles):
    a,b,c=triangles[:,0],triangles[:,1],triangles[:,2]
    ab=b-a;ac=c-a;ap=point-a
    normal=np.cross(ab,ac);den=np.sum(normal*normal,axis=1)
    safe=np.maximum(den,1e-60)
    # Oriented cross products are more stable than the Gram determinant for long thin triangles.
    beta=np.sum(np.cross(ap,ac)*normal,axis=1)/safe
    gamma=np.sum(np.cross(ab,ap)*normal,axis=1)/safe
    plane=np.sum(ap*normal,axis=1)**2/safe
    inside=(beta>=-1e-12)&(gamma>=-1e-12)&(beta+gamma<=1+1e-12)&(den>1e-50)
    result=np.where(inside,plane,np.inf)
    for x,y in [(a,b),(b,c),(c,a)]:
        edge=y-x;lam=np.clip(np.sum((point-x)*edge,axis=1)/np.maximum(np.sum(edge*edge,axis=1),1e-60),0,1)
        diff=point-(x+lam[:,None]*edge)
        result=np.minimum(result,np.sum(diff*diff,axis=1))
    return result

def _candidate_tree(low, high, leaf_size=64):
    """Float64 bounds containing every triangle; no quantization or padding."""
    centers = (low + high) * .5

    def build(ids):
        lower = low[ids].min(axis=0)
        upper = high[ids].max(axis=0)
        if len(ids) <= leaf_size:
            return lower, upper, ids, None, None
        axis = int(np.argmax(np.ptp(centers[ids], axis=0)))
        middle = len(ids) // 2
        order = np.argpartition(centers[ids, axis], middle)
        return (lower, upper, None, build(ids[order[:middle]]),
                build(ids[order[middle:]]))

    return build(np.arange(len(low)))


def _tree_squared(points, triangles, low, high, tree, upper):
    """Prune enclosing boxes, then apply the original exact candidate predicate."""
    values = np.full(len(points), np.inf, dtype=float)
    stack = [(tree, np.arange(len(points)))]
    while stack:
        node, ids = stack.pop()
        lower, higher, triangle_ids, left, right = node
        separation = np.maximum(np.maximum(lower - points[ids], points[ids] - higher), 0)
        ids = ids[np.sum(separation * separation, axis=1) <= upper[ids] + 1e-16]
        if not len(ids):
            continue
        if triangle_ids is None:
            stack.extend(((left, ids), (right, ids)))
            continue
        separation = np.maximum(np.maximum(
            low[triangle_ids][None, :, :] - points[ids, None, :],
            points[ids, None, :] - high[triangle_ids][None, :, :]), 0)
        point_ids, local_triangles = np.nonzero(
            np.sum(separation * separation, axis=2) <= upper[ids, None] + 1e-16)
        for start in range(0, len(point_ids), 8192):
            selected = ids[point_ids[start:start + 8192]]
            eligible = triangle_ids[local_triangles[start:start + 8192]]
            exact = point_triangles_squared(points[selected], triangles[eligible])
            np.minimum.at(values, selected, exact)
    return values


def _spatial_order(points, bits=10):
    """Morton (Z-order) permutation of points; ties keep their input order."""
    low = points.min(axis=0)
    span = np.maximum(points.max(axis=0) - low, 1e-300)
    cells = np.clip(((points - low) / span * ((1 << bits) - 1)).astype(np.int64), 0, (1 << bits) - 1)
    code = np.zeros(len(points), dtype=np.int64)
    for bit in range(bits):
        for axis in range(3):
            code |= ((cells[:, axis] >> bit) & 1) << (3 * bit + axis)
    return np.argsort(code, kind='stable')


def accurate_distances(points,triangles,bvh):
    from mathutils import Vector
    low=triangles.min(axis=1);high=triangles.max(axis=1)
    values=np.full(len(points),np.inf,dtype=float)
    if len(triangles) >= 2048 and len(points):
        tree = _candidate_tree(low, high)
        # Each point's exact minimum depends only on that point and its own
        # upper bound, so the visiting order is free. Spatially coherent
        # batches (Morton order) share tree nodes and leaves, which removes
        # most per-node NumPy overhead without changing any value.
        order = _spatial_order(points)
        for start in range(0, len(points), 4096):
            ids = order[start:start + 4096]
            batch = points[ids]
            nearest = np.asarray([bvh.find_nearest(Vector(point))[2] for point in batch], dtype=int)
            upper = point_triangles_squared(batch, triangles[nearest])
            values[ids] = _tree_squared(batch, triangles, low, high, tree, upper)
        return np.sqrt(values)
    # Keep the exact float64 candidate test, but avoid thousands of tiny NumPy calls.
    for start in range(0,len(points),16):
        batch=points[start:start+16]
        nearest=np.asarray([bvh.find_nearest(Vector(point))[2] for point in batch],dtype=int)
        upper=point_triangles_squared(batch,triangles[nearest])
        for triangle_start in range(0,len(triangles),8192):
            triangle_end=triangle_start+8192
            separation=np.maximum(np.maximum(low[None,triangle_start:triangle_end,:]-batch[:,None,:],
                                             batch[:,None,:]-high[None,triangle_start:triangle_end,:]),0)
            point_ids,triangle_ids=np.nonzero(
                np.sum(separation*separation,axis=2)<=upper[:,None]+1e-16)
            for pair_start in range(0,len(point_ids),8192):
                pair_end=pair_start+8192
                ids=point_ids[pair_start:pair_end]
                distances=point_triangles_squared(
                    batch[ids],triangles[triangle_start+triangle_ids[pair_start:pair_end]])
                np.minimum.at(values[start:start+len(batch)],ids,distances)
    return np.sqrt(values)
