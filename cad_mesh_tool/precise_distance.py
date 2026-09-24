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

def accurate_distances(points,triangles,bvh):
    from mathutils import Vector
    low=triangles.min(axis=1);high=triangles.max(axis=1)
    values=np.full(len(points),np.inf,dtype=float)
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
