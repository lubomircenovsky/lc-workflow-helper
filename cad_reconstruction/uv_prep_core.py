"""Geometry-only cut planning for CAD-aware UV preparation."""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from dataclasses import dataclass


EdgeKey = tuple[int, int]


@dataclass(frozen=True)
class UVCutPlan:
    cuts: frozenset[EdgeKey]
    angle_cuts: int
    material_cuts: int
    annulus_slits: int
    face_regions: int


def _edge(a: int, b: int) -> EdgeKey:
    return (a, b) if a < b else (b, a)


def _boundary_loops(edges: list[EdgeKey]) -> list[tuple[int, ...]]:
    neighbors: dict[int, list[int]] = defaultdict(list)
    for a, b in edges:
        neighbors[a].append(b)
        neighbors[b].append(a)
    if not neighbors or any(len(items) != 2 for items in neighbors.values()):
        return []
    remaining = set(neighbors)
    loops = []
    while remaining:
        start = min(remaining)
        loop = [start]
        previous = -1
        current = start
        while True:
            following = min(item for item in neighbors[current] if item != previous)
            if following == start:
                break
            if following not in remaining or len(loop) > len(neighbors):
                return []
            loop.append(following)
            previous, current = current, following
        remaining.difference_update(loop)
        loops.append(tuple(loop))
    return loops


def _slit_between_rims(
    vertices: tuple[tuple[float, float, float], ...],
    interior_edges: list[EdgeKey],
    loops: list[tuple[int, ...]],
) -> list[EdgeKey]:
    interior: dict[int, list[tuple[int, EdgeKey, float]]] = defaultdict(list)
    for key in interior_edges:
        a, b = key
        length = math.dist(vertices[a], vertices[b])
        interior[a].append((b, key, length))
        interior[b].append((a, key, length))

    targets = set(loops[1])
    queue = [(0.0, vertex) for vertex in sorted(loops[0])]
    heapq.heapify(queue)
    previous: dict[int, tuple[int, EdgeKey] | None] = {
        vertex: None for vertex in loops[0]
    }
    distances = {vertex: 0.0 for vertex in loops[0]}
    while queue:
        distance, vertex = heapq.heappop(queue)
        if distance != distances[vertex]:
            continue
        if vertex in targets:
            path = []
            while previous[vertex] is not None:
                vertex, key = previous[vertex]
                path.append(key)
            return path
        for other, key, length in sorted(interior[vertex]):
            candidate = distance + length
            if candidate < distances.get(other, math.inf):
                distances[other] = candidate
                previous[other] = (vertex, key)
                heapq.heappush(queue, (candidate, other))
    return []


def plan_uv_cuts(
    vertices: tuple[tuple[float, float, float], ...],
    faces: tuple[tuple[int, ...], ...],
    normals: tuple[tuple[float, float, float], ...],
    materials: tuple[int, ...],
    angle_degrees: float = 45.0,
) -> UVCutPlan:
    """Cut strong folds; keep smooth bends; open isolated annular wall regions."""
    if not 0.0 < angle_degrees < 180.0:
        raise ValueError("The UV cut angle must be between 0 and 180 degrees")
    if len(faces) != len(normals) or len(faces) != len(materials):
        raise ValueError("UV face metadata does not match the mesh")

    incidence: dict[EdgeKey, list[int]] = defaultdict(list)
    for index, face in enumerate(faces):
        if len(face) < 3 or len(set(face)) != len(face):
            raise ValueError(f"Face {index} has invalid topology")
        for offset, vertex in enumerate(face):
            incidence[_edge(vertex, face[(offset + 1) % len(face)])].append(index)

    cuts: set[EdgeKey] = set()
    angle_cuts = material_cuts = 0
    threshold = math.cos(math.radians(angle_degrees))
    neighbors: list[list[int]] = [[] for _ in faces]
    for key, linked in incidence.items():
        if len(linked) != 2:
            cuts.add(key)
            continue
        a, b = linked
        if materials[a] != materials[b]:
            cuts.add(key)
            material_cuts += 1
            continue
        cosine = sum(x * y for x, y in zip(normals[a], normals[b]))
        if cosine < threshold - 1e-9:
            cuts.add(key)
            angle_cuts += 1
            continue
        neighbors[a].append(b)
        neighbors[b].append(a)

    visited: set[int] = set()
    regions: list[set[int]] = []
    for seed in range(len(faces)):
        if seed in visited:
            continue
        region = {seed}
        stack = [seed]
        visited.add(seed)
        while stack:
            for other in neighbors[stack.pop()]:
                if other not in visited:
                    visited.add(other)
                    region.add(other)
                    stack.append(other)
        regions.append(region)

    region_ids = [0] * len(faces)
    for index, region in enumerate(regions):
        for face in region:
            region_ids[face] = index
    boundaries: list[list[EdgeKey]] = [[] for _ in regions]
    interiors: list[list[EdgeKey]] = [[] for _ in regions]
    for key, linked in incidence.items():
        owners = {region_ids[face] for face in linked}
        if len(linked) == 2 and len(owners) == 1:
            interiors[next(iter(owners))].append(key)
        else:
            for owner in owners:
                boundaries[owner].append(key)

    slits = 0
    for index, region in enumerate(regions):
        if len(region) < 6:
            continue
        first = normals[min(region)]
        if all(sum(a * b for a, b in zip(first, normals[index])) > 0.5 for index in region):
            continue
        loops = _boundary_loops(boundaries[index])
        if len(loops) != 2 or min(map(len, loops)) < 6:
            continue
        path = _slit_between_rims(vertices, interiors[index], loops)
        if path:
            cuts.update(path)
            slits += 1

    return UVCutPlan(frozenset(cuts), angle_cuts, material_cuts, slits, len(regions))
