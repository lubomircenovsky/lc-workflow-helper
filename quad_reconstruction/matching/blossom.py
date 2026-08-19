from __future__ import annotations

from dataclasses import dataclass

from ..models import CandidatePair, MatchingResult, TriangleRegion
from ._vendor.networkx_blossom import max_weight_matching


COST_SCALE = 1_000_000
SECONDARY_SCALE = 1_000_000


class _EdgeView:
    def __init__(self, graph: "_SimpleGraph") -> None:
        self._graph = graph

    def __call__(self, data: bool = False):
        for first, second in self._graph._edge_keys:
            if data:
                yield first, second, self._graph._adjacency[first][second]
            else:
                yield first, second


class _SimpleGraph:
    """Minimal deterministic graph API consumed by the vendored blossom function."""

    def __init__(self) -> None:
        self._adjacency: dict[int, dict[int, dict[str, int]]] = {}
        self._edge_keys: list[tuple[int, int]] = []
        self.edges = _EdgeView(self)

    def add_node(self, node: int) -> None:
        self._adjacency.setdefault(node, {})

    def add_edge(self, first: int, second: int, weight: int) -> None:
        if first == second:
            raise ValueError("Self-loops are not valid matching candidates.")
        first, second = sorted((first, second))
        self.add_node(first)
        self.add_node(second)
        data = {"weight": weight}
        self._adjacency[first][second] = data
        self._adjacency[second][first] = data
        self._edge_keys.append((first, second))
        self._edge_keys.sort()

    def neighbors(self, node: int) -> tuple[int, ...]:
        return tuple(sorted(self._adjacency[node]))

    def nodes(self) -> tuple[int, ...]:
        return tuple(sorted(self._adjacency))

    def __iter__(self):
        return iter(self.nodes())

    def __getitem__(self, node: int):
        return self._adjacency[node]


@dataclass(frozen=True, slots=True)
class _EncodedCandidate:
    candidate: CandidatePair
    penalty: int


def _stable_candidate_key(candidate: CandidatePair):
    return (
        round(candidate.cost, 12),
        candidate.metrics.attribute_violation_count,
        round(
            candidate.metrics.valence_delta
            + candidate.metrics.flow_alignment_error,
            12,
        ),
        candidate.dissolve_edge_index,
        candidate.face_indices,
        candidate.index,
    )


def _encode_region_candidates(
    region: TriangleRegion,
    candidates: tuple[CandidatePair, ...],
) -> tuple[_EncodedCandidate, ...]:
    valid = sorted(
        (
            candidate
            for candidate in candidates
            if candidate.region_index == region.index and candidate.hard_valid
        ),
        key=_stable_candidate_key,
    )
    best_by_pair: dict[tuple[int, int], CandidatePair] = {}
    for candidate in valid:
        key = tuple(sorted(candidate.face_indices))
        best_by_pair.setdefault(key, candidate)
    canonical = tuple(sorted(best_by_pair.values(), key=_stable_candidate_key))
    if not canonical:
        return ()

    pair_limit = max(1, len(region.face_indices) // 2)
    tie_span = pair_limit * len(canonical) + 1
    valence_values = tuple(
        max(
            0,
            round(
                (
                    candidate.metrics.valence_delta
                    + candidate.metrics.flow_alignment_error
                )
                * SECONDARY_SCALE
            ),
        )
        for candidate in canonical
    )
    valence_span = pair_limit * max((*valence_values, 0)) + 1
    attribute_span = (
        pair_limit
        * max((candidate.metrics.attribute_violation_count for candidate in canonical), default=0)
        + 1
    )

    encoded = []
    for tie_rank, (candidate, valence_value) in enumerate(
        zip(canonical, valence_values, strict=True)
    ):
        cost_value = max(0, round(candidate.cost * COST_SCALE))
        penalty = (
            (
                (cost_value * attribute_span + candidate.metrics.attribute_violation_count)
                * valence_span
                + valence_value
            )
            * tie_span
            + tie_rank
        )
        encoded.append(_EncodedCandidate(candidate, penalty))
    return tuple(encoded)


def _solve_region(
    region: TriangleRegion,
    candidates: tuple[CandidatePair, ...],
) -> tuple[int, ...]:
    encoded = _encode_region_candidates(region, candidates)
    graph = _SimpleGraph()
    for face_index in region.face_indices:
        graph.add_node(face_index)
    candidate_by_pair = {}
    for item in encoded:
        pair = tuple(sorted(item.candidate.face_indices))
        candidate_by_pair[pair] = item.candidate.index
        graph.add_edge(*pair, weight=-item.penalty)
    matched_pairs = max_weight_matching(graph, maxcardinality=True, weight="weight")
    return tuple(
        sorted(candidate_by_pair[tuple(sorted(pair))] for pair in matched_pairs)
    )


def solve_exact_blossom(
    regions: tuple[TriangleRegion, ...],
    candidates: tuple[CandidatePair, ...],
    *,
    max_region_triangles: int = 2000,
) -> MatchingResult:
    selected = []
    warnings = []
    exact = True
    unresolved_oversized: set[int] = set()
    for region in sorted(regions, key=lambda item: item.index):
        if len(region.face_indices) > max_region_triangles:
            exact = False
            unresolved_oversized.update(region.face_indices)
            warnings.append(
                f"Region {region.index} has {len(region.face_indices)} triangles; "
                f"Exact Blossom limit is {max_region_triangles}, so it remains unresolved."
            )
            continue
        selected.extend(_solve_region(region, candidates))

    selected_indices = tuple(sorted(selected))
    matched_faces = {
        face_index
        for candidate_index in selected_indices
        for face_index in candidates[candidate_index].face_indices
    }
    all_faces = tuple(sorted(face for region in regions for face in region.face_indices))
    unmatched = tuple(
        face for face in all_faces if face not in matched_faces or face in unresolved_oversized
    )
    return MatchingResult(
        backend="EXACT_BLOSSOM",
        selected_candidate_indices=selected_indices,
        unmatched_face_indices=unmatched,
        cardinality=len(selected_indices),
        total_cost=sum(candidates[index].cost for index in selected_indices),
        exact=exact,
        warnings=tuple(warnings),
    )
