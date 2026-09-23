"""Deterministic cylinder extraction from adjacent planar facets, not mesh boundaries."""
import math
from collections import Counter, defaultdict
import numpy as np
from .geometry import adjacency, face_normals, planar_regions, basis, circle_fit, segment_count, loops


def complete_cylinders(vertices,faces,features,epsilon=.0004):
    """Recover cylinder faces hidden inside a mixed coplanar detector region.

    Region-level growth proposes the cylinder; face-level growth verifies its
    entire connected support and recomputes the rim geometry before rebuilding.
    """
    v=np.asarray(vertices,dtype=float);normals=face_normals(v,faces);_,adj=adjacency(faces)
    claimed={fi:cy['id'] for cy in features for fi in cy['faces']}
    for cy in features:
        frame=np.array(cy['frame']);p=(v-cy['origin'])@frame.T
        radial=abs(np.linalg.norm(p[:,:2]-cy['center'],axis=1)-cy['radius'])
        support=set(cy['faces']);stack=sorted(support)
        while stack:
            for fi in sorted(adj[stack.pop()]-support):
                if fi in claimed or abs(normals[fi]@frame[2])>=.8:continue
                if max(radial[faces[fi]])<=1e-6:support.add(fi);stack.append(fi)
        if len(support)==len(cy['faces']):continue
        fs=sorted(support);ids=sorted({i for f in fs for i in faces[f]})
        c,r,res=circle_fit(p[ids,:2])
        if res>(1e-6 if cy['full'] else 1e-5):continue
        ec=Counter(tuple(sorted((a,b))) for f in fs for a,b in zip(faces[f],faces[f][1:]+faces[f][:1]));boundary=[e for e,n in ec.items() if n==1]
        lo,hi=float(p[ids,2].min()),float(p[ids,2].max())
        bd=sorted({i for e in boundary for i in e});rims=[[i for i in bd if abs(p[i,2]-level)<1e-6] for level in (lo,hi)]
        angles=np.sort(np.unique(np.round(np.arctan2(p[ids,1]-c[1],p[ids,0]-c[0]),7)))
        gaps=np.diff(np.r_[angles,angles[0]+2*math.pi]);k=int(np.argmax(gaps))
        start=float(angles[0]) if cy['full'] else float(angles[(k+1)%len(angles)]);span=2*math.pi if cy['full'] else float(2*math.pi-gaps[k])
        old_segments=min(map(len,rims))-(0 if cy['full'] else 1)
        if old_segments<3:continue
        cy.update(faces=fs,vertices=ids,boundary=boundary,center=c.tolist(),radius=r,residual=res,lo=lo,hi=hi,start=start,span=span,
                  segments=min(segment_count(r,span,cy['full'],epsilon,res),old_segments),segments_before=old_segments,
                  support_faces_added=len(fs)-len(cy['faces']))
        for f in fs:claimed[f]=cy['id']
    return features


def discover(vertices, faces, epsilon=.0004):
    v=np.asarray(vertices,dtype=float)
    center=v.mean(0); v=v-center
    normals=face_normals(v,faces); ef,adj=adjacency(faces)
    regions=planar_regions(v,faces,normals,adj)
    owner={f:i for i,fs in enumerate(regions) for f in fs}
    rverts=[sorted({i for f in fs for i in faces[f]}) for fs in regions]
    rn=np.array([normals[fs[0]] for fs in regions]); ra=[set() for _ in regions]
    for fs in ef.values():
        if len(fs)==2:
            a,b=map(owner.get,fs)
            if a!=b:ra[a].add(b);ra[b].add(a)
    # Axes come from measured shared rails, not the world coordinate frame.
    votes=defaultdict(list)
    for a,ns in enumerate(ra):
        for b in sorted(ns):
            if b<=a:continue
            cross=np.cross(rn[a],rn[b]); length=np.linalg.norm(cross)
            if length < math.sin(math.radians(.2)) or rn[a]@rn[b]<math.cos(math.radians(45)):continue
            axis=cross/length
            if axis[np.argmax(abs(axis))]<0:axis=-axis
            votes[tuple(np.round(axis,3))].append(axis)
    axes=[]
    for i,ids in enumerate(rverts):
        if len(ids)>=6:
            z=rn[i].copy()
            if z[np.argmax(abs(z))]<0:z=-z
            frame=basis(z); justified=False
            try:
                for ring in loops([faces[f] for f in regions[i]]):
                    if len(ring)<9:continue
                    _,_,res=circle_fit((v[ring]@frame.T)[:,:2])
                    if res<1e-6:justified=True;break
            except ValueError:pass
            if justified and not any(abs(z@a/np.linalg.norm(a))>1-1e-8 for a in axes):axes.append(z)
    for _,xs in sorted(votes.items(),key=lambda x:(-len(x[1]),x[0])):
        if len(xs)<6:continue
        z=np.mean(xs,axis=0);z/=np.linalg.norm(z)
        if not any(abs(z@a/np.linalg.norm(a))>1-1e-8 for a in axes):axes.append(z)
    found={}; discovered_regions=set()
    for axis in axes:
        frame=basis(axis); p=v@frame.T
        eligible=set(np.flatnonzero(abs(rn@frame[2])<.8).tolist())-discovered_regions
        tested=set(); accepted_support=[]
        for a in sorted(eligible):
            for b in [a]+sorted(ra[a]&eligible):
                if b<a:continue
                if any(a in s and b in s for s in accepted_support):continue
                seed=frozenset((a,b))
                ids=sorted(set(rverts[a])|set(rverts[b]))
                try:c,r,res=circle_fit(p[ids,:2])
                except ValueError:continue
                if res>1e-5 or r<1e-5 or r>np.linalg.norm(np.ptp(v,axis=0))*10:continue
                support=set(seed);stack=list(seed)
                while stack:
                    x=stack.pop()
                    for y in sorted((ra[x]&eligible)-support):
                        error=np.max(abs(np.linalg.norm(p[rverts[y],:2]-c,axis=1)-r))
                        if error<=1e-5:support.add(y);stack.append(y)
                key=tuple(sorted(support))
                if key in tested or len(key)<3:continue
                tested.add(key)
                ids=sorted({i for z in support for i in rverts[z]})
                c,r,res=circle_fit(p[ids,:2])
                if res>1e-5:continue
                fs=sorted(f for z in support for f in regions[z])
                ec=Counter(tuple(sorted((i,j))) for f in fs for i,j in zip(faces[f],faces[f][1:]+faces[f][:1]))
                boundary=[e for e,n in ec.items() if n==1]
                lo,hi=float(p[ids,2].min()),float(p[ids,2].max())
                if hi-lo<1e-6:continue
                # A closed cylinder has only rim boundary edges. Open strips also have two rails.
                is_rim=lambda e: (max(abs(p[list(e),2]-lo))<1e-6 or max(abs(p[list(e),2]-hi))<1e-6)
                full=all(is_rim(e) for e in boundary)
                angles=np.sort(np.unique(np.round(np.arctan2(p[ids,1]-c[1],p[ids,0]-c[0]),7)))
                gaps=np.diff(np.r_[angles,angles[0]+2*math.pi]); k=int(np.argmax(gaps))
                start=float(angles[(k+1)%len(angles)]);span=float(2*math.pi-gaps[k])
                if full:start=float(angles[0]);span=2*math.pi
                if span<math.radians(5):continue
                # Every boundary vertex must lie on a rim or the start/end rail.
                bd=sorted({i for e in boundary for i in e})
                rims=[[i for i in bd if abs(p[i,2]-level)<1e-6] for level in (lo,hi)]
                if min(map(len,rims))<3:continue
                theta=(np.arctan2(p[bd,1]-c[1],p[bd,0]-c[0])-start)%(2*math.pi)
                theta=np.where(abs(theta-2*math.pi)<1e-5,0.,theta)
                onrim=(abs(p[bd,2]-lo)<1e-6)|(abs(p[bd,2]-hi)<1e-6)
                if not full and not np.all(onrim|(abs(theta)<1e-4)|(abs(theta-span)<1e-4)):continue
                rad=np.zeros((len(fs),3))
                rad[:,:2]=np.array([p[faces[f],:2].mean(0)-c for f in fs])
                score=np.sum(np.sum((normals[fs]@frame.T)*rad,axis=1))
                sign=1 if score>0 else -1
                old_segments=min(map(len,rims))-(0 if full else 1)
                n=min(segment_count(r,span,full,epsilon,res),old_segments)
                category='circular_hole' if full and sign<0 else 'outer_cylinder' if full else 'concave_arc' if sign<0 else 'convex_arc'
                record=dict(faces=fs,vertices=ids,boundary=boundary,frame=frame.tolist(),origin=center.tolist(),center=c.tolist(),radius=r,residual=res,lo=lo,hi=hi,start=start,span=span,full=full,sign=sign,segments=n,segments_before=old_segments,category=category)
                key=tuple(fs)
                if key not in found or res<found[key]['residual']:found[key]=record
                accepted_support.append(support)
                discovered_regions.update(support)
    claimed=set();features=[];overlaps=[]
    for cy in sorted(found.values(),key=lambda x:(-len(x['faces']),x['residual'],x['faces'][0])):
        if claimed.intersection(cy['faces']):
            overlaps.append(cy['faces']);continue
        cy['id']=len(features);claimed.update(cy['faces']);features.append(cy)
    features=complete_cylinders(vertices,faces,features,epsilon)
    claimed={fi for cy in features for fi in cy['faces']}
    # Discovery is a proposal. Remaining regions are explicitly inventoried, never interpreted as absence.
    return dict(features=features,region_count=len(regions),axis_candidates=len(axes),
                covered_faces=len(claimed),unclaimed_faces=sorted(set(range(len(faces)))-claimed),
                overlapping_candidates=len(overlaps))


if __name__=='__main__':
    import json,sys
    from pathlib import Path
    d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=discover(d['vertices'],d['faces'])
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'features':len(result['features']),'categories':dict(Counter(x['category'] for x in result['features'])),'regions':result['region_count'],'axes':result['axis_candidates'],'covered_faces':result['covered_faces']}))
