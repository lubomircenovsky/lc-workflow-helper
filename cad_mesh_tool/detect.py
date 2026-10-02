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
        # Completing support can close the missing sector of a circular hole.
        # Reclassify from the completed boundary, rather than retaining the
        # earlier open-strip decision and leaving a seam in the rebuilt wall.
        full=all(max(abs(p[list(edge),2]-lo))<1e-6 or
                 max(abs(p[list(edge),2]-hi))<1e-6 for edge in boundary)
        start=float(angles[0]) if full else float(angles[(k+1)%len(angles)]);span=2*math.pi if full else float(2*math.pi-gaps[k])
        old_segments=min(map(len,rims))-(0 if full else 1)
        if old_segments<3:continue
        cy.update(faces=fs,vertices=ids,boundary=boundary,center=c.tolist(),radius=r,residual=res,lo=lo,hi=hi,start=start,span=span,
                  full=full,category=('circular_hole' if cy['sign']<0 else 'outer_cylinder') if full else cy['category'],
                  segments=min(segment_count(r,span,full,epsilon,res),old_segments),segments_before=old_segments,
                  support_faces_added=len(fs)-len(cy['faces']))
        for f in fs:claimed[f]=cy['id']
    return features


def refine_rail_axis(vertices, feature, epsilon):
    """Correct a noisy normal-vote axis using two measured parallel axial rails.

    Vote rounding can bias a long extrusion enough to join its end contours.
    Accept a refinement only when two boundary rails agree and the radial fit
    improves to micron accuracy. Rebuilding still receives full validation.
    """
    if feature['full'] or feature['residual'] <= 1e-6:
        return
    v = np.asarray(vertices, dtype=float)
    old_axis = np.asarray(feature['frame'])[2]
    rails = []
    for a, b in feature['boundary']:
        delta = v[b] - v[a]
        length = np.linalg.norm(delta)
        if length <= max(1e-6, feature['radius'] * 2):
            continue
        direction = delta / length
        if abs(direction @ old_axis) > .999999:
            rails.append(direction if direction @ old_axis > 0 else -direction)
    if len(rails) < 2:
        return
    axis = np.mean(rails, axis=0)
    axis /= np.linalg.norm(axis)
    if any(direction @ axis < 1 - 1e-10 for direction in rails):
        return
    frame = basis(axis)
    p = (v - feature['origin']) @ frame.T
    ids = feature['vertices']
    center, radius, residual = circle_fit(p[ids, :2])
    if residual > 1e-6 or residual >= feature['residual']:
        return
    angles = np.sort(np.unique(np.round(np.arctan2(
        p[ids, 1] - center[1], p[ids, 0] - center[0]), 7)))
    gaps = np.diff(np.r_[angles, angles[0] + 2 * math.pi])
    start_index = int(np.argmax(gaps))
    lo, hi = float(p[ids, 2].min()), float(p[ids, 2].max())
    bd = sorted({vi for edge in feature['boundary'] for vi in edge})
    rims = [[vi for vi in bd if abs(p[vi, 2] - level) < 1e-6] for level in (lo, hi)]
    if min(map(len, rims)) < 3:
        return
    span = float(2 * math.pi - gaps[start_index])
    before = min(map(len, rims)) - 1
    feature.update(frame=frame.tolist(), center=center.tolist(), radius=radius,
                   residual=residual, lo=lo, hi=hi,
                   start=float(angles[(start_index + 1) % len(angles)]), span=span,
                   segments_before=before,
                   segments=min(segment_count(radius, span, False, epsilon, residual), before),
                   axis_refined_from_rails=True)


def refine_open_interval(vertices, feature, epsilon):
    """Measure an open strip's angular interval from its two boundary chains.

    The largest angular gap is not necessarily the missing sector of a coarse
    or uneven strip. Its actual boundary rails determine the endpoints.
    """
    if feature['full']:
        return
    p = (np.asarray(vertices)-feature['origin']) @ np.asarray(feature['frame']).T
    graph = defaultdict(set)
    for a, b in feature['boundary']:
        axial = abs(p[a, 2]-p[b, 2])
        radial = np.linalg.norm(p[a, :2]-p[b, :2])
        if axial > max(1e-12, radial*10):
            continue
        graph[a].add(b); graph[b].add(a)
    pending = set(graph); chains = []
    while pending:
        seed = min(pending); component = {seed}; stack = [seed]
        while stack:
            fresh = graph[stack.pop()]-component
            component.update(fresh); stack.extend(sorted(fresh))
        pending -= component
        ends = sorted(i for i in component if len(graph[i]) == 1)
        if len(ends) != 2 or any(len(graph[i]) > 2 for i in component):
            return
        chain = [ends[0]]
        while chain[-1] != ends[1]:
            following = graph[chain[-1]]-set(chain)
            if len(following) != 1:
                return
            chain.append(next(iter(following)))
        if len(chain) < 3:
            return
        xy = p[chain, :2]-feature['center']
        angles = np.unwrap(np.arctan2(xy[:, 1], xy[:, 0]))
        if angles[-1] < angles[0]:
            angles = angles[::-1]
        if np.any(np.diff(angles) <= 1e-7) or np.any(np.diff(angles) >= math.pi-1e-4):
            return
        chains.append((float(angles[0]), float(angles[-1]-angles[0]), len(chain)-1))
    if len(chains) != 2:
        return
    start, span, count = chains[0]
    other_start, other_span, other_count = chains[1]
    angle_error = abs((other_start-start+math.pi) % (2*math.pi)-math.pi)
    if angle_error > 1e-4 or abs(other_span-span) > 1e-4 or not 0 < span < 2*math.pi:
        return
    old_error = abs((feature['start']-start+math.pi) % (2*math.pi)-math.pi)
    if old_error <= 1e-4 and abs(feature['span']-span) <= 1e-4:
        return
    before = min(count, other_count)
    feature.update(start=start, span=span, segments_before=before,
                   segments=min(segment_count(feature['radius'], span, False,
                                              epsilon, feature['residual']), before),
                   interval_refined_from_boundary=True)


def discover(vertices, faces, epsilon=.0004, hole_detail_factor=1., hole_epsilon=None):
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
    max_radius = float(np.linalg.norm(np.ptp(v, axis=0))) * 10
    for axis in axes:
        frame=basis(axis); p=v@frame.T
        eligible=set(np.flatnonzero(abs(rn@frame[2])<.8).tolist())-discovered_regions
        # A cylinder's side-facet normal is perpendicular to its axial rails.
        # Only seed from such facets; keep existing tolerant support growth for
        # trimmed/noisy boundaries. This avoids testing every triangle against
        # hundreds of unrelated axis votes on curved assemblies.
        seeds = eligible & set(np.flatnonzero(
            abs(rn @ frame[2]) < math.sin(math.radians(.2))).tolist())
        tested=set(); accepted_support=[]
        for a in sorted(seeds):
            for b in [a]+sorted(ra[a]&seeds):
                if b<a:continue
                if any(a in s and b in s for s in accepted_support):continue
                seed=frozenset((a,b))
                ids=sorted(set(rverts[a])|set(rverts[b]))
                try:c,r,res=circle_fit(p[ids,:2])
                except ValueError:continue
                if res>1e-5 or r<1e-5 or r>max_radius:continue
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
                # A circle through a few corners also fits unrelated flat
                # walls. Require every facet to face the proposed radial side.
                radial_lengths=np.linalg.norm(rad,axis=1)
                agreement=np.sum((normals[fs]@frame.T)*rad,axis=1)*sign
                if np.any(agreement<=.5*radial_lengths):continue
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
    for feature in features:
        refine_rail_axis(vertices, feature, epsilon)
        refine_open_interval(vertices, feature, epsilon)
    from .geometry import hole_segment_count
    for feature in features:
        if feature['category']=='circular_hole':
            feature['segments']=hole_segment_count(
                feature['radius'], feature['segments_before'], epsilon,
                feature['residual'], hole_detail_factor, hole_epsilon)
            feature['hole_deviation_m']=epsilon if hole_epsilon is None else hole_epsilon
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
