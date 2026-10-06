"""Deterministic edge-connected shell partition; never weld or union geometry."""
from collections import defaultdict


def components(faces):
    edge_faces = defaultdict(list)
    for fi, face in enumerate(faces):
        for a, b in zip(face, face[1:] + face[:1]):
            edge_faces[tuple(sorted((a, b)))].append(fi)
    pending = set(range(len(faces)))
    result = []
    while pending:
        seed = min(pending)
        pending.remove(seed)
        stack, group = [seed], []
        while stack:
            fi = stack.pop()
            group.append(fi)
            face = faces[fi]
            for a, b in zip(face, face[1:] + face[:1]):
                fresh = set(edge_faces[tuple(sorted((a, b)))]) & pending
                pending.difference_update(fresh)
                stack.extend(sorted(fresh, reverse=True))
        result.append(sorted(group))
    return result


def manifold_groups(faces):
    """Connected face groups without traversing many-face junction edges."""
    from .nonmanifold import edge_faces
    neighbors = defaultdict(set)
    for adjacent in edge_faces(faces).values():
        if len(adjacent) == 2:
            a, b = adjacent
            neighbors[a].add(b)
            neighbors[b].add(a)
    pending = set(range(len(faces)))
    result = []
    while pending:
        seed = min(pending)
        pending.remove(seed)
        stack, group = [seed], []
        while stack:
            fi = stack.pop()
            group.append(fi)
            fresh = neighbors[fi] & pending
            pending.difference_update(fresh)
            stack.extend(sorted(fresh, reverse=True))
        result.append(sorted(group))
    return result


def independent_components(faces):
    """Peel closed shells meeting at junctions; keep ambiguous open patches joined.

    Only existing faces are partitioned. A cut through a many-face edge is
    accepted for a shell only when that shell is independently closed and
    consistently wound. Remaining patches retain their original connections.
    Source intersections are still checked by every reconstruction worker.
    """
    from .geometry import topology
    from .nonmanifold import edge_faces

    incidence = edge_faces(faces)
    if not any(len(adjacent) > 2 for adjacent in incidence.values()):
        return components(faces)
    closed = []
    for group in manifold_groups(faces):
        counts = topology([faces[fi] for fi in group])
        if not any(counts[key] for key in ('boundary', 'nonmanifold', 'winding', 'duplicates')):
            closed.append(sorted(group))
    remainder = sorted(set(range(len(faces))) - {fi for group in closed for fi in group})
    retained = [[remainder[i] for i in group]
                for group in components([faces[fi] for fi in remainder])]
    return sorted(closed + retained, key=lambda group: group[0])


def solid_partitions(faces, vertices):
    """Partition measured shells, including an unambiguous shared planar cap.

    A cap may be reused in two outputs only when its boundary exactly matches
    two larger open shells, and adding it with opposite orientations makes
    both shells closed oriented manifolds. Conflicting proposals are rejected.
    This separates bodies; it does not certify their intersections or a union.
    """
    import numpy as np
    from .geometry import topology, face_normals
    from .nonmanifold import edge_faces

    groups = manifold_groups(faces)
    boundaries = []
    for group in groups:
        incidence = edge_faces([faces[fi] for fi in group])
        boundaries.append({edge for edge, adjacent in incidence.items() if len(adjacent) == 1})
    proposals = []
    v = np.asarray(vertices, dtype=float)
    for ci, cap in enumerate(groups):
        if not boundaries[ci]:
            continue
        bodies = [bi for bi, body in enumerate(groups)
                  if len(body) > len(cap) and boundaries[bi] == boundaries[ci]]
        if len(bodies) != 2:
            continue
        cap_faces = [faces[fi] for fi in cap]
        normal = face_normals(v, cap_faces)[0]
        ids = sorted({vi for face in cap_faces for vi in face})
        if (np.linalg.norm(normal) < .99
                or np.max(abs((v[ids] - v[ids[0]]) @ normal)) > 1e-6):
            continue
        choices = []
        for bi in bodies:
            orientations = []
            for flip in (False, True):
                counts = topology([faces[fi] for fi in groups[bi]]
                                  + [face[::-1] if flip else face for face in cap_faces])
                if not any(counts[key] for key in ('boundary', 'nonmanifold', 'winding', 'duplicates')):
                    orientations.append(flip)
            if len(orientations) != 1:
                break
            choices.append(orientations[0])
        if len(choices) == 2 and choices[0] != choices[1]:
            proposals.append((ci, bodies, choices))
    involvement = defaultdict(int)
    for ci, bodies, _ in proposals:
        for gi in [ci] + bodies:
            involvement[gi] += 1
    consumed, result = set(), []
    for ci, bodies, choices in proposals:
        if any(involvement[gi] != 1 for gi in [ci] + bodies):
            continue
        for bi, flip in zip(bodies, choices):
            result.append(dict(faces=sorted(groups[bi] + groups[ci]),
                               reversed_faces=groups[ci] if flip else [],
                               shared_interface_faces=groups[ci]))
        consumed.update([ci] + bodies)
    remaining = sorted({fi for gi, group in enumerate(groups) if gi not in consumed for fi in group})
    for group in independent_components([faces[fi] for fi in remaining]):
        result.append(dict(faces=[remaining[i] for i in group], reversed_faces=[],
                           shared_interface_faces=[]))
    return sorted(result, key=lambda item: item['faces'][0])


def extract_component(snapshot, face_ids, reversed_faces=()):
    face_ids = sorted(face_ids)
    selected = set(face_ids)
    reversed_faces = set(reversed_faces)
    if not reversed_faces <= selected:
        raise ValueError('Reversed interface faces must belong to the selected solid')
    ids = sorted({vi for fi in face_ids for vi in snapshot['faces'][fi]})
    mapping = {vi: index for index, vi in enumerate(ids)}
    triangle_faces = {tuple(sorted(face)): fi for fi, face in enumerate(snapshot['faces']) if len(face)==3}
    # Capture carries polygon indices to avoid guessing triangulation ownership.
    polygon_ids = snapshot.get('triangle_polygons')
    if polygon_ids is None:
        polygon_ids = [triangle_faces.get(tuple(sorted(tri))) for tri in snapshot['triangles']]
        if any(fi is None for fi in polygon_ids):
            raise ValueError('Missing triangle polygon map for solid extraction')
    normals, offset = [], 0
    for fi, face in enumerate(snapshot['faces']):
        if fi in selected:
            normals.extend(snapshot['normals'][offset:offset+len(face)])
        offset += len(face)
    result = dict(snapshot, vertices=[snapshot['vertices'][vi] for vi in ids],
                  faces=[[mapping[vi] for vi in (snapshot['faces'][fi][::-1] if fi in reversed_faces else snapshot['faces'][fi])] for fi in face_ids],
                  materials=[snapshot['materials'][fi] for fi in face_ids], normals=normals,
                  triangles=[[mapping[vi] for vi in (tri[::-1] if fi in reversed_faces else tri)] for tri,fi in zip(snapshot['triangles'],polygon_ids) if fi in selected],
                  sharp_edges=[[mapping[a],mapping[b]] for a,b in snapshot.get('sharp_edges',[]) if a in mapping and b in mapping],
                  source_vertex_ids=ids, source_face_ids=face_ids)
    result.pop('triangle_polygons',None)
    if reversed_faces:
        import numpy as np
        from .geometry import face_normals
        result['normals'] = [normal.tolist() for normal,face in
                             zip(face_normals(np.asarray(result['vertices']),result['faces']),result['faces'])
                             for _ in face]
        result['reversed_source_faces'] = sorted(reversed_faces)
    if snapshot.get('cad_roles') is not None:
        result['cad_roles']=[snapshot['cad_roles'][fi] for fi in face_ids]
    if snapshot.get('user_protected_faces'):
        locked = set(snapshot['user_protected_faces'])
        result['user_protected_faces'] = [index for index, fi in enumerate(face_ids) if fi in locked]
    return result
