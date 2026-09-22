"""Checks actual Blender loop triangulation; reports sampled, not exact Hausdorff distance."""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from .geometry import topology
from .precise_distance import accurate_distances
from .intersections import intersections


def quality(v,t):
    p=v[t];area2=np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)
    length2=np.maximum.reduce([((p[:,(i+1)%3]-p[:,i])**2).sum(1) for i in range(3)])
    return length2/np.maximum(area2,1e-30),area2/2


def stats(q):
    if not len(q):return dict(count=0)
    return dict(count=len(q),median=float(np.median(q)),p95=float(np.percentile(q,95)),max=float(q.max()),gt20=int(sum(q>20)),gt100=int(sum(q>100)))


def samples(v,t,areas,count):
    edges=sorted({tuple(sorted((int(a),int(b)))) for tri in t for a,b in zip(tri,np.roll(tri,-1))})
    rng=np.random.default_rng(0);ids=rng.choice(len(t),count,p=areas/areas.sum());r=rng.random((count,2));s=np.sqrt(r[:,0]);p=v[t[ids]]
    return np.concatenate([v,np.array([(v[a]+v[b])/2 for a,b in edges]),v[t].mean(1),(1-s)[:,None]*p[:,0]+(s*(1-r[:,1]))[:,None]*p[:,1]+(s*r[:,1])[:,None]*p[:,2]])


def distance(points,v,t):
    bvh=BVHTree.FromPolygons([Vector(x) for x in v],[tuple(map(int,x)) for x in t],all_triangles=True)
    d=accurate_distances(points,v[t],bvh)
    return dict(max_mm=float(d.max()*1000),p95_mm=float(np.percentile(d,95)*1000),rms_mm=float(np.sqrt(np.mean(d*d))*1000),samples=len(d),worst_sample_centered_m=np.asarray(points[int(np.argmax(d))]).tolist())


def validate(snapshot,mesh,origin,roles,perimeters,epsilon=.0004,sample_count=20000):
    mesh.calc_loop_triangles()
    center=np.asarray(snapshot['vertices']).mean(0)
    v=np.asarray(snapshot['vertices'])-center;t=np.array(snapshot['triangles'])
    w=np.array([x.co[:] for x in mesh.vertices])+origin-center;u=np.array([list(x.vertices) for x in mesh.loop_triangles])
    bq,ba=quality(v,t);aq,aa=quality(w,u)
    poly=np.array([x.polygon_index for x in mesh.loop_triangles]);labels=np.array(roles)[poly]
    f=[list(p.vertices) for p in mesh.polygons];top=topology(f);oldtop=topology(snapshot['faces'])
    print('VALIDATE intersections',flush=True);isect=intersections(w,u)
    print('VALIDATE source_to_result',flush=True);forward=distance(samples(v,t,ba,sample_count),w,u)
    print('VALIDATE result_to_source',flush=True);backward=distance(samples(w,u,aa,sample_count),v,t)
    annulus=stats(aq[labels=='PERIMETER_RING'])
    edge_roles={}
    for fi,face in enumerate(f):
        for a,b in zip(face,face[1:]+face[:1]):edge_roles.setdefault(tuple(sorted((a,b))),[]).append(roles[fi])
    errors=[]
    for pi,p in enumerate(perimeters):
        for ringname in ('ids','hole'):
            ring=p[ringname]
            for a,b in zip(ring,ring[1:]+ring[:1]):
                rr=edge_roles.get(tuple(sorted((a,b))),[])
                expected={'BACKGROUND_PLANE'} if ringname=='ids' else {'DETAIL_REBUILT','PROTECTED_OTHER'}
                # Straight wall sections of compound cutouts may be retained exactly.
                valid=len(rr)==2 and sum(r in {'PERIMETER_RING','PERIMETER_STRAIGHT'} for r in rr)==1 and any(r in expected for r in rr)
                if not valid:errors.append(dict(perimeter=pi,edge=[a,b],roles=rr))
    from .sparse_perimeter import audit
    strip_errors=audit(w,f,roles,perimeters)
    checks=dict(closed_oriented=not any(top[k] for k in ('boundary','nonmanifold','winding','duplicates')),
                euler_unchanged=len(v)-oldtop['edges']+len(snapshot['faces'])==len(w)-top['edges']+len(f),
                fewer_triangles=len(u)<len(t),no_degenerate_triangles=bool(np.all(aa>1e-16)),
                annulus_quality=annulus.get('max',0)<=20,perimeter_edges=not errors,straight_perimeter_layout=not strip_errors,
                no_detected_intersections=not isect['intersections'],
                sampled_distance=max(forward['max_mm'],backward['max_mm'])<=epsilon*1000)
    return dict(checks=checks,topology=top,before=dict(v=len(v),f=len(snapshot['faces']),t=len(t),q=stats(bq)),
                after=dict(v=len(w),f=len(f),t=len(u),q=stats(aq)),quality_by_role={r:stats(aq[labels==r]) for r in sorted(set(labels))},
                perimeter_errors=errors,straight_perimeter_errors=strip_errors,intersections=isect,distance=dict(source_to_result=forward,result_to_source=backward),distance_reference_center_m=center.tolist(),
                distance_method='Bidirectional sampled float64 point-triangle, vertices/edge midpoints/triangle centroids plus area samples seed 0; not exact Hausdorff')
