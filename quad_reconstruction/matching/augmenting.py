from __future__ import annotations

from collections import deque

from ..models import CandidatePair, MatchingResult, TriangleRegion


def _candidate_key(candidate: CandidatePair):
    return (
        round(candidate.cost, 12),
        candidate.metrics.attribute_violation_count,
        candidate.dissolve_edge_index,
        candidate.face_indices,
        candidate.index,
    )


def _mate_map(selected: set[int], candidates: tuple[CandidatePair, ...]):
    mate: dict[int, tuple[int, int]] = {}
    for candidate_index in selected:
        candidate = candidates[candidate_index]
        face_a, face_b = candidate.face_indices
        mate[face_a] = (face_b, candidate_index)
        mate[face_b] = (face_a, candidate_index)
    return mate


def _is_face_disjoint(
    selected: set[int],
    candidates: tuple[CandidatePair, ...],
) -> bool:
    matched_faces: set[int] = set()
    for candidate_index in selected:
        face_indices = candidates[candidate_index].face_indices
        if not matched_faces.isdisjoint(face_indices):
            return False
        matched_faces.update(face_indices)
    return True


def _find_augmenting_path(
    free_faces: tuple[int, ...],
    selected: set[int],
    candidates: tuple[CandidatePair, ...],
    adjacency: dict[int, tuple[int, ...]],
) -> tuple[int, ...]:
    mate = _mate_map(selected, candidates)
    for start in free_faces:
        queue = deque([start])
        visited_even = {start}
        visited_odd: set[int] = set()
        parents: dict[int, tuple[int, int, int]] = {}
        while queue:
            current = queue.popleft()
            for candidate_index in adjacency.get(current, ()):
                if candidate_index in selected:
                    continue
                candidate = candidates[candidate_index]
                neighbor = (
                    candidate.face_indices[1]
                    if candidate.face_indices[0] == current
                    else candidate.face_indices[0]
                )
                if neighbor in visited_odd or neighbor == start:
                    continue
                visited_odd.add(neighbor)
                if neighbor not in mate:
                    segments = []
                    node = current
                    while node != start:
                        parent, unmatched_candidate, matched_candidate = parents[node]
                        segments.append((unmatched_candidate, matched_candidate))
                        node = parent
                    path = []
                    for unmatched_candidate, matched_candidate in reversed(segments):
                        path.extend((unmatched_candidate, matched_candidate))
                    path.append(candidate_index)
                    return tuple(path)
                matched_neighbor, matched_candidate = mate[neighbor]
                if matched_neighbor in visited_even:
                    continue
                visited_even.add(matched_neighbor)
                parents[matched_neighbor] = (current, candidate_index, matched_candidate)
                queue.append(matched_neighbor)
    return ()


def _improve_four_cycles(
    selected: set[int],
    candidates: tuple[CandidatePair, ...],
    valid_candidates: tuple[CandidatePair, ...],
) -> int:
    """Apply one deterministic four-cycle improvement."""
    by_faces = {
        tuple(sorted(candidate.face_indices)): candidate.index
        for candidate in valid_candidates
    }
    mate = _mate_map(selected, candidates)
    for alternative_a in sorted(valid_candidates, key=_candidate_key):
        if alternative_a.index in selected:
            continue
        face_a, face_b = alternative_a.face_indices
        matched_a = mate.get(face_a)
        matched_b = mate.get(face_b)
        if matched_a is None or matched_b is None:
            continue
        mate_a, selected_a = matched_a
        mate_b, selected_b = matched_b
        if selected_a == selected_b or mate_a == mate_b:
            continue
        alternative_b_index = by_faces.get(tuple(sorted((mate_a, mate_b))))
        if alternative_b_index is None or alternative_b_index in selected:
            continue
        old_cost = candidates[selected_a].cost + candidates[selected_b].cost
        new_cost = alternative_a.cost + candidates[alternative_b_index].cost
        old_key = (round(old_cost, 12), tuple(sorted((selected_a, selected_b))))
        new_key = (
            round(new_cost, 12),
            tuple(sorted((alternative_a.index, alternative_b_index))),
        )
        if new_key < old_key:
            selected.difference_update((selected_a, selected_b))
            selected.update((alternative_a.index, alternative_b_index))
            return 1
    return 0


def solve_seed_augment(
    regions: tuple[TriangleRegion, ...],
    candidates: tuple[CandidatePair, ...],
    *,
    seed_edge_indices: tuple[int, ...] = (),
    maximum_iterations: int = 8,
) -> MatchingResult:
    region_indices = {region.index for region in regions}
    valid = tuple(
        candidate
        for candidate in candidates
        if candidate.hard_valid and candidate.region_index in region_indices
    )
    all_faces = tuple(sorted(face for region in regions for face in region.face_indices))
    adjacency_lists: dict[int, list[int]] = {face: [] for face in all_faces}
    for candidate in sorted(valid, key=_candidate_key):
        for face_index in candidate.face_indices:
            adjacency_lists.setdefault(face_index, []).append(candidate.index)
    adjacency = {
        face: tuple(sorted(indices, key=lambda index: _candidate_key(candidates[index])))
        for face, indices in adjacency_lists.items()
    }

    selected: set[int] = set()
    matched_faces: set[int] = set()
    seed_edges = set(seed_edge_indices)
    seeded = sorted(
        (candidate for candidate in valid if candidate.dissolve_edge_index in seed_edges),
        key=_candidate_key,
    )
    for candidate in (*seeded, *sorted(valid, key=_candidate_key)):
        if matched_faces.isdisjoint(candidate.face_indices):
            selected.add(candidate.index)
            matched_faces.update(candidate.face_indices)

    while True:
        mate = _mate_map(selected, candidates)
        free_faces = tuple(face for face in all_faces if face not in mate)
        path = _find_augmenting_path(free_faces, selected, candidates, adjacency)
        if not path:
            break
        proposed = set(selected)
        for candidate_index in path:
            if candidate_index in proposed:
                proposed.remove(candidate_index)
            else:
                proposed.add(candidate_index)
        if not _is_face_disjoint(proposed, candidates):
            break
        selected = proposed

    cycle_passes = 0
    cycle_limit_reached = False
    for _iteration in range(maximum_iterations):
        cycle_passes += 1
        improvements = _improve_four_cycles(selected, candidates, valid)
        if improvements == 0:
            break
        cycle_limit_reached = cycle_passes == maximum_iterations

    mate = _mate_map(selected, candidates)
    if len(mate) != len(selected) * 2:
        raise RuntimeError("Seed + augment produced an invalid overlapping matching.")
    selected_indices = tuple(sorted(selected))
    return MatchingResult(
        backend="SEED_AUGMENT",
        selected_candidate_indices=selected_indices,
        unmatched_face_indices=tuple(face for face in all_faces if face not in mate),
        cardinality=len(selected_indices),
        total_cost=sum(candidates[index].cost for index in selected_indices),
        exact=False,
        warnings=(
            "Seed + augment does not guarantee maximum-cardinality matching on general odd-cycle graphs.",
            *(
                ("Alternating cycle optimization reached its configured pass limit.",)
                if cycle_limit_reached
                else ()
            ),
        ),
    )
