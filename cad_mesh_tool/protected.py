"""User-protected faces: authored regions that reconstruction keeps unchanged.

The source carries a BOOLEAN face attribute ``cad_protected``. Capture stores
its face indices as ``user_protected_faces``. Every feature sharing a vertex
with those faces is forced to SKIP, the faces themselves are locked during
reconstruction, and final validation compares them by explicit source vertex
IDs. After validation the result meshes carry the same attribute on exactly
those faces, so a result used as the next input keeps its protection.
"""
import struct
from collections import Counter

ATTRIBUTE = 'cad_protected'
SKIP_REASON = 'Touches a user-protected region'


def faces_from_mesh(mesh):
    """Face indices flagged in a Blender mesh (empty when no usable attribute)."""
    attr = mesh.attributes.get(ATTRIBUTE)
    if attr is None or attr.domain != 'FACE' or attr.data_type != 'BOOLEAN':
        return []
    values = [False] * len(attr.data)
    attr.data.foreach_get('value', values)
    return [index for index, value in enumerate(values) if value]


def locked_faces(snapshot):
    return sorted(set(snapshot.get('user_protected_faces') or ()))


def mark_features(snapshot, features):
    """Force-skip features touching protected faces; return their IDs."""
    faces = locked_faces(snapshot)
    if not faces:
        return []
    vertices = {vi for fi in faces for vi in snapshot['faces'][fi]}
    marked = []
    for feature in features:
        if vertices.intersection(feature['vertices']):
            marked.append(feature['id'])
            if not feature.get('forced_skip_reason'):
                feature['forced_skip_reason'] = SKIP_REASON
    return marked


def face_cycles(snapshot):
    """Vertex cycles of the locked faces; vertex IDs are stable across source repair."""
    return [list(snapshot['faces'][fi]) for fi in locked_faces(snapshot)]


def _cyclic(face):
    face = tuple(face)
    return min(face[i:] + face[:i] for i in range(len(face)))


def preservation_errors(cycles, source_vertices, output_faces, output_vertices, source_to_output,
                        origin=None):
    """Each protected cycle must exist once in the output at unchanged positions."""
    errors = []
    counts = Counter(_cyclic(face) for face in output_faces)
    for cycle in cycles:
        mapped = [source_to_output[vi] if 0 <= vi < len(source_to_output) else -1 for vi in cycle]
        if min(mapped) < 0:
            errors.append(f'Protected face {cycle} lost a vertex')
            continue
        for vi, target in zip(cycle, mapped):
            if origin is None:
                same = all(abs(a-b) <= 1e-9 for a, b in zip(source_vertices[vi], output_vertices[target]))
            else:
                # Output meshes store float32 local coordinates.
                same = all(struct.pack('<f', a-c) == struct.pack('<f', b-c)
                           for a, b, c in zip(source_vertices[vi], output_vertices[target], origin))
            if not same:
                errors.append(f'Protected vertex {vi} moved')
                break
        key = _cyclic(mapped)
        if counts[key] <= 0:
            errors.append(f'Protected face {cycle} changed')
        else:
            counts[key] -= 1
    return errors


def mark_output(mesh, cycles, source_to_output):
    """Flag the output faces of validated protected cycles; return how many.

    Called only after ``preservation_errors`` passed, so every cycle maps to
    exactly one output face. Unmapped cycles are ignored rather than guessed."""
    wanted = Counter()
    for cycle in cycles:
        mapped = [source_to_output[vi] if 0 <= vi < len(source_to_output) else -1 for vi in cycle]
        if min(mapped) >= 0:
            wanted[_cyclic(mapped)] += 1
    values = [False] * len(mesh.polygons)
    for polygon in mesh.polygons:
        key = _cyclic(polygon.vertices)
        if wanted[key] > 0:
            values[polygon.index] = True
            wanted[key] -= 1
    attr = mesh.attributes.get(ATTRIBUTE)
    if attr is not None and (attr.domain != 'FACE' or attr.data_type != 'BOOLEAN'):
        mesh.attributes.remove(attr)
        attr = None
    if attr is None:
        attr = mesh.attributes.new(ATTRIBUTE, 'BOOLEAN', 'FACE')
    attr.data.foreach_set('value', values)
    return sum(values)
