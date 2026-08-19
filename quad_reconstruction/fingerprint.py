from __future__ import annotations

import hashlib
import struct

from .models import MeshSnapshot


def _feed_hash(digest, value: object) -> None:
    if value is None:
        digest.update(b"N")
    elif isinstance(value, bool):
        digest.update(b"B\x01" if value else b"B\x00")
    elif isinstance(value, int):
        digest.update(b"I" + str(value).encode("ascii") + b";")
    elif isinstance(value, float):
        digest.update(b"F" + struct.pack("<d", value))
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        digest.update(b"S" + struct.pack("<I", len(encoded)) + encoded)
    elif isinstance(value, (tuple, list)):
        digest.update(b"[")
        for item in value:
            _feed_hash(digest, item)
        digest.update(b"]")
    else:
        _feed_hash(digest, str(value))


def fingerprint_snapshot(snapshot: MeshSnapshot) -> str:
    digest = hashlib.blake2b(digest_size=32, person=b"LCW-AIQ-MESH-v1")
    _feed_hash(
        digest,
        (len(snapshot.vertices), len(snapshot.edges), len(snapshot.polygons), len(snapshot.loops)),
    )
    _feed_hash(digest, snapshot.vertices)
    _feed_hash(
        digest,
        tuple(
            (edge.vertices, edge.face_indices, edge.seam, edge.sharp, edge.locked)
            for edge in snapshot.edges
        ),
    )
    _feed_hash(
        digest,
        tuple((loop.vertex_index, loop.edge_index) for loop in snapshot.loops),
    )
    _feed_hash(
        digest,
        tuple(
            (polygon.vertices, polygon.loop_indices, polygon.material_index)
            for polygon in snapshot.polygons
        ),
    )
    _feed_hash(digest, tuple((layer.name, layer.values) for layer in snapshot.uv_layers))
    _feed_hash(
        digest,
        tuple(
            (layer.name, layer.domain, layer.data_type, layer.values)
            for layer in snapshot.attributes
        ),
    )
    _feed_hash(digest, snapshot.material_slots)
    _feed_hash(digest, snapshot.custom_normals)
    _feed_hash(digest, snapshot.modifier_types)
    _feed_hash(digest, snapshot.matrix_world)
    _feed_hash(digest, snapshot.scale)
    _feed_hash(digest, snapshot.parent_reference)
    return digest.hexdigest()
