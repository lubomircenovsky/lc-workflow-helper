from __future__ import annotations

import unittest

from quad_reconstruction.cache import CachedPreparation, PreparationCache
from quad_reconstruction.models import MeshAudit, MeshClassification


def _audit(face_count: int) -> MeshAudit:
    return MeshAudit(
        classification=MeshClassification.CLEAN_TRIANGULATED,
        vertex_count=3,
        edge_count=3,
        loop_count=3,
        face_count=face_count,
        triangle_count=face_count,
        quad_count=0,
        ngon_count=0,
        boundary_edge_count=3,
        true_non_manifold_edge_count=0,
        wire_edge_count=0,
        degenerate_face_indices=(),
        duplicate_face_indices=(),
        vertex_valences=(2, 2, 2),
        connected_components=(),
        uv_layer_names=(),
        attribute_names=(),
        has_custom_normals=False,
        modifier_types=(),
    )


class PreparationCacheTests(unittest.TestCase):
    def test_lru_is_bounded_and_reports_hits(self):
        cache = PreparationCache(max_entries=2)
        first = CachedPreparation(_audit(1), (), ())
        second = CachedPreparation(_audit(2), (), ())
        third = CachedPreparation(_audit(3), (), ())
        cache.put(("a",), first)
        cache.put(("b",), second)
        self.assertIs(cache.get(("a",)), first)
        cache.put(("c",), third)
        self.assertIsNone(cache.get(("b",)))
        self.assertEqual(cache.info()["entries"], 2)
        self.assertEqual(cache.info()["hits"], 1)


if __name__ == "__main__":
    unittest.main()
