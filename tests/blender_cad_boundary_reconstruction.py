"""Regression: close holes without support loops and subdivided bend rails."""
import math
import sys
from types import SimpleNamespace
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.mesh_io import capture, fingerprint
from cad_mesh_tool.geometry import face_normals
from cad_mesh_tool.rebuild import cylinder_rims, tessellation
from cad_mesh_tool.recovery import decisions
from cad_mesh_tool.worker import validated_candidate

options = dict(circular_holes=True, perimeter_loops=False, arcs=True,
               outer_cylinders=True, background_cleanup=True, straight_walls=True)


def check(vertices, faces, expected_category, expected_count, support=False):
    mesh = bpy.data.meshes.new('Boundary source')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Boundary source', mesh)
    bpy.context.scene.collection.objects.link(obj)
    source = capture(obj)
    plan = discover(source['vertices'], source['faces'], .0015, .5, .0015)
    features = [f for f in plan['features'] if f['category'] == expected_category]
    assert len(features) == expected_count, plan
    selected_options=dict(options,perimeter_loops=support)
    candidate, result, origin, validation = validated_candidate(
        source, decisions(plan['features'], selected_options), selected_options,
        dict(epsilon_m=.0015, sample_count=2000,perimeter_clearance_mm=1.5))
    assert all(validation['checks'].values()), validation['checks']
    assert len(result.loop_triangles) < len(source['triangles'])
    if support:
        assert len(candidate['perimeters'])==2*expected_count
        assert all(p.get('layout')!='direct_join' for p in candidate['perimeters'])
    bpy.data.meshes.remove(result)
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)


outer = np.array([[-.1,-.05],[.1,-.05],[.1,.05],[-.1,.05]])
angles = np.arange(36) * math.tau / 36
holes = [np.array([x,0.]) + .02 * np.column_stack((np.cos(angles),np.sin(angles)))
         for x in (-.023,.023)]
points, triangles = tessellation([outer] + holes)
count = len(points)
vertices = [[x,y,z] for z in (0.,.008) for x,y in points]
faces = [list(reversed(f)) for f in triangles]
faces += [[i + count for i in f] for f in triangles]
offset = 0
for ring_index, ring in enumerate([outer] + holes):
    for i in range(len(ring)):
        a=offset+i;b=offset+(i+1)%len(ring)
        face=[a,b,b+count,a+count]
        faces.append(face if ring_index == 0 else face[::-1])
    offset += len(ring)
check(vertices, faces, 'circular_hole', 2)
check(vertices, faces, 'circular_hole', 2, support=True)

# Multiple source rail edges must remain incident to both adjoining surfaces.
radius=.01
angles=np.linspace(-math.pi/2,-math.pi,17)
arc=[radius,radius]+radius*np.column_stack((np.cos(angles),np.sin(angles)))
outline=np.vstack((arc,[[0,.04],[.04,.04],[.04,0]]))[::-1]
points,triangles=tessellation([outline]);count=len(points)
levels=np.linspace(0.,1.6,5)
vertices=[[x,y,z] for z in levels for x,y in points]
faces=[list(reversed(f)) for f in triangles]
faces += [[i+4*count for i in f] for f in triangles]
for row in range(4):
    for i in range(count):
        j=(i+1)%count
        faces.append([row*count+i,row*count+j,(row+1)*count+j,(row+1)*count+i])
check(vertices,faces,'convex_arc',1)

# The lower end of a trimmed rail lies inside the fitted angular interval.
theta=np.linspace(.065,4.936,29)
points=[[.02*math.cos(a),.02*math.sin(a),z] for z in (0.,.008) for a in theta]
points += [[.02,0.,0.], [points[0][0],points[0][1],.002],
           [points[0][0],points[0][1],.004]]
boundary=[(i,i+1) for i in range(28)]+[(i,i+1) for i in range(29,57)]
boundary += [(28,57),(29,60),(60,59),(59,0),(0,58),(58,1)]
# Replace the original first lower edge with the small measured notch.
boundary.remove((0,1))
cy=dict(id=0,boundary=boundary,center=[0.,0.],radius=.02,start=0.,span=4.936,
        full=False,lo=0.,hi=.008)
rims=cylinder_rims(cy,np.array(points))
assert len(rims)==2
assert 58 in set(rims[0][0])|set(rims[1][0])

# Reusing a near-planar editable n-gon must not create an orthogonal sliver
# triangle along its almost collinear boundary. Capture repairs the reference
# tessellation only, retaining the mesh and its exact fingerprint.
vertices=[[0.8247134685516357,-0.10296623408794403,0.28049758076667786],
          [0.8243334293365479,-0.10169701278209686,0.27634623646736145],
          [0.8232057094573975,-0.1004662960767746,0.27232077717781067],
          [0.8213639259338379,-0.09931163489818573,0.2685437500476837],
          [1.0097131729125977,-0.09273330867290497,0.247026726603508],
          [1.0097131729125977,-0.11319927871227264,0.3139682114124298],
          [1.0097131729125977,-0.12635593116283417,0.35700204968452454],
          [0.9797132015228271,-0.135126993060112,0.38569095730781555],
          [0.8372135162353516,-0.135126993060112,0.38569095730781555],
          [0.8232057094573975,-0.10546605288982391,0.28867438435554504],
          [0.8243334293365479,-0.1042354553937912,0.28464916348457336]]
mesh=bpy.data.meshes.new('Near-collinear n-gon')
mesh.from_pydata(vertices,[],[list(range(len(vertices)))]);mesh.update()
obj=bpy.data.objects.new('Near-collinear n-gon',mesh)
bpy.context.scene.collection.objects.link(obj)
before=fingerprint(obj)
# Reproduce the cached tessellation from the earlier editable result. A fresh
# from_pydata may choose different ears even with identical polygon vertices.
class CachedTriangles:
    def __init__(self,data):self.data=data
    def __getattr__(self,name):return getattr(self.data,name)
    def calc_loop_triangles(self):pass
    loop_triangles=[SimpleNamespace(vertices=tri,polygon_index=0) for tri in
                    ([2,3,4],[4,5,6],[6,7,8],[8,9,10],[8,10,0],
                     [4,6,8],[1,2,4],[8,0,1],[1,4,8])]
proxy=SimpleNamespace(type=obj.type,modifiers=obj.modifiers,matrix_world=obj.matrix_world,
                      name=obj.name,data=CachedTriangles(mesh))
source=capture(proxy,check_topology=False)
assert source['source_triangulation_repaired_faces']==[0],source
assert fingerprint(obj)==before
p=np.array(source['vertices']);normal=face_normals(p,source['faces'])[0]
for tri in source['triangles']:
    cross=np.cross(p[tri[1]]-p[tri[0]],p[tri[2]]-p[tri[0]])
    assert cross@normal>.99*np.linalg.norm(cross)
print('CAD_BOUNDARY_RECONSTRUCTION_OK')
print('PASS blender_cad_boundary_reconstruction')
