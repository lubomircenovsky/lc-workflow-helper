"""Conservative, boundary-preserving coalescing of straight cutout walls (metres).

Only PROTECTED_OTHER patches bounded by two perimeter rails and rebuilt corner
faces qualify. DETAIL_REBUILT is never a dissolve candidate, including circles.
"""
import math
from collections import Counter
import numpy as np
import bpy
from mathutils import Vector
from .geometry import adjacency, face_normals, loops, topology

DEFAULTS = dict(enabled=True, angle_deg=0.1, planarity_m=1e-6, normal_limit_deg=None)


def normal_chord_limit(angle_deg):
    return 2 * math.sin(math.radians(min(angle_deg, 180.0)) / 2)


def settings(options=None):
    result = dict(DEFAULTS)
    if options is not None:
        if set(options) - set(result):
            raise ValueError('Unknown straight wall parameter')
        result.update(options)
    if type(result['enabled']) is not bool:
        raise ValueError('straight wall enabled must be bool')
    for name, maximum in [('angle_deg', 0.1), ('planarity_m', 1e-6)]:
        value = result[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= maximum:
            raise ValueError(f'{name} must be positive and <= {maximum}')
    limit = result['normal_limit_deg']
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, (int, float))
                              or not math.isfinite(limit) or limit <= 0):
        raise ValueError('normal_limit_deg must be a positive finite angle')
    return result


def cleanup_straight_walls(mesh, options=None):
    """Return a new mesh and audit report; input and every boundary vertex survive."""
    config = settings(options)
    report = dict(parameters=config, merged_patches=[], rejected=Counter(), removed_faces=0,
                  protected_faces_lost=0, moved_vertices=0, removed_interior_vertices=0,
                  vertex_map=list(range(len(mesh.vertices))))
    if not config['enabled']:
        return mesh.copy(), report
    attr = mesh.attributes.get('cad_role')
    if attr is None:
        raise ValueError('Straight wall cleanup requires cad_role')
    vertices = np.array([v.co[:] for v in mesh.vertices])
    faces = [list(p.vertices) for p in mesh.polygons]
    roles = [x.value for x in attr.data]
    normals = face_normals(vertices, faces)
    edge_faces, adjacent = adjacency(faces)
    edge_flags = {tuple(sorted(e.vertices)): (e.use_seam, e.use_edge_sharp) for e in mesh.edges if e.use_seam or e.use_edge_sharp}
    blocked = set(edge_flags)
    cos = math.cos(math.radians(config['angle_deg']))
    sin = math.sin(math.radians(config['angle_deg']))
    tol = config['planarity_m']
    corner = [{v: list(mesh.corner_normals[li].vector) for v, li in zip(p.vertices, p.loop_indices)} for p in mesh.polygons]
    vertex_faces = [set() for _ in vertices]
    for fi, face in enumerate(faces):
        for v in face:
            vertex_faces[v].add(fi)
    visited, replacements, removed, removed_vertices = set(), {}, set(), set()
    for seed in range(len(faces)):
        if roles[seed] != 4 or seed in visited:
            continue
        region, stack = {seed}, [seed]
        visited.add(seed)
        origin, normal = vertices[faces[seed][0]], normals[seed]
        while stack:
            current = stack.pop()
            for other in sorted(adjacent[current] - visited):
                if roles[other] != 4 or mesh.polygons[other].material_index != mesh.polygons[seed].material_index:
                    continue
                if normals[other] @ normal < cos or np.max(abs((vertices[faces[other]] - origin) @ normal)) > tol:
                    continue
                visited.add(other); region.add(other); stack.append(other)
        if len(region) < 2:
            continue
        internal = [e for e, fs in edge_faces.items() if len(fs) == 2 and all(f in region for f in fs)]
        if any(e in blocked for e in internal):
            report['rejected']['edge_delimiter'] += 1; continue
        region_normals = {}
        discontinuity = False
        for fi in sorted(region):
            for v, n in corner[fi].items():
                if v in region_normals and np.dot(n, region_normals[v]) < cos:
                    discontinuity = True
                region_normals[v] = n
        if discontinuity:
            report['rejected']['normal_discontinuity'] += 1; continue
        try:
            boundary = loops([faces[i] for i in sorted(region)])
        except ValueError:
            report['rejected']['non_simple_boundary'] += 1; continue
        if len(boundary) != 1:
            report['rejected']['multiple_boundaries'] += 1; continue
        interior = set(region_normals) - set(boundary[0])
        if any(not vertex_faces[v] <= region for v in interior):
            report['rejected']['shared_interior_vertex'] += 1; continue
        ring = boundary[0]
        if face_normals(vertices, [ring])[0] @ normal < 0:
            ring.reverse()
        edges = list(zip(ring, ring[1:] + ring[:1]))
        vectors = np.array([vertices[b] - vertices[a] for a, b in edges])
        lengths = np.linalg.norm(vectors, axis=1)
        if np.any(lengths <= 1e-12):
            report['rejected']['zero_edge'] += 1; continue
        directions = vectors / lengths[:, None]
        corners = [i for i in range(len(ring)) if directions[i-1] @ directions[i] < cos]
        if len(corners) != 4 or any(abs(directions[i-1] @ directions[i]) > sin for i in corners):
            report['rejected']['not_rectangle'] += 1; continue
        # A rectangle has exactly two opposing perimeter rails, with corner
        # surfaces closing the other two ends. Excludes caps and free planes.
        sides = []
        valid = True
        for k, start in enumerate(corners):
            stop = corners[(k+1) % 4]
            indices = list(range(start, stop if stop > start else stop + len(ring)))
            side_roles = set()
            for j in indices:
                e = tuple(sorted(edges[j % len(ring)]))
                outside = [f for f in edge_faces[e] if f not in region]
                if len(edge_faces[e]) != 2 or len(outside) != 1:
                    valid = False; break
                f = outside[0]; side_roles.add(2 if roles[f] == 5 else roles[f])
                if roles[f] in (2,5) and abs(normals[f] @ normal) > sin:
                    valid = False
            sides.append(side_roles)
        if not valid or not (sides == [{2}, {1}, {2}, {1}] or sides == [{1}, {2}, {1}, {2}]):
            report['rejected']['not_perimeter_bounded_wall'] += 1; continue
        # Probe Blender's actual tessellation. Never deliver zero-area/reversed
        # triangles just to obtain an n-gon. Such a patch stays unchanged.
        probe = bpy.data.meshes.new('_CAD_WallProbe')
        try:
            probe.from_pydata(vertices[ring].tolist(), [], [list(range(len(ring)))]); probe.update(); probe.calc_loop_triangles()
            triangles = np.array([t.vertices[:] for t in probe.loop_triangles], dtype=int)
            xyz = vertices[ring][triangles]
            cross = np.cross(xyz[:, 1]-xyz[:, 0], xyz[:, 2]-xyz[:, 0])
            if np.any(cross @ normal <= 2e-16):
                report['rejected']['invalid_ngon_triangulation'] += 1; continue
            old_area = sum(mesh.polygons[i].area for i in region)
            if abs(np.linalg.norm(cross, axis=1).sum()/2 - old_area) > max(1e-12, old_area*1e-5):
                report['rejected']['area_mismatch'] += 1; continue
        finally:
            bpy.data.meshes.remove(probe)
        replacements[seed] = (ring, region_normals)
        removed.update(region - {seed})
        removed_vertices.update(interior)
        report['merged_patches'].append(dict(source_faces=sorted(region), boundary_vertices=ring, faces_before=len(region), faces_after=1))
    out_faces, out_roles, out_materials, out_normals = [], [], [], []
    for fi, face in enumerate(faces):
        if fi in removed:
            continue
        ids, ns = replacements.get(fi, (face, corner[fi]))
        out_faces.append(ids); out_roles.append(roles[fi]); out_materials.append(mesh.polygons[fi].material_index)
        out_normals.extend(ns[v] for v in ids)
    before, after = topology(faces), topology(out_faces)
    if any(before[k] != after[k] for k in ('boundary', 'nonmanifold', 'winding', 'duplicates')):
        raise ValueError('Straight wall cleanup changed topology')
    retained = [i for i in range(len(vertices)) if i not in removed_vertices]
    remap = {old: new for new, old in enumerate(retained)}
    result = bpy.data.meshes.new(mesh.name+'_StraightWalls')
    result.from_pydata(vertices[retained].tolist(), [], [[remap[v] for v in f] for f in out_faces]); result.update()
    for material in mesh.materials:
        result.materials.append(material)
    result.attributes.new('cad_role', 'INT', 'FACE').data.foreach_set('value', out_roles)
    for p, material in zip(result.polygons, out_materials):
        p.material_index = material; p.use_smooth = True
    for e in result.edges:
        key = tuple(sorted(retained[v] for v in e.vertices))
        if key in blocked:
            e.use_seam, e.use_edge_sharp = edge_flags[key]
    result.normals_split_custom_set(out_normals)
    if any(result.vertices[new].co != mesh.vertices[old].co for old, new in remap.items()):
        bpy.data.meshes.remove(result)
        raise ValueError('Straight wall cleanup moved a retained vertex')
    result_faces = {tuple(p.vertices): p for p in result.polygons}
    untouched = set(range(len(faces))) - removed - set(replacements)
    for fi in untouched:
        ids = tuple(remap[v] for v in faces[fi])
        if ids not in result_faces or result_faces[ids].material_index != mesh.polygons[fi].material_index:
            bpy.data.meshes.remove(result)
            raise ValueError('Straight wall cleanup changed a protected face')
    # Calibrate Blender's quantized normal read/write error on the topology
    # actually being delivered. The input topology can have a different loop
    # encoding after wall faces are merged and is not a valid sole reference.
    input_reference = mesh.copy()
    try:
        original_normals = [n.vector.copy() for n in mesh.corner_normals]
        input_reference.normals_split_custom_set(original_normals)
        input_roundtrip_error = max(((n.vector - expected).length for n, expected in
                                     zip(input_reference.corner_normals, original_normals)), default=0.)
    finally:
        bpy.data.meshes.remove(input_reference)
    output_reference = bpy.data.meshes.new('_CAD_NormalTopologyReference')
    try:
        output_reference.from_pydata(vertices[retained].tolist(), [],
                                     [[remap[v] for v in f] for f in out_faces])
        output_reference.update()
        for p, material in zip(output_reference.polygons, out_materials):
            p.material_index = material
            p.use_smooth = True
        output_reference.normals_split_custom_set(out_normals)
        output_roundtrip_error = max(((n.vector - Vector(expected)).length for n, expected in
                                      zip(output_reference.corner_normals, out_normals)), default=0.)
    finally:
        bpy.data.meshes.remove(output_reference)
    normal_error = max(((n.vector - Vector(expected)).length
                        for n, expected in zip(result.corner_normals, out_normals)), default=0.)
    normal_limit = (normal_chord_limit(config['normal_limit_deg'])
                    if config['normal_limit_deg'] is not None
                    else min(2*math.sin(math.radians(config['angle_deg'])/2), output_roundtrip_error+1e-6))
    if normal_error > normal_limit:
        error = ValueError('Straight wall cleanup changed corner normals: '+str(normal_error))
        error.review_mesh = result
        error.review_stage = 'straight_walls_unvalidated'
        raise error
    report['corner_normal_max_error'] = normal_error
    report['corner_normal_input_roundtrip_error'] = input_roundtrip_error
    report['corner_normal_roundtrip_error'] = output_roundtrip_error
    report['corner_normal_calibration'] = 'output_topology_roundtrip'
    report['corner_normal_error_limit'] = normal_limit
    report['corner_normal_limit_override_deg'] = config['normal_limit_deg']
    report['removed_faces'] = len(removed)
    report['removed_interior_vertices'] = len(removed_vertices)
    report['vertex_map'] = [remap.get(i, -1) for i in range(len(vertices))]
    return result, report
