"""Map stored worker diagnostics to polygons of the source mesh (no bpy).

The worker writes the triangle pairs that intersect into
``validation_source.json``. Their indices refer to ``triangles`` in the run's
``source.json``, which for Separate Solids is a sub-mesh of the source object.
This module turns them into polygon indices of the original Blender mesh.
"""
from __future__ import annotations

import json
from pathlib import Path

SOURCE = "source.json"
VALIDATION = "validation_source.json"


def triangle_polygons(source: dict) -> list[list[int]]:
    """Return the candidate source polygons (run-local indices) of every triangle.

    Uses the capture's explicit ``triangle_polygons`` when present. A
    Separate Solids sub-mesh drops that map, so the owner is the polygon that
    contains all three triangle vertices; an ambiguous triangle keeps every
    candidate rather than guessing.
    """
    explicit = source.get("triangle_polygons")
    if explicit is not None:
        return [[int(index)] for index in explicit]
    faces_of_vertex: dict[int, set[int]] = {}
    for face_index, face in enumerate(source["faces"]):
        for vertex in face:
            faces_of_vertex.setdefault(vertex, set()).add(face_index)
    owners = []
    for triangle in source["triangles"]:
        candidates = set.intersection(*(faces_of_vertex.get(vertex, set()) for vertex in triangle))
        if not candidates:
            raise ValueError("A stored triangle does not belong to any source polygon")
        owners.append(sorted(candidates))
    return owners


def intersection_polygons(source: dict, validation: dict) -> tuple[list[int], int]:
    """Return (sorted source-object polygon indices, intersecting pair count)."""
    pairs = validation.get("intersections") or []
    owners = triangle_polygons(source)
    local = set()
    for pair in pairs:
        for key in ("a", "b"):
            index = int(pair[key])
            if not 0 <= index < len(owners):
                raise ValueError("Stored intersection refers to a missing triangle")
            local.update(owners[index])
    face_ids = source.get("source_face_ids") or list(range(len(source["faces"])))
    return sorted({int(face_ids[index]) for index in local}), len(pairs)


def load_intersections(run_dir: str | Path) -> tuple[str, list[int], int]:
    """Read a run folder; return (source_hash, polygon indices, pair count)."""
    run_dir = Path(run_dir)
    source_path, validation_path = run_dir / SOURCE, run_dir / VALIDATION
    if not source_path.is_file() or not validation_path.is_file():
        raise FileNotFoundError("This run has no stored intersection diagnostics")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    polygons, pairs = intersection_polygons(source, validation)
    return source.get("source_hash", ""), polygons, pairs
