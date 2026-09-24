"""Protect existing non-manifold edge junctions without accepting new defects."""

from collections import Counter, defaultdict
import struct


def edge_faces(faces):
    result = defaultdict(list)
    for face_id, face in enumerate(faces):
        for a, b in zip(face, face[1:] + face[:1]):
            result[tuple(sorted((a, b)))].append(face_id)
    return result


def cyclic_face(face):
    face = tuple(face)
    return min(face[i:] + face[:i] for i in range(len(face)))


def protection(snapshot, features):
    """Close the locked patch over features sharing any of its source vertices."""
    faces = snapshot['faces']
    from .geometry import topology
    counts = topology(faces)
    if any(counts[key] for key in ('boundary', 'winding', 'duplicates')):
        raise ValueError('Non-manifold recovery requires a closed, consistently wound source')
    incidence = edge_faces(faces)
    defects = {edge: adjacent for edge, adjacent in incidence.items() if len(adjacent) > 2}
    if not defects:
        return None
    defect_vertices = {vi for edge in defects for vi in edge}
    locked_faces = {fi for fi, face in enumerate(faces) if defect_vertices.intersection(face)}
    locked_features = set()
    while True:
        locked_vertices = {vi for fi in locked_faces for vi in faces[fi]}
        newly_locked = [feature for feature in features
                        if feature['id'] not in locked_features
                        and locked_vertices.intersection(feature['vertices'])]
        if not newly_locked:
            break
        for feature in newly_locked:
            locked_features.add(feature['id'])
            locked_faces.update(feature['faces'])
    locked_vertices = {vi for fi in locked_faces for vi in faces[fi]}
    return dict(edges=[list(edge) for edge in sorted(defects)],
                faces=sorted(locked_faces), vertices=sorted(locked_vertices),
                features=sorted(locked_features))


def preservation_errors(snapshot, output_faces, output_vertices, source_to_output, policy,
                        origin=None):
    """Compare exact protected faces and original bad-edge incidence by source IDs."""
    if policy is None:
        return []
    errors = []
    source_faces = snapshot['faces']
    source_vertices = snapshot['vertices']
    mapped = {}
    for source_id in policy['vertices']:
        target_id = source_to_output[source_id]
        if target_id < 0 or target_id >= len(output_vertices):
            errors.append(f'Protected vertex {source_id} was removed')
            continue
        mapped[source_id] = target_id
        if origin is None:
            same_position = all(abs(a - b) <= 1e-9 for a, b in zip(
                source_vertices[source_id], output_vertices[target_id]))
        else:
            # Mesh.from_pydata stores float32 local coordinates. Compare those
            # exact representable values, not unrepresentable world doubles.
            same_position = all(struct.pack('<f', a - center) == struct.pack('<f', b - center)
                for a, b, center in zip(source_vertices[source_id],
                                        output_vertices[target_id], origin))
        if not same_position:
            errors.append(f'Protected vertex {source_id} moved')
    output_counts = Counter(cyclic_face(face) for face in output_faces)
    for source_face_id in policy['faces']:
        face = source_faces[source_face_id]
        if not all(vi in mapped for vi in face):
            continue
        key = cyclic_face([mapped[vi] for vi in face])
        if not output_counts[key]:
            errors.append(f'Protected source face {source_face_id} changed')
        else:
            output_counts[key] -= 1
    original_incidence = edge_faces(source_faces)
    result_incidence = edge_faces(output_faces)
    original_defects = {edge: adjacent for edge, adjacent in original_incidence.items()
                        if len(adjacent) > 2}
    expected_edges = set()
    for edge, adjacent in original_defects.items():
        if not all(vi in mapped for vi in edge):
            continue
        target = tuple(sorted(mapped[vi] for vi in edge))
        expected_edges.add(target)
        if len(result_incidence.get(target, ())) != len(adjacent):
            errors.append(f'Non-manifold source edge {edge} changed incidence')
    actual_edges = {edge for edge, adjacent in result_incidence.items() if len(adjacent) > 2}
    if actual_edges != expected_edges:
        errors.append('New or missing non-manifold edges: '
                      f'new={sorted(actual_edges - expected_edges)[:8]}, '
                      f'missing={sorted(expected_edges - actual_edges)[:8]}')
    return errors
