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
    low=triangles.min(axis=1);high=triangles.max(axis=1);values=[]
    for point in points:
        index=bvh.find_nearest(Vector(point))[2]
        upper=float(point_triangles_squared(point,triangles[index:index+1])[0])
        separation=np.maximum(np.maximum(low-point,point-high),0)
        eligible=np.flatnonzero(np.sum(separation*separation,axis=1)<=upper+1e-16)
        values.append(float(np.min(point_triangles_squared(point,triangles[eligible]))))
    return np.sqrt(values)
