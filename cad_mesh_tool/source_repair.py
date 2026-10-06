"""Exact collinear edge sewing; never weld or move source coordinates."""
import numpy as np
from .geometry import adjacency, face_normals, topology


def repair_collinear_faces(snapshot):
    """Remove zero-area triangular strips by subdividing neighboring edges.

    Only closed oriented triangle meshes with collinear zero-area patches are
    supported. Existing vertices sew overlapping edge intervals. Neighboring
    triangles are partitioned into fans on the same measured surface. Every
    resulting triangle and the complete topology are checked before return;
    the worker still validates its final output against the ORIGINAL input.
    """
    v = np.asarray(snapshot['vertices'], dtype=float)
    triangles = np.asarray(snapshot['triangles'])
    area2 = np.linalg.norm(np.cross(v[triangles[:,1]] - v[triangles[:,0]],
                                    v[triangles[:,2]] - v[triangles[:,0]]), axis=1)
    if np.all(area2 > 2e-16):
        return snapshot, {'removed_zero_area_faces': []}
    faces = snapshot['faces']
    if any(len(face) != 3 for face in faces) or not np.array_equal(triangles, np.asarray(faces)):
        raise ValueError('Source degenerate triangles require manual triangulation repair')
    bad = set(np.flatnonzero(area2 == 0).tolist())
    if not bad or np.any((area2 > 0) & (area2 <= 2e-16)):
        raise ValueError('Source degenerate triangles are not exact collinear faces; repair the source')
    before = topology(faces)
    if any(before[key] for key in ('boundary','nonmanifold','winding','duplicates')):
        raise ValueError('Source degenerate triangles require a closed independent solid for safe repair')
    incidence, adjacent = adjacency(faces)
    pending, groups = set(bad), []
    while pending:
        seed = min(pending)
        pending.remove(seed)
        stack, group = [seed], [seed]
        while stack:
            fresh = adjacent[stack.pop()] & pending
            pending.difference_update(fresh)
            stack.extend(sorted(fresh))
            group.extend(fresh)
        groups.append(sorted(group))
    cuts = {}
    for group in groups:
        ids = sorted({vi for fi in group for vi in faces[fi]})
        # An extremal pair along the largest coordinate span defines the line.
        axis_index = int(np.argmax(np.ptp(v[ids], axis=0)))
        a = min(ids, key=lambda vi: v[vi,axis_index])
        b = max(ids, key=lambda vi: v[vi,axis_index])
        axis = v[b] - v[a]
        length = np.linalg.norm(axis)
        if length <= 1e-12:
            raise ValueError('Source degenerate triangles contain coincident vertices; repair the source')
        axis /= length
        if np.max(np.linalg.norm(np.cross(v[ids] - v[a], axis), axis=1)) > 1e-14:
            raise ValueError('Source degenerate triangles do not form one exact collinear strip')
        selected = set(group)
        for edge, neighbors in incidence.items():
            if len(set(neighbors) & selected) != 1:
                continue
            x, y = edge
            delta = v[y] - v[x]
            denominator = delta @ delta
            if denominator <= 1e-24:
                raise ValueError('Source degenerate triangles contain a collapsed edge')
            samples = [(float((v[vi] - v[x]) @ delta / denominator), vi)
                       for vi in ids if vi not in edge]
            middle = [vi for t,vi in sorted(samples) if 0 < t < 1]
            if not middle:
                continue
            fi = next(i for i in neighbors if i not in bad)
            if fi in cuts or list(edge) in snapshot.get('sharp_edges', []):
                raise ValueError('Source degenerate triangles touch a conflicting or sharp boundary')
            cuts[fi] = (edge, middle)
    if not cuts:
        raise ValueError('Source degenerate triangles have no nondegenerate surface that can be sewn')
    affected = bad | set(cuts)
    roles = snapshot.get('cad_roles')
    if roles is not None and any(roles[fi] not in ('UNCLASSIFIED','BACKGROUND_PLANE') for fi in affected):
        raise ValueError('Source degenerate triangles touch a protected CAD region')
    locked = set(snapshot.get('user_protected_faces') or ())
    if locked & affected:
        raise ValueError('Source degenerate triangles touch a user-protected region; repair the source')
    result, materials, source_ids, new_roles, new_locked = [], [], [], [], []
    original_ids = snapshot.get('source_face_ids', list(range(len(faces))))
    for fi, face in enumerate(faces):
        if fi in bad:
            continue
        if fi not in cuts:
            pieces = [face]
        else:
            edge, middle = cuts[fi]
            x, y = edge
            if not any(a == x and b == y for a,b in zip(face, face[1:] + face[:1])):
                x, y = y, x
                middle = middle[::-1]
            third = next(vi for vi in face if vi not in edge)
            chain = [x] + middle + [y]
            pieces = [[a,b,third] for a,b in zip(chain, chain[1:])]
        if fi in locked:
            new_locked.append(len(result))
        result.extend(pieces)
        materials.extend([snapshot['materials'][fi]] * len(pieces))
        source_ids.extend([original_ids[fi]] * len(pieces))
        if roles is not None:
            new_roles.extend([roles[fi]] * len(pieces))
    after = topology(result)
    old_euler = len(v) - before['edges'] + len(faces)
    new_euler = len(v) - after['edges'] + len(result)
    t = np.asarray(result)
    area2 = np.linalg.norm(np.cross(v[t[:,1]] - v[t[:,0]], v[t[:,2]] - v[t[:,0]]), axis=1)
    if (old_euler != new_euler or not np.all(area2 > 2e-16)
            or any(after[key] for key in ('boundary','nonmanifold','winding','duplicates'))):
        raise ValueError('Source degenerate triangles cannot be sewn without changing valid topology')
    repaired = dict(snapshot, faces=result, triangles=result,
                    triangle_polygons=list(range(len(result))), materials=materials,
                    source_face_ids=source_ids,
                    normals=[normal.tolist() for normal in face_normals(v, result) for _ in range(3)])
    if roles is not None:
        repaired['cad_roles'] = new_roles
    if locked:
        repaired['user_protected_faces'] = new_locked
    report = dict(removed_zero_area_faces=[original_ids[fi] for fi in sorted(bad)],
                  subdivided_source_faces=[original_ids[fi] for fi in sorted(cuts)],
                  vertices_moved=0, euler_unchanged=True)
    return repaired, report

