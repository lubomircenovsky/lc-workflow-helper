"""Remove vertices that only split a straight crease into collinear pieces.

CAD tessellation often pins plane vertices onto a bend rim. Reconstruction
keeps them so the bend stays joined to its plane, which leaves extra
segmentation along the bend. Vertices are processed one at a time in index
order; a vertex is removed only when, in the current mesh,

* it is not blocked (perimeter rings, user- or non-manifold-protected faces),
* exactly two of its edges are creases (geometric folds or UV seams) and they
  are collinear, every other edge is flat, so its faces form two coplanar
  fans (a sharp flag on a flat edge is a display hint and does not block),
* each fan has one role and one material and no protected face,
* each merged fan is a simple polygon whose triangulation (Blender's, or a
  constrained Delaunay fallback) has no zero-area or reversed triangle and
  the same area.

The removed vertex lies on the remaining straight edge, so the surface does
not move. Every other vertex keeps its exact position; ``vertex_map`` maps
input to output indices (-1 when removed).
"""
import math
from collections import Counter, defaultdict

import bpy
import numpy as np

from .errors import StageRejected
from .geometry import basis, face_normals, topology

FLAT_ANGLE_DEG = 0.1
PLANE_TOLERANCE_M = 1e-6
# Output meshes store float32 local coordinates (about 5e-7 m resolution at
# a few metres); a vertex within 2 µm of the line is treated as on it.
LINE_TOLERANCE_M = 2e-6
ALLOWED_ATTRIBUTES = {
    'position', 'cad_role', 'material_index', 'sharp_edge', 'sharp_face', 'uv_seam', 'custom_normal',
    '.edge_verts', '.corner_vert', '.corner_edge', '.select_vert', '.select_edge', '.select_poly',
    '.hide_vert', '.hide_edge', '.hide_poly',
}


def _loop(faces, group):
    """Boundary cycle of a face group, or None when it is not one simple loop."""
    directed = set()
    for fi in group:
        face = faces[fi]
        for a, b in zip(face, face[1:] + face[:1]):
            if (b, a) in directed:
                directed.discard((b, a))
            else:
                directed.add((a, b))
    following = {}
    for a, b in directed:
        if a in following:
            return None
        following[a] = b
    if not following:
        return None
    start = next(iter(following))
    loop = [start]
    while following[loop[-1]] != start:
        if len(loop) > len(following):
            return None
        loop.append(following[loop[-1]])
    return loop if len(loop) == len(following) else None


def _area(points, normal):
    return abs(np.cross(points[1:-1] - points[0], points[2:] - points[0]).sum(0) @ normal) / 2


def _clean(points, triangles, normal, area):
    if not len(triangles):
        return False
    xyz = points[np.asarray(triangles, dtype=int)]
    cross = np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0])
    if np.any(cross @ normal <= 2e-16):
        return False
    return abs(np.linalg.norm(cross, axis=1).sum() / 2 - area) <= max(1e-12, area * 1e-6)


def _polygons(points, normal):
    """One n-gon when Blender triangulates it cleanly, else CDT triangles, else None."""
    area = _area(points, normal)
    probe = bpy.data.meshes.new('_CAD_CollinearProbe')
    try:
        probe.from_pydata(points.tolist(), [], [list(range(len(points)))])
        probe.update()
        probe.calc_loop_triangles()
        triangles = [t.vertices[:] for t in probe.loop_triangles]
    finally:
        bpy.data.meshes.remove(probe)
    if _clean(points, triangles, normal, area):
        return [list(range(len(points)))]
    from .rebuild import orient, tessellation

    frame = basis(normal)
    flat = ((points - points[0]) @ frame.T)[:, :2]
    try:
        _, triangles = tessellation([flat])
    except Exception:
        return None
    if any(i >= len(points) for t in triangles for i in t):
        return None
    triangles = [list(t) if orient(*flat[list(t)]) > 0 else list(t)[::-1] for t in triangles]
    return triangles if _clean(points, triangles, normal, area) else None


def remove_collinear_vertices(mesh, blocked_vertices=(), frozen_vertices=()):
    """Return ``(new_mesh, report)``; ``new_mesh`` is a copy when nothing changes.

    ``blocked_vertices`` are never removed. A face whose vertices all belong to
    ``frozen_vertices`` (user-protected or non-manifold-protected faces) is
    never merged or changed."""
    report = dict(removed_vertices=0, merged_faces=0, candidates=0, triangulated_fallbacks=0,
                  merged_sides=0, collapsed_sides=0,
                  rejected=defaultdict(int), vertex_map=list(range(len(mesh.vertices))))
    extra = [a.name for a in mesh.attributes if a.name not in ALLOWED_ATTRIBUTES]
    if extra or mesh.uv_layers or mesh.shape_keys:
        report['skipped'] = 'Mesh carries extra data: ' + ', '.join(extra or ['uv/shape keys'])
        report['rejected'] = {}
        return mesh.copy(), report
    attr = mesh.attributes.get('cad_role')
    if attr is None:
        raise StageRejected('Collinear cleanup requires cad_role')
    vertices = np.array([v.co[:] for v in mesh.vertices], dtype=float)
    source_faces = [list(p.vertices) for p in mesh.polygons]
    initial_normals = face_normals(vertices, source_faces)
    # Mutable face store: id -> data. Merged faces get new ids.
    faces = {fi: list(f) for fi, f in enumerate(source_faces)}
    roles = {fi: x.value for fi, x in enumerate(attr.data)}
    materials = {p.index: p.material_index for p in mesh.polygons}
    normals = {fi: initial_normals[fi] for fi in faces}
    corner = {p.index: {v: list(mesh.corner_normals[li].vector) for v, li in zip(p.vertices, p.loop_indices)}
              for p in mesh.polygons}
    flags = {tuple(sorted(e.vertices)): (e.use_seam, e.use_edge_sharp) for e in mesh.edges}
    vertex_faces = defaultdict(set)
    for fi, face in faces.items():
        for v in face:
            vertex_faces[v].add(fi)
    frozen_set = set(frozen_vertices)
    frozen = {fi for fi, face in faces.items() if frozen_set and frozen_set.issuperset(face)}
    blocked = set(blocked_vertices) | frozen_set
    cos = math.cos(math.radians(FLAT_ANGLE_DEG))
    next_id = len(source_faces)

    def coplanar(group):
        n = normals[group[0]]
        origin = vertices[faces[group[0]][0]]
        return all(normals[f] @ n >= cos and
                   np.max(np.abs((vertices[faces[f]] - origin) @ n)) <= PLANE_TOLERANCE_M for f in group)

    def incident(v):
        """Edges at v -> faces using them (in the current face store)."""
        edges = defaultdict(list)
        for f in vertex_faces[v]:
            face = faces[f]
            i = face.index(v)
            for u in (face[i - 1], face[(i + 1) % len(face)]):
                edges[u].append(f)
        return edges

    why = defaultdict(list)

    def merge_plan(v, side):
        """Merge the fan into one polygon without v (or its CDT triangles)."""
        if not coplanar(side):
            why[v].append('merge:not_coplanar')
            return None
        loop = _loop(faces, side)
        if loop is None:
            why[v].append('merge:not_simple_loop')
            return None
        kept = [u for u in loop if u != v]
        if len(kept) < 3:
            why[v].append('merge:too_few')
            return None
        polygons = _polygons(vertices[kept], normals[side[0]])
        if polygons is None:
            why[v].append('merge:triangulation')
            return None
        return side, [([kept[i] for i in polygon], {}) for polygon in polygons], 'merged_sides'

    def collapse_plan(v, side, creases):
        """Move v's corners onto a crease neighbour; that neighbour is on the
        same line and in the same plane, so no face leaves its plane. Every
        changed face must stay a valid, same-facing polygon, the fan's area
        must be unchanged (no fold) and no edge may gain a third face."""
        if not coplanar(side):
            return None
        normal = normals[side[0]]
        area = sum(_area(vertices[faces[f]], normal) for f in side)
        for target in creases:
            new_faces = []
            for f in side:
                ids = faces[f]
                if target in ids:
                    i, j = ids.index(v), ids.index(target)
                    if (i - j) % len(ids) not in (1, len(ids) - 1):
                        why[v].append('collapse:not_adjacent')
                        break
                    ids = [u for u in ids if u != v]
                else:
                    ids = [target if u == v else u for u in ids]
                if len(ids) < 3:
                    continue
                polygons = _polygons(vertices[ids], normal)
                if polygons is None:
                    why[v].append('collapse:triangulation')
                    break
                corners = {target: corner[f].get(target, corner[f][v])}
                new_faces.extend(([ids[k] for k in polygon], corners) for polygon in polygons)
            else:
                after = sum(_area(vertices[ids], normal) for ids, _ in new_faces)
                if abs(after - area) > max(1e-12, area * 1e-6):
                    why[v].append('collapse:fold')
                    continue
                counts = defaultdict(int)
                for f in vertex_faces[target] - set(side):
                    face = faces[f]
                    for a, b in zip(face, face[1:] + face[:1]):
                        if target in (a, b):
                            counts[tuple(sorted((a, b)))] += 1
                for ids, _ in new_faces:
                    for a, b in zip(ids, ids[1:] + ids[:1]):
                        if target in (a, b):
                            counts[tuple(sorted((a, b)))] += 1
                if any(count > 2 for count in counts.values()):
                    why[v].append('collapse:nonmanifold')
                    continue
                return side, new_faces, 'collapsed_sides'
        return None

    removed = set()
    candidates = set()
    rejected = set()
    # A removal can make a neighbour removable, so repeat until stable.
    for _ in range(4):
        count = len(removed)
        rejected.clear()
        for v in sorted(vertex_faces):
            if v in blocked:
                continue
            edges = incident(v)
            if any(len(fs) != 2 for fs in edges.values()):
                continue
            # Seams are authored UV cuts and stay. Sharp flags are display
            # hints (users re-apply them by angle); a flat sharp edge does not
            # block, and a merged crease keeps the flag.
            creases = [u for u, fs in edges.items()
                       if flags.get(tuple(sorted((v, u))), (False, False))[0] or not coplanar(fs)]
            if len(creases) != 2:
                continue
            a, b, p = vertices[creases[0]], vertices[creases[1]], vertices[v]
            direction = b - a
            length = np.linalg.norm(direction)
            if length == 0 or (p - a) @ direction <= 0 or (b - p) @ direction <= 0:
                continue
            if np.linalg.norm(np.cross(p - a, direction)) / length > LINE_TOLERANCE_M:
                continue
            candidates.add(v)
            parent = {f: f for f in vertex_faces[v]}

            def find(f):
                while parent[f] != f:
                    parent[f] = parent[parent[f]]
                    f = parent[f]
                return f

            for u, (f, g) in edges.items():
                if u not in creases:
                    parent[find(f)] = find(g)
            sides = defaultdict(list)
            for f in vertex_faces[v]:
                sides[find(f)].append(f)
            sides = [sorted(s) for s in sides.values()]
            if len(sides) != 2:
                why[v] = [f'fan:{len(sides)}_sides']
            elif any(frozen.intersection(s) for s in sides):
                why[v] = ['fan:protected_face']
            elif any(len({roles[f] for f in s}) != 1 or len({materials[f] for f in s}) != 1 for s in sides):
                why[v] = ['fan:mixed_role_or_material']
            else:
                why[v] = []
            if why[v]:
                rejected.add(('fan', v))
                continue
            plans = []
            for side in sides:
                plan = merge_plan(v, side) or collapse_plan(v, side, creases)
                if plan is None:
                    break
                plans.append(plan)
            if len(plans) != 2:
                rejected.add(('merge', v))
                continue
            for side, new_faces, kind in plans:
                report[kind] += 1
                report['triangulated_fallbacks'] += kind == 'merged_sides' and len(new_faces) > 1
                role, material = roles[side[0]], materials[side[0]]
                normal = normals[side[0]]
                corners = {}
                for f in side:
                    corners.update({u: n for u, n in corner[f].items() if u not in corners})
                for f in side:
                    for u in faces[f]:
                        vertex_faces[u].discard(f)
                    del faces[f], roles[f], materials[f], normals[f], corner[f]
                for ids, face_corners in new_faces:
                    faces[next_id] = ids
                    roles[next_id], materials[next_id], normals[next_id] = role, material, normal
                    corner[next_id] = {u: face_corners.get(u, corners.get(u)) for u in ids}
                    for u in ids:
                        vertex_faces[u].add(next_id)
                    next_id += 1
                report['merged_faces'] += len(side)
            # The two collinear crease pieces become one edge with their flags.
            first, second = (tuple(sorted((v, u))) for u in creases)
            merged = tuple(sorted(creases))
            flag_a, flag_b = flags.pop(first, (False, False)), flags.pop(second, (False, False))
            flags[merged] = (flag_a[0] or flag_b[0], flag_a[1] or flag_b[1])
            for u in edges:
                flags.pop(tuple(sorted((v, u))), None)
            del vertex_faces[v]
            removed.add(v)

        if len(removed) == count:
            break
    report['candidates'] = len(candidates)
    report['rejected_examples'] = [dict(vertex=v, position=vertices[v].tolist(), reasons=sorted(set(why[v])))
                                   for _, v in sorted(rejected, key=lambda item: item[1])[:25]]
    report['rejected'] = dict(Counter(kind for kind, _ in rejected))
    if not removed:
        return mesh.copy(), report
    order = sorted(faces)
    out_faces = [faces[f] for f in order]
    out_roles = [roles[f] for f in order]
    out_materials = [materials[f] for f in order]
    out_normals = [corner[f][u] for f in order for u in faces[f]]
    before, after = topology(source_faces), topology(out_faces)
    if any(before[k] != after[k] for k in ('boundary', 'nonmanifold', 'winding', 'duplicates')):
        raise StageRejected('Collinear cleanup changed topology')
    retained = [i for i in range(len(vertices)) if i not in removed]
    remap = {old: new for new, old in enumerate(retained)}
    result = bpy.data.meshes.new(mesh.name + '_Collinear')
    result.from_pydata(vertices[retained].tolist(), [], [[remap[u] for u in f] for f in out_faces])
    result.update()
    if result.validate(verbose=False):
        bpy.data.meshes.remove(result)
        raise StageRejected('Blender had to repair the collinear cleanup mesh')
    for material in mesh.materials:
        result.materials.append(material)
    result.attributes.new('cad_role', 'INT', 'FACE').data.foreach_set('value', out_roles)
    for polygon, material in zip(result.polygons, out_materials):
        polygon.material_index = material
        polygon.use_smooth = True
    for edge in result.edges:
        key = tuple(sorted(retained[i] for i in edge.vertices))
        if key in flags:
            edge.use_seam, edge.use_edge_sharp = flags[key]
    result.normals_split_custom_set(out_normals)
    if any(result.vertices[new].co != mesh.vertices[old].co for old, new in remap.items()):
        bpy.data.meshes.remove(result)
        raise StageRejected('Collinear cleanup moved a retained vertex')
    report.update(removed_vertices=len(removed), vertex_map=[remap.get(i, -1) for i in range(len(vertices))])
    return result, report
