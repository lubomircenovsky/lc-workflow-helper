"""Coordinated reconstruction of analytic cylinders and their incident planar domains."""
import math
from collections import Counter
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from .geometry import adjacency,face_normals,planar_regions,loops,basis,topology


def orient(a,b,c):
    u=b-a;v=c-a
    return float(u[0]*v[1]-u[1]*v[0])


def inside(p,poly):
    hit=False
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


def segment_distance(a,b,c,d):
    if orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0:return 0.
    def point_dist(p,x,y):
        t=np.clip((p-x)@(y-x)/max((y-x)@(y-x),1e-30),0,1)
        return np.linalg.norm(p-x-t*(y-x))
    return min(point_dist(a,c,d),point_dist(b,c,d),point_dist(c,a,b),point_dist(d,a,b))


def contacts(a,b):
    return any(segment_distance(x,y,z,w)<=1e-8 for x,y in zip(a,np.roll(a,-1,axis=0)) for z,w in zip(b,np.roll(b,-1,axis=0)))


def tessellation(boundaries):
    points=np.concatenate(boundaries);edges=[];offset=0
    for ring in boundaries:
        edges.extend((offset+i,offset+(i+1)%len(ring)) for i in range(len(ring)));offset+=len(ring)
    vv,_,ff,orig,_,_=delaunay_2d_cdt([Vector(p) for p in points],edges,[],0,1e-8,True)
    if any(len(ref)!=1 for ref in orig):raise ValueError('CDT created ambiguous/intersecting constraints')
    result=[]
    for f in ff:
        p=np.array([vv[i][:] for i in f]);mid=p.mean(0)
        if inside(mid,boundaries[0]) and not any(inside(mid,h) for h in boundaries[1:]):
            ids=[orig[i][0] for i in f]
            if abs(orient(*points[ids]))<1e-16:continue
            result.append(ids)
    return points,result


def annulus_quality(outer,inner):
    p,ff=tessellation([outer,inner])
    if len(ff)!=len(outer)+len(inner):return float('inf')
    return max(max(np.sum((p[f[(i+1)%3]]-p[f[i]])**2) for i in range(3))/max(abs(orient(*p[f])),1e-30) for f in ff)


def cylinder_rims(cy,p):
    """Two end chains, including planar oblique cuts of an open bend."""
    bd=sorted({i for e in cy['boundary'] for i in e});c=np.array(cy['center'])
    angular_tolerance=max(1e-4,2e-6/cy['radius'])
    angle={i:float((math.atan2(p[i,1]-c[1],p[i,0]-c[0])-cy['start'])%(2*math.pi)) for i in bd}
    angle={i:0. if abs(t-2*math.pi)<1e-4 else t for i,t in angle.items()}
    if cy['full']:
        rings=[[i for i in bd if abs(p[i,2]-level)<1e-6] for level in (cy['lo'],cy['hi'])]
    else:
        graph={}
        for a,b in cy['boundary']:
            # Near-coincident CAD vertices can form a tiny circumferential
            # edge at a rail endpoint. Remove axial rails only; dropping
            # that tiny end-chain edge loses the adjoining planar boundary.
            axial=abs(p[a,2]-p[b,2])
            radial=float(np.linalg.norm(p[a,:2]-p[b,:2]))
            if axial>max(1e-12,radial*10) and any(abs(angle[a]-t)<angular_tolerance and abs(angle[b]-t)<angular_tolerance for t in (0.,cy['span'])):continue
            graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
        pending=set(graph);rings=[]
        while pending:
            comp={min(pending)};stack=list(comp);pending-=comp
            while stack:
                fresh=graph[stack.pop()]&pending;comp|=fresh;pending-=fresh;stack.extend(fresh)
            if any(len(graph[i])>2 for i in comp):raise ValueError('Branching cylinder end contour')
            rings.append(sorted(comp,key=lambda i:angle[i]))
        rings=[r for r in rings if len(r)>=3]
        if len(rings)!=2:
            constant=[[i for i in bd if abs(p[i,2]-level)<1e-6] for level in (cy['lo'],cy['hi'])]
            if all(len(r)>=3 and min(angle[i] for i in r)<angular_tolerance and abs(max(angle[i] for i in r)-cy['span'])<angular_tolerance for r in constant):rings=constant
            else:raise ValueError('Expected two cylinder end contours: '+str((cy['id'],[len(r) for r in rings])))
        rings.sort(key=lambda ids:float(p[ids,2].mean()))
    result=[]
    for ids in rings:
        if len(ids)<3:raise ValueError('Cylinder end contour has fewer than three samples')
        points=p[ids];center=points.mean(0);_,_,vh=np.linalg.svd(points-center,full_matrices=False);normal=vh[-1]
        if np.max(abs((points-center)@normal))>1e-6 or abs(normal[2])<1e-5:
            # Retain a trimmed end's measured axial profile rather than forcing
            # a constant extrusion or planar cap. Full validation bounds error.
            result.append((ids,None,None))
        else:result.append((ids,normal,float(normal@center)))
    return result


def choose_perimeter(hole,outer,obstacles,radius=None,center=None):
    attempts=[]
    center=hole.mean(0) if center is None else center
    sizes=list(dict.fromkeys([max(radius+max(.002,.25*radius),.008),radius+max(.002,.25*radius),radius+max(.002,.125*radius),radius+.002,radius+.001,radius+.0005,radius+.00025])) if radius else [None]
    for size in sizes:
        for degree in [0,15,30,45,60,75]:
            a=math.radians(degree);rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
            if radius:
                corners=np.array([[-size,-size],[size,-size],[size,size],[-size,size]])@rot.T+center
            else:
                local=(hole-center)@rot;low=local.min(0)-.002;high=local.max(0)+.002
                corners=np.array([[low[0],low[1]],[high[0],low[1]],[high[0],high[1]],[low[0],high[1]]])@rot.T+center
            reason=None
            if not all(inside(p,outer) for p in corners) or contacts(corners,outer):reason='outer_boundary'
            elif not all(inside(p,corners) for p in hole):reason='does_not_enclose_hole'
            elif any(contacts(corners,o) or any(inside(p,corners) for p in o) or inside(corners[0],o) for o in obstacles):reason='other_feature'
            if reason:
                attempts.append(dict(degree=degree,size=size,rejected=reason));continue
            for divisions in ([1,2,4,8,16] if radius else [1,2,4,8,16,32,64]):
                sq=np.array([p+(q-p)*k/divisions for p,q in zip(corners,np.roll(corners,-1,axis=0)) for k in range(divisions)])
                q=annulus_quality(sq,hole)
                attempts.append(dict(degree=degree,size=size,divisions=divisions,q=q))
                if q<=20:return sq,attempts
    raise ValueError('UNRESOLVED_PERIMETER: '+str(attempts))


def reconstruct(snapshot,features):
    V=np.array(snapshot['vertices'],dtype=float);F=snapshot['faces'];vertices=V.tolist()
    normals=face_normals(V,F);ef,adj=adjacency(F)
    keep=np.ones(len(V),dtype=bool);changed=set();grids={};fullrings={};claimed=set();rim_alias={};rail_points={}
    CY=[c for c in features if c.get('decision','REBUILD')=='REBUILD']
    for cy in CY:
        if claimed.intersection(cy['faces']):raise ValueError('Overlapping cylinder ownership')
        claimed.update(cy['faces'])
        frame=np.array(cy['frame']);origin=np.array(cy['origin']);p=(V-origin)@frame.T
        c=np.array(cy['center']);n=cy['segments'];boundary=sorted({i for e in cy['boundary'] for i in e});rows=[];chosen=set()
        for ids,end_normal,end_d in cylinder_rims(cy,p):
            level=float(p[ids,2].mean())
            theta={i:float((math.atan2(p[i,1]-c[1],p[i,0]-c[0])-cy['start'])%(2*math.pi)) for i in ids}
            theta={i:0. if abs(a-2*math.pi)<1e-4 else a for i,a in theta.items()}
            row=[]
            for k in range(n if cy['full'] else n+1):
                angle=cy['span']*k/n
                def distance(i):
                    d=abs(theta[i]-angle)
                    return min(d,2*math.pi-d) if cy['full'] else d
                vi=min(ids,key=distance)
                if vi in row:raise ValueError('Too few independent rim samples for requested reconstruction: '+str((cy['id'],len(ids),n,level,cy['category'])))
                if cy['full'] or k not in (0,n):
                    a=cy['start']+angle;xy=c+cy['radius']*np.array([math.cos(a),math.sin(a)])
                    if end_normal is None:
                        ordered=sorted(ids,key=lambda i:theta[i])
                        z=float(np.interp(angle,[theta[i] for i in ordered],p[ordered,2]))
                    else:z=(end_d-end_normal[:2]@xy)/end_normal[2]
                    target=np.array([*xy,z])@frame+origin
                    if vi in changed and np.linalg.norm(np.array(vertices[vi])-target)>1e-6:raise ValueError('Conflicting shared analytic endpoint')
                    vertices[vi]=target.tolist();changed.add(vi)
                row.append(vi);chosen.add(vi)
            rows.append(row)
            # The same rim also bounds nonplanar transition surfaces. Those
            # surfaces need a consistent edge contraction, not deleted corners.
            for vi in ids:
                def sample_distance(k):
                    d=abs(theta[vi]-cy['span']*k/n)
                    return min(d,2*math.pi-d) if cy['full'] else d
                replacement=row[min(range(len(row)),key=sample_distance)]
                if vi in rim_alias and rim_alias[vi]!=replacement:
                    raise ValueError('Conflicting shared transition rim mapping')
                rim_alias[vi]=replacement
            if cy['full']:fullrings[frozenset(ids)]=(cy,row)
        # Intermediate rail vertices may connect long adjacent flat surfaces.
        # Keep their measured contour instead of contracting it to the caps.
        rails=[i for i in boundary if i not in rim_alias and i not in chosen]
        rail_points[cy['id']]=rails;chosen.update(rails)
        for vi in cy['vertices']:
            if vi not in chosen:keep[vi]=False
        grids[cy['id']]=rows
    retained={i for rows in grids.values() for row in rows for i in row}
    if any(not keep[i] for i in retained):raise ValueError('Shared retained/deleted vertex conflict')
    changed.update(np.flatnonzero(~keep).tolist())
    groups=planar_regions(V,F,normals,adj,claimed)
    corners=np.array(snapshot['normals']);off=np.cumsum([0]+[len(f) for f in F])
    outfaces=[];outnormals=[];roles=[];tags=[];materials=[];patches=[];perimeters=[];transitions=[];split_edges={}
    def add(ids,ns,role,tag,mat=0):
        if len(set(ids))!=len(ids) or len(ids)<3:raise ValueError('Degenerate face')
        outfaces.append(list(map(int,ids)));outnormals.append(np.asarray(ns).tolist());roles.append(role);tags.append(tag);materials.append(int(mat))
    def point(p):vertices.append(np.asarray(p).tolist());return len(vertices)-1
    for gid,fs in enumerate(groups):
        touched=any(changed.intersection(F[fi]) for fi in fs)
        if not touched:
            # Regions untouched by reconstruction are not automatically eligible for dissolve.
            for fi in fs:add(F[fi],corners[off[fi]:off[fi+1]],'PROTECTED_OTHER','retained',snapshot['materials'][fi])
            continue
        normal=normals[fs[0]];origin=V[F[fs[0]][0]];frame=basis(normal)
        ids=sorted({i for fi in fs for i in F[fi]})
        attached=[cy for cy in CY if set(ids)&set(cy['vertices'])]
        boundary_loops=loops([F[i] for i in fs])
        collapsed_boundary=any(sum(bool(keep[i]) for i in ring)<3 for ring in boundary_loops)
        if (attached and all(keep[i] or i in rim_alias for i in ids)
                and (collapsed_boundary or not any(abs(normal@np.array(cy['frame'])[2])>=math.cos(math.radians(.1)) for cy in attached))):
            new_faces=[];collapsed=[]
            for fi in fs:
                mapped=[rim_alias.get(i,i) for i in F[fi]]
                if any(not keep[i] for i in mapped):raise ValueError('Unmapped nonplanar transition vertex')
                unique=[];ns=[]
                for k,vi in enumerate(mapped):
                    if not unique or vi!=unique[-1]:unique.append(vi);ns.append(corners[off[fi]+k])
                if len(unique)>1 and unique[-1]==unique[0]:unique.pop();ns.pop()
                if len(unique)<3:collapsed.append(fi);continue
                if len(set(unique))!=len(unique):raise ValueError('Transition contraction creates a self-touching face')
                p=np.array([vertices[i] for i in unique]);cr=np.cross(p[1:-1]-p[0],p[2:]-p[0]).sum(0)
                if np.linalg.norm(cr)<2e-16:raise ValueError('Transition contraction creates a zero-area face')
                if cr@normals[fi]<=0:raise ValueError('Transition contraction flips a face')
                add(unique,ns,'DETAIL_REBUILT','transition_'+str(gid),snapshot['materials'][fi]);new_faces.append(len(outfaces)-1)
            transitions.append(dict(patch=gid,old_faces=fs,new_faces=new_faces,contracted_faces=collapsed))
            continue
        if max(abs((V[ids]-origin)@normal))>1e-6:raise ValueError('Unsupported nonplanar incident patch')
        def uv(i):return ((np.array(vertices[i])-origin)@frame.T)[:2]
        def area(ring):return sum(orient(np.zeros(2),uv(a),uv(b)) for a,b in zip(ring,ring[1:]+ring[:1]))/2
        oldloops=boundary_loops;newloops=[]
        for ring in oldloops:
            mapped=[]
            for i in ring:
                vi=rim_alias.get(i,i)
                if keep[vi] and (not mapped or mapped[-1]!=vi):mapped.append(vi)
            if len(mapped)>1 and mapped[-1]==mapped[0]:mapped.pop()
            # Contract a backtracking spike created when both sides of a
            # short source contour collapse to the same retained rim sample.
            while len(mapped)>=3:
                spike=next((k for k in range(len(mapped)) if mapped[k-1]==mapped[(k+1)%len(mapped)]),None)
                if spike is None:break
                mapped=mapped[spike-1:]+mapped[:spike-1] if spike else mapped[-1:]+mapped[:-1]
                mapped=mapped[2:]
            if len(set(mapped))!=len(mapped):raise ValueError('Planar boundary contraction creates a self-touching contour')
            newloops.append(mapped)
        if any(len(ring)<3 for ring in newloops):raise ValueError('Collapsed incident patch')
        order=sorted(range(len(newloops)),key=lambda k:-abs(area(newloops[k])))
        oldloops=[oldloops[k] for k in order];newloops=[newloops[k] for k in order]
        outer=np.array([uv(i) for i in newloops[0]]);outside=[newloops[0]];annuli=[];squares=[];layouts=[]
        # Plan larger features first, reserving enough clearance for a minimum
        # square of every still-unplanned circular neighbour in any orientation.
        hole_pairs=sorted(zip(oldloops[1:],newloops[1:]),key=lambda pair:-abs(area(pair[1])))
        processed=set()
        for old,ring in hole_pairs:
            entry=fullrings.get(frozenset(old));affected=any(set(old)&set(cy['vertices']) for cy in CY)
            if not affected:outside.append(ring);continue
            hole=np.array([uv(i) for i in ring]);obstacles=[]
            for other_old,other_ring in hole_pairs:
                if other_ring is ring:continue
                xy=np.array([uv(i) for i in other_ring]);other_entry=fullrings.get(frozenset(other_old))
                if other_entry and frozenset(other_old) not in processed:
                    reserve=math.sqrt(2)*(other_entry[0]['radius']+.00025)/math.cos(math.pi/32)
                    angles=np.arange(32)*2*math.pi/32
                    xy=xy.mean(0)+reserve*np.column_stack((np.cos(angles),np.sin(angles)))
                obstacles.append(xy)
            obstacles+=squares
            radius=entry[0]['radius'] if entry else None
            from .sparse_perimeter import choose as choose_sparse
            sparse=choose_sparse(hole,outer,obstacles) if radius is None else None
            if radius is None and sparse is None:
                # Large cutouts have long straight wall edges. A narrow local
                # annulus cannot meet Q if those edges remain a single segment.
                refined=[]
                for a,b in zip(ring,ring[1:]+ring[:1]):
                    length=np.linalg.norm(np.array(vertices[b])-vertices[a]);divisions=max(1,math.ceil(length/.02))
                    if divisions>1:
                        seq=split_edges.get((a,b))
                        if seq is None:
                            seq=[a]+[point(np.array(vertices[a])+(np.array(vertices[b])-vertices[a])*k/divisions) for k in range(1,divisions)]+[b]
                            split_edges[(a,b)]=seq;split_edges[(b,a)]=seq[::-1]
                        refined.extend(seq[:-1])
                    else:refined.append(a)
                ring=refined;hole=np.array([uv(i) for i in ring])
            center=None
            if entry:
                cy=entry[0];cp=np.array([*cy['center'],np.mean([(V[i]-cy['origin'])@np.array(cy['frame'])[2] for i in old])])@np.array(cy['frame'])+cy['origin']
                center=((cp-origin)@frame.T)[:2]
            sq,attempts=sparse if sparse is not None else choose_perimeter(hole,outer,obstacles,radius,center)
            square=[point(origin+x[0]*frame[0]+x[1]*frame[1]) for x in sq]
            outside.append(square);annuli.append((square,ring));squares.append(sq)
            layout=attempts[-1] if sparse is not None else None
            layouts.append(layout);ids_all=square+ring
            perimeters.append(dict(patch=gid,ids=square,hole=ring,attempts=attempts,
                                   kind='circular' if radius is not None else 'compound',
                                   layout='straight_strips' if layout else 'triangulated',
                                   strips=[[ids_all[i] for i in f] for f in layout['strips']] if layout else []))
            processed.add(frozenset(old))
        def tess(boundaries,role,tag):
            rings=[np.array([uv(i) for i in ring]) for ring in boundaries]
            points,tri=tessellation(rings);index=[i for ring in boundaries for i in ring];added=[]
            for face in tri:
                out=[index[i] for i in face]
                if orient(*points[face])<0:out.reverse()
                add(out,[normal]*3,role,tag,snapshot['materials'][fs[0]]);added.append(len(outfaces)-1)
            expected=abs(area(boundaries[0]))-sum(abs(area(r)) for r in boundaries[1:])
            actual=sum(abs(orient(*points[f]))/2 for f in tri)
            if abs(actual-expected)>max(1e-10,expected*1e-7):raise ValueError('Planar coverage mismatch')
            return added
        # A cap touching several cylinders is a rebuilt detail, not background.
        attached=[cy for cy in CY if set(ids)&set(cy['vertices'])]
        cap=bool(attached) and not annuli and all(abs(normal@np.array(cy['frame'])[2])>.999 for cy in attached) and len(ids)<200
        role='DETAIL_REBUILT' if cap else 'BACKGROUND_PLANE'
        new=tess(outside,role,'plane_'+str(gid))
        for ai,(square,ring) in enumerate(annuli):
            layout=layouts[ai];tag=f'annulus_{gid}_{ai}'
            if layout is None:tess([square,ring],'PERIMETER_RING',tag)
            else:
                ids_all=square+ring
                for f in layout['strips']:
                    ids_strip=[ids_all[i] for i in f]
                    add(ids_strip,[normal]*len(ids_strip),'PERIMETER_STRAIGHT',tag,snapshot['materials'][fs[0]])
                for f in layout['corner_regions']:tess([[ids_all[i] for i in f]],'PERIMETER_RING',tag)
        patches.append(dict(id=gid,old_faces=fs,new_faces=new,role=role))
    for cy in CY:
        rows=grids[cy['id']];frame=np.array(cy['frame']);origin=np.array(cy['origin']);c=np.array(cy['center'])
        for k in range(cy['segments']):
            j=(k+1)%len(rows[0]);ids=[rows[0][k],rows[0][j],rows[1][j],rows[1][k]]
            if not cy['full']:
                expanded=[]
                for a,b in zip(ids,ids[1:]+ids[:1]):
                    expanded.append(a)
                    if (a,b) not in [(rows[0][0],rows[1][0]),(rows[1][0],rows[0][0]),(rows[0][-1],rows[1][-1]),(rows[1][-1],rows[0][-1])]:continue
                    pa=np.array(vertices[a]);pb=np.array(vertices[b]);delta=pb-pa;length2=float(delta@delta)
                    candidates=[]
                    for vi in rail_points[cy['id']]:
                        t=float((V[vi]-pa)@delta/max(length2,1e-30))
                        if 0<t<1 and np.linalg.norm(V[vi]-pa-t*delta)<1e-6:candidates.append((t,vi))
                    expanded.extend(i for _,i in sorted(candidates))
                ids=expanded
            p=np.array([vertices[i] for i in ids]);q=(p-origin)@frame.T
            radial=np.array([*(q[:,:2].mean(0)-c),0.])@frame
            if np.cross(p[1]-p[0],p[2]-p[0])@radial*cy['sign']<0:ids.reverse()
            ns=[]
            for i in ids:
                pt=(np.array(vertices[i])-origin)@frame.T;nn=np.array([*(pt[:2]-c),0.])@frame
                ns.append(nn/np.linalg.norm(nn)*cy['sign'])
            add(ids,ns,'DETAIL_REBUILT','cylinder_'+str(cy['id']),snapshot['materials'][cy['faces'][0]])
    # Propagate annulus edge subdivisions into every incident wall. Explicit
    # constrained triangles avoid T-junctions and collinear n-gon tessellation.
    original_count=len(outfaces);omit=set()
    for fi in range(original_count):
        f=outfaces[fi]
        if not any((a,b) in split_edges for a,b in zip(f,f[1:]+f[:1])):continue
        poly=[];ns=[]
        for k,(a,b) in enumerate(zip(f,f[1:]+f[:1])):
            seq=split_edges.get((a,b),[a,b])
            for j,vi in enumerate(seq[:-1]):
                t=j/(len(seq)-1);nn=(1-t)*np.array(outnormals[fi][k])+t*np.array(outnormals[fi][(k+1)%len(f)])
                poly.append(vi);ns.append(nn/max(np.linalg.norm(nn),1e-30))
        pts=np.array([vertices[i] for i in poly]);normal=face_normals(np.array(vertices),[f])[0];frame=basis(normal)
        if np.max(abs((pts-pts[0])@normal))>1e-6:raise ValueError('Cannot propagate a perimeter subdivision into a nonplanar wall')
        _,tri=tessellation([((pts-pts[0])@frame.T)[:,:2]])
        for indices in tri:
            out=[poly[i] for i in indices]
            if np.cross(np.array(vertices[out[1]])-vertices[out[0]],np.array(vertices[out[2]])-vertices[out[0]])@normal<0:indices=indices[::-1];out=out[::-1]
            add(out,[ns[i] for i in indices],roles[fi],tags[fi],materials[fi])
        omit.add(fi)
    if omit:
        outfaces=[x for i,x in enumerate(outfaces) if i not in omit];outnormals=[x for i,x in enumerate(outnormals) if i not in omit]
        roles=[x for i,x in enumerate(roles) if i not in omit];tags=[x for i,x in enumerate(tags) if i not in omit];materials=[x for i,x in enumerate(materials) if i not in omit]
        for patch in patches:patch['new_faces']=[i for i,t in enumerate(tags) if t=='plane_'+str(patch['id'])]
        for patch in transitions:patch['new_faces']=[i for i,t in enumerate(tags) if t=='transition_'+str(patch['patch'])]
    used=sorted({i for f in outfaces for i in f});remap={i:k for k,i in enumerate(used)}
    result=dict(vertices=[vertices[i] for i in used],faces=[[remap[i] for i in f] for f in outfaces],normals=outnormals,roles=roles,tags=tags,materials=materials,patches=patches,perimeters=perimeters,transitions=transitions)
    for p in perimeters:
        p['ids']=[remap[i] for i in p['ids']];p['hole']=[remap[i] for i in p['hole']]
        p['strips']=[[remap[i] for i in f] for f in p['strips']]
    result['topology']=topology(result['faces'])
    if any(result['topology'][k] for k in ['boundary','nonmanifold','winding','duplicates']):raise ValueError('Candidate topology failed: '+str(result['topology']))
    return result
