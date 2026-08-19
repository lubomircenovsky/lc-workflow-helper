from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from .models import CandidatePair, MeshAudit, TriangleRegion


@dataclass(frozen=True, slots=True)
class CachedPreparation:
    audit: MeshAudit
    regions: tuple[TriangleRegion, ...]
    candidates: tuple[CandidatePair, ...]


class PreparationCache:
    """Small LRU cache containing only immutable pure-core results."""

    def __init__(self, max_entries: int = 8) -> None:
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[object, ...], CachedPreparation] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple[object, ...]) -> CachedPreparation | None:
        value = self._entries.get(key)
        if value is None:
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key: tuple[object, ...], value: CachedPreparation) -> None:
        self._entries[key] = value
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
        self.hits = 0
        self.misses = 0

    def info(self) -> dict[str, int]:
        return {
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
            "max_entries": self.max_entries,
        }


PREPARATION_CACHE = PreparationCache()


def preparation_cache_key(
    fingerprint: str,
    area_tolerance: float,
    region_settings,
    candidate_settings,
) -> tuple[object, ...]:
    return (
        fingerprint,
        area_tolerance,
        region_settings,
        candidate_settings,
    )
