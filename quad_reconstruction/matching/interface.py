from __future__ import annotations

from typing import Protocol

from ..models import CandidatePair, MatchingResult, TriangleRegion


class MatchingSolver(Protocol):
    def __call__(
        self,
        backend: str,
        regions: tuple[TriangleRegion, ...],
        candidates: tuple[CandidatePair, ...],
        *,
        seed_edge_indices: tuple[int, ...] = (),
        exact_component_limit: int = 2000,
        maximum_iterations: int = 8,
    ) -> MatchingResult: ...
