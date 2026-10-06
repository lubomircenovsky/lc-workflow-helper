"""Headless regression: user-protected faces stay exactly as authored.

blender --background --factory-startup --python tests/blender_cad_protected.py
"""
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import prepare_selected
from cad_mesh_tool.mesh_io import capture, fingerprint
from cad_mesh_tool.protected import ATTRIBUTE, faces_from_mesh
from cad_mesh_tool.rebuild import tessellation
from cad_mesh_tool.worker import main as run_worker

outer = np.array([[-.06, -.03], [.06, -.03], [.06, .03], [-.06, .03]])
angles = np.arange(32) * math.tau / 32
circle = .0065 * np.column_stack((np.cos(angles), np.sin(angles)))
holes = [circle + (-.03, 0.), circle + (.03, 0.)]
# Square support rings keep each hole's cap triangles separate, as in a
# typical CAD sheet; a shared triangle would make the holes interdependent.
rings = [np.array([[-.012, -.012], [.012, -.012], [.012, .012], [-.012, .012]]) + center
         for center in ((-.03, 0.), (.03, 0.))]
points, triangles = tessellation([outer, *rings])
for ring, hole in zip(rings, holes):
    local_points, local_triangles = tessellation([ring, hole])
    index = []
    for point in local_points:
        match = np.flatnonzero(np.all(np.abs(points - point) < 1e-12, axis=1)) if len(points) else []
        if len(match):
            index.append(int(match[0]))
        else:
            points = np.vstack([points, point]); index.append(len(points) - 1)
    triangles = list(triangles) + [[index[i] for i in face] for face in local_triangles]
count = len(points)
hole_ids = [[int(np.flatnonzero(np.all(np.abs(points - q) < 1e-12, axis=1))[0]) for q in hole] for hole in holes]
vertices = [(x, y, z) for z in (0., .004) for x, y in points]
faces = [list(reversed(face)) for face in triangles]
faces += [[count + i for i in face] for face in triangles]
walls = {}
for index, (ids, reverse) in enumerate(((list(range(4)), False), (hole_ids[0], True), (hole_ids[1], True))):
    walls[index] = []
    for a, b in zip(ids, ids[1:] + ids[:1]):
        walls[index].append(len(faces))
        faces.append([b, a, a + count, b + count] if reverse else [a, b, b + count, a + count])


def build(name, protected):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    if protected is not None:
        attr = mesh.attributes.new(ATTRIBUTE, 'BOOLEAN', 'FACE')
        values = [False] * len(mesh.polygons)
        for fi in protected:
            values[fi] = True
        attr.data.foreach_set('value', values)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def legacy_fingerprint(obj):
    role = obj.data.attributes.get('cad_role')
    data = dict(v=[list(v.co) for v in obj.data.vertices], f=[list(p.vertices) for p in obj.data.polygons],
                n=[list(n.vector) for n in obj.data.corner_normals], matrix=[list(r) for r in obj.matrix_world],
                materials=[p.material_index for p in obj.data.polygons],
                sharp_edges=[list(e.vertices) for e in obj.data.edges if e.use_edge_sharp],
                cad_role=[value.value for value in role.data] if role and role.domain == 'FACE' and role.data_type == 'INT' else None)
    return hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()


def run(obj, operations=None):
    root = Path(tempfile.mkdtemp(prefix='cad_protected_')) / 'run'
    prepare_selected(root, epsilon_mm=.4, obj=obj, operations=operations)
    run_worker(root, {})
    manifest = json.loads((root / 'manifest.json').read_text())
    candidate = json.loads((root / 'candidate.json').read_text())
    validation = json.loads((root / 'validation_final.json').read_text())
    with bpy.data.libraries.load(str(root / 'result.blend'), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in manifest['objects'] and 'Checkpoint' not in n]
    result = dst.objects[0]
    from mathutils import Matrix
    matrix = Matrix(manifest['result_matrix_world'])  # apply_result() restores it the same way
    world = np.array([tuple(matrix @ v.co) for v in result.data.vertices])
    return manifest, candidate, validation, result, world


def output_face_set(result, world, source_faces):
    """Map each source face to output vertex IDs by position (float32 output)."""
    def nearest(point):
        distance = np.linalg.norm(world - np.asarray(point), axis=1)
        index = int(np.argmin(distance))
        return index if distance[index] < 1e-6 else None
    polygons = {frozenset(p.vertices) for p in result.data.polygons}
    missing = []
    for face in source_faces:
        ids = [nearest(vertices[vi]) for vi in face]
        if None in ids or frozenset(ids) not in polygons:
            missing.append(face)
    return missing


# Unprotected meshes keep their previous fingerprint; protection changes it.
plain = build('Plain', None)
assert fingerprint(plain) == legacy_fingerprint(plain)
assert capture(plain)['user_protected_faces'] == []

# 1) Protect the walls of the first hole: it stays, the second is reduced.
obj = build('Protected Hole', walls[1])
assert faces_from_mesh(obj.data) == walls[1]
assert fingerprint(obj) != legacy_fingerprint(obj)
manifest, candidate, validation, result, world = run(obj)
assert manifest['geometry_status'] == 'PASS', manifest
assert validation['checks']['user_protected_preserved'] is True
assert manifest['user_protected_faces'] == 32
assert len(manifest['user_protected_features']) == 1
assert not manifest['partial'], 'intended protection alone is not a review finding'
targets = {item['id']: item for item in manifest['hole_segment_targets']}
protected_id = manifest['user_protected_features'][0]
other = [fid for fid in targets if fid != protected_id]
assert other and all(targets[fid]['target'] < 32 for fid in other)
assert manifest['operation_results']['curves_reduced'] >= 1
assert not output_face_set(result, world, [faces[fi] for fi in walls[1]]), 'protected wall faces must remain as authored'

# 2) Protect one cap triangle between the holes; both holes are still reduced.
corner = min(range(len(triangles)), key=lambda fi: np.linalg.norm(points[triangles[fi]].mean(0)))
manifest, candidate, validation, result, world = run(build('Protected Cap', [corner]))
assert manifest['geometry_status'] == 'PASS', manifest
assert validation['checks']['user_protected_preserved'] is True
assert manifest['user_protected_features'] == [], manifest['user_protected_features']
assert manifest['operation_results']['curves_reduced'] >= 2, manifest['skipped_features']
assert all(item['target'] < 32 for item in manifest['hole_segment_targets'])
assert not output_face_set(result, world, [faces[corner]]), 'protected cap face must remain as authored'

# 3) The protection travels with the result: a second reconstruction of the
#    first result keeps the same faces protected without re-marking them.
first_ops = dict(perimeter_loops=False, background_cleanup=False, straight_walls=False)
obj = build('Protected Chain', walls[1])
manifest, candidate, validation, result, world = run(obj, first_ops)
assert manifest['geometry_status'] == 'PASS', manifest
assert manifest['user_protected_faces_marked']['final'] == 32, manifest['user_protected_faces_marked']
flagged = faces_from_mesh(result.data)
assert len(flagged) == 32, len(flagged)
wall_points = np.array([vertices[vi] for fi in walls[1] for vi in faces[fi]])
flagged_points = np.array([world[vi] for fi in flagged for vi in result.data.polygons[fi].vertices])
gaps = np.min(np.linalg.norm(flagged_points[:, None] - wall_points[None], axis=2), axis=1)
assert gaps.max() < 1e-6, f'marked faces are the protected walls (max gap {gaps.max()})'
from mathutils import Matrix
result.matrix_world = Matrix(manifest['result_matrix_world'])
bpy.context.scene.collection.objects.link(result)
assert len(capture(result)['user_protected_faces']) == 32
second, _, second_validation, second_result, second_world = run(result)
assert second['geometry_status'] == 'PASS', second
assert second_validation['checks']['user_protected_preserved'] is True
assert second['user_protected_faces'] == 32 and len(second['user_protected_features']) == 1
assert second['user_protected_faces_marked']['final'] == 32
assert not output_face_set(second_result, second_world, [faces[fi] for fi in walls[1]]), 'protected walls survive two runs'
assert len(faces_from_mesh(second_result.data)) == 32
print('PASS blender_cad_protected')
