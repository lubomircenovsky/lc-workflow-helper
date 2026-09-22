"""Deterministic rectangular cutout ring: four straight strips and four corners."""
import numpy as np


def partition(hole, corners, tolerance=1e-6):
    """12 outer points: rectangle corners and strip endpoints; hole unchanged."""
    from .rebuild import orient
    hole=np.asarray(hole,dtype=float);corners=np.asarray(corners,dtype=float)
    area=sum(orient(np.zeros(2),a,b) for a,b in zip(hole,np.roll(hole,-1,axis=0)))
    step=1 if area>0 else -1
    if any(step*orient(hole[i-1],hole[i],hole[(i+1)%len(hole)]) < -1e-12 for i in range(len(hole))):return None
    sides=[];outer=[]
    for a,b in zip(corners,np.roll(corners,-1,axis=0)):
        direction=(b-a)/np.linalg.norm(b-a);inward=np.array([-direction[1],direction[0]])
        distance=(hole-a)@inward;offset=float(distance.min())
        if offset<=tolerance:return None
        ids=np.flatnonzero(abs(distance-offset)<=tolerance).tolist()
        ids.sort(key=lambda i:float((hole[i]-a)@direction))
        if len(ids)<2:return None
        if any((y-x)%len(hole)!=step%len(hole) for x,y in zip(ids,ids[1:])):return None
        start=float((hole[ids[0]]-a)@direction);end=float((hole[ids[-1]]-a)@direction)
        if start<=tolerance or end>=np.linalg.norm(b-a)-tolerance or end-start<=tolerance:return None
        outer.extend([a,a+start*direction,a+end*direction]);sides.append(ids)
    if len({i for ids in sides for i in ids})!=sum(map(len,sides)):return None
    strips=[];regions=[]
    for i,ids in enumerate(sides):
        strips.append([3*i+1,3*i+2]+[12+j for j in reversed(ids)])
        nxt=(i+1)%4;arc=[ids[-1]]
        while arc[-1]!=sides[nxt][0]:
            arc.append((arc[-1]+step)%len(hole))
            if len(arc)>len(hole):return None
        if len(arc)<3:return None
        regions.append([3*i+2,3*nxt,3*nxt+1]+[12+j for j in reversed(arc)])
    return np.asarray(outer),strips,regions


def choose(hole,outer,obstacles):
    from .rebuild import inside,contacts,tessellation,orient
    hole=np.asarray(hole);center=hole.mean(0)
    for degree in [0,15,30,45,60,75]:
        a=np.radians(degree);rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
        local=(hole-center)@rot;low=local.min(0)-.002;high=local.max(0)+.002
        corners=np.array([[low[0],low[1]],[high[0],low[1]],[high[0],high[1]],[low[0],high[1]]])@rot.T+center
        if not all(inside(p,outer) for p in corners) or contacts(corners,outer):continue
        if any(contacts(corners,o) or any(inside(p,corners) for p in o) or inside(corners[0],o) for o in obstacles):continue
        layout=partition(hole,corners)
        if layout is None:continue
        ring,strips,regions=layout;points=np.concatenate([ring,hole]);qmax=0.;valid=True
        for region in regions:
            pp,tri=tessellation([points[region]])
            if len(tri)!=len(region)-2:valid=False;break
            for f in tri:
                q=max(np.sum((pp[f[(i+1)%3]]-pp[f[i]])**2) for i in range(3))/max(abs(orient(*pp[f])),1e-30)
                qmax=max(qmax,q)
        if valid and qmax<=20:
            return ring,[dict(degree=degree,size=None,layout='straight_strips',corner_q=qmax,
                              strips=strips,corner_regions=regions)]
    return None


def audit(vertices,faces,roles,perimeters):
    """Recompute strip geometry; an arbitrary long skinny face cannot opt out of Q."""
    from .geometry import basis,face_normals
    def canonical(f):
        f=list(f);k=f.index(min(f));return tuple(f[k:]+f[:k])
    actual={canonical(f) for f,r in zip(faces,roles) if r=='PERIMETER_STRAIGHT'}
    expected=set();errors=[]
    for pi,p in enumerate(perimeters):
        if p.get('layout')!='straight_strips':
            if p.get('strips'):errors.append(dict(perimeter=pi,reason='unexpected_strips'))
            continue
        if len(p['ids'])!=12 or len(p.get('strips',[]))!=4:
            errors.append(dict(perimeter=pi,reason='layout_counts'));continue
        outer=vertices[p['ids']];hole=vertices[p['hole']]
        normal=face_normals(vertices,[p['ids']])[0];frame=basis(normal);origin=outer[0]
        if np.max(abs((np.concatenate([outer,hole])-origin)@normal))>1e-6:
            errors.append(dict(perimeter=pi,reason='nonplanar'));continue
        xy=((outer-origin)@frame.T)[:,:2];hh=((hole-origin)@frame.T)[:,:2]
        layout=partition(hh,xy[::3])
        if layout is None or np.max(np.linalg.norm(layout[0]-xy,axis=1))>1e-6:
            errors.append(dict(perimeter=pi,reason='not_rectangular_strips'));continue
        all_ids=p['ids']+p['hole'];derived={canonical([all_ids[i] for i in f]) for f in layout[1]}
        if derived!={canonical(f) for f in p['strips']}:
            errors.append(dict(perimeter=pi,reason='strip_metadata_mismatch'))
        expected.update(derived)
    if actual!=expected:errors.append(dict(reason='strip_faces_mismatch',missing=len(expected-actual),unexpected=len(actual-expected)))
    return errors
