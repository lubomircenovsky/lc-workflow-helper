"""Blender mesh IO and strictly role-restricted editable delivery."""
import hashlib,json,math
import bpy,bmesh,numpy as np

ROLES=['UNCLASSIFIED','DETAIL_REBUILT','PERIMETER_RING','BACKGROUND_PLANE','PROTECTED_OTHER','PERIMETER_STRAIGHT','LOCKED_FEATURE']


def source_topology(obj):
    from .geometry import topology
    return topology([list(poly.vertices) for poly in obj.data.polygons])


def topology_problem(obj, preserve_nonmanifold=False):
    counts=source_topology(obj)
    blocked=('boundary','winding','duplicates') if preserve_nonmanifold else ('boundary','nonmanifold','winding','duplicates')
    problems={key:counts[key] for key in blocked if counts[key]}
    if not problems:return ''
    detail=', '.join(f'{key}={count}' for key,count in problems.items())
    return f'{obj.name}: CAD source must be a closed manifold mesh ({detail}). Merge split vertices if needed, then repair and inspect the remaining topology.'


def fingerprint(obj):
    role=obj.data.attributes.get('cad_role')
    data=dict(v=[list(v.co) for v in obj.data.vertices],f=[list(p.vertices) for p in obj.data.polygons],
              n=[list(n.vector) for n in obj.data.corner_normals],matrix=[list(r) for r in obj.matrix_world],
              materials=[p.material_index for p in obj.data.polygons],
              sharp_edges=[list(e.vertices) for e in obj.data.edges if e.use_edge_sharp],
              cad_role=[value.value for value in role.data] if role and role.domain=='FACE' and role.data_type=='INT' else None)
    return hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()


def capture(obj,preserve_nonmanifold=False):
    if obj.type!='MESH' or obj.modifiers:raise ValueError('Requires a mesh without unevaluated modifiers')
    if bpy.context.mode!='OBJECT':raise ValueError('Object mode required')
    problem=topology_problem(obj,preserve_nonmanifold=preserve_nonmanifold)
    if problem:raise ValueError(problem)
    obj.data.calc_loop_triangles();scale=bpy.context.scene.unit_settings.scale_length
    from .geometry import face_normals
    m=np.array(obj.matrix_world,dtype=float);v=np.array([v.co[:] for v in obj.data.vertices])
    world=(v@m[:3,:3].T+m[:3,3])*scale
    faces=[list(p.vertices) for p in obj.data.polygons]
    # Authored split normals are not a geometric constraint for reconstruction.
    geometric=face_normals(world,faces)
    n=[normal.tolist() for normal,face in zip(geometric,faces) for _ in face]
    role=obj.data.attributes.get('cad_role')
    return dict(name=obj.name,source_hash=fingerprint(obj),unit_scale=scale,vertices=world.tolist(),
                faces=faces,triangles=[list(t.vertices) for t in obj.data.loop_triangles],
                normals=n,sharp_edges=[list(sorted(e.vertices)) for e in obj.data.edges if e.use_edge_sharp],
                materials=[p.material_index for p in obj.data.polygons],matrix=m.tolist(),
                cad_roles=[ROLES[value.value] for value in role.data]
                if role and role.domain=='FACE' and role.data_type=='INT' else None)


def make_mesh(candidate,name):
    origin=np.array(candidate['vertices']).mean(0)
    mesh=bpy.data.meshes.new(name);mesh.from_pydata((np.array(candidate['vertices'])-origin).tolist(),[],candidate['faces']);mesh.update()
    if mesh.validate(verbose=False):bpy.data.meshes.remove(mesh);raise ValueError('Blender had to repair candidate mesh')
    for p,mat in zip(mesh.polygons,candidate['materials']):p.material_index=mat;p.use_smooth=True
    sharp={tuple(edge) for edge in candidate.get('sharp_edges',[])}
    for edge in mesh.edges:
        edge.use_edge_sharp=tuple(sorted(edge.vertices)) in sharp
    role=mesh.attributes.new('cad_role','INT','FACE');role.data.foreach_set('value',[ROLES.index(r) for r in candidate['roles']])
    return mesh,origin


def cleanup(mesh):
    """Return a NEW mesh; retain validated checkpoint and its protected topology."""
    result=mesh.copy();result.name=mesh.name+'_Editable'
    before_edges={tuple(sorted(edge.vertices)) for edge in mesh.edges}
    sharp_edges={tuple(sorted(edge.vertices)) for edge in mesh.edges if edge.use_edge_sharp}
    bm=bmesh.new();bm.from_mesh(result);bm.faces.ensure_lookup_table();bm.verts.ensure_lookup_table()
    role=bm.faces.layers.int.get('cad_role')
    if role is None:bm.free();bpy.data.meshes.remove(result);raise ValueError('Missing explicit role map')
    def key(ids):return tuple(sorted(ids))
    old={key(p.vertices):{vi:list(mesh.corner_normals[li].vector) for vi,li in zip(p.vertices,p.loop_indices)} for p in mesh.polygons}
    protected={key(p.vertices):tuple(p.vertices) for p in mesh.polygons if mesh.attributes['cad_role'].data[p.index].value!=ROLES.index('BACKGROUND_PLANE')}
    eligible=[]
    for e in bm.edges:
        if len(e.link_faces)!=2:continue
        a,b=e.link_faces
        if a[role]!=ROLES.index('BACKGROUND_PLANE') or b[role]!=a[role]:continue
        if not e.smooth or e.seam or a.material_index!=b.material_index:continue
        if a.normal.dot(b.normal)<math.cos(math.radians(.1)):continue
        if max(abs((v.co-a.verts[0].co).dot(a.normal)) for v in b.verts)>1e-6:continue
        # Protect authored corner-normal discontinuities as well as sharp flags.
        ka,kb=key(v.index for v in a.verts),key(v.index for v in b.verts)
        if any(np.dot(old[ka][v.index],old[kb][v.index])<math.cos(math.radians(.1)) for v in e.verts):continue
        eligible.append(e)
    bmesh.ops.dissolve_edges(bm,edges=eligible,use_verts=False,use_face_split=False)
    bm.to_mesh(result);bm.free();result.update()
    # Blender ear-clipping of a concave n-gon with collinear boundary vertices
    # can create a zero-area or reversed loop triangle. Keep other large n-gons;
    # retriangulate only the offending background polygons with constrained CDT.
    result.calc_loop_triangles()
    vv=np.array([v.co[:] for v in result.vertices]);bad_polys=set()
    for tri in result.loop_triangles:
        p=vv[list(tri.vertices)];cross=np.cross(p[1]-p[0],p[2]-p[0]);poly=result.polygons[tri.polygon_index]
        if np.linalg.norm(cross)<=2e-16 or cross@np.array(poly.normal)<=0:
            if result.attributes['cad_role'].data[poly.index].value!=ROLES.index('BACKGROUND_PLANE'):
                bpy.data.meshes.remove(result);raise ValueError('Invalid triangulation in protected detail')
            bad_polys.add(poly.index)
    if bad_polys:
        from .geometry import basis,topology
        from .rebuild import tessellation,orient
        faces=[];face_roles=[];face_mats=[]
        for p in result.polygons:
            ids=list(p.vertices);r=result.attributes['cad_role'].data[p.index].value
            if p.index not in bad_polys:
                faces.append(ids);face_roles.append(r);face_mats.append(p.material_index);continue
            frame=basis(p.normal);points=((vv[ids]-vv[ids[0]])@frame.T)[:,:2]
            _,triangles=tessellation([points])
            for tri in triangles:
                if orient(*points[tri])<0:tri=tri[::-1]
                faces.append([ids[i] for i in tri]);face_roles.append(r);face_mats.append(p.material_index)
        before_top=topology([list(p.vertices) for p in result.polygons]);after_top=topology(faces)
        if any(before_top[k]!=after_top[k] for k in ('boundary','nonmanifold','winding','duplicates')):
            bpy.data.meshes.remove(result);raise ValueError('Local n-gon repair changed topology')
        replacement=bpy.data.meshes.new(result.name+'_Safe');replacement.from_pydata(vv.tolist(),[],faces);replacement.update()
        attr=replacement.attributes.new('cad_role','INT','FACE');attr.data.foreach_set('value',face_roles)
        for p,mat in zip(replacement.polygons,face_mats):p.material_index=mat
        bpy.data.meshes.remove(result);result=replacement
    new={key(p.vertices):tuple(p.vertices) for p in result.polygons}
    missing=[k for k in protected if k not in new]
    if missing:
        bpy.data.meshes.remove(result);raise ValueError('Protected faces lost during cleanup: '+str(len(missing)))
    result_edges={tuple(sorted(edge.vertices)):edge for edge in result.edges}
    if not sharp_edges <= result_edges.keys():
        bpy.data.meshes.remove(result);raise ValueError('Cleanup removed a protected sharp edge')
    for edge_key in sharp_edges:
        result_edges[edge_key].use_edge_sharp=True
    normals=[]
    for p in result.polygons:
        ns=old.get(key(p.vertices))
        normals.extend([ns[v] if ns else list(p.normal) for v in p.vertices]);p.use_smooth=True
    result.normals_split_custom_set(normals)
    if len(mesh.vertices)!=len(result.vertices) or any((a.co-b.co).length>0 for a,b in zip(mesh.vertices,result.vertices)):
        bpy.data.meshes.remove(result);raise ValueError('Cleanup changed vertices')
    roles=[ROLES[x.value] for x in result.attributes['cad_role'].data]
    after_edges={tuple(sorted(edge.vertices)) for edge in result.edges}
    return result,roles,dict(dissolved_edges=len(before_edges-after_edges),protected_faces=len(protected),protected_faces_lost=len(missing),locally_triangulated_ngons=len(bad_polys))
