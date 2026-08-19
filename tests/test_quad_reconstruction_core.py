from __future__ import annotations

import sys
import unittest
from pathlib import Path


ADDON_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADDON_ROOT))

from quad_reconstruction.audit import audit_snapshot
from quad_reconstruction.models import (
    EdgeSnapshot,
    LoopSnapshot,
    MeshClassification,
    MeshSnapshot,
    PolygonSnapshot,
    UVLayerSnapshot,
)
from quad_reconstruction.regions import RegionSettings, build_triangle_regions
from quad_reconstruction.fingerprint import fingerprint_snapshot


def make_snapshot(
    faces: tuple[tuple[int, ...], ...],
    *,
    seams: set[tuple[int, int]] | None = None,
    materials: tuple[int, ...] | None = None,
    split_uv_edge: tuple[int, int] | None = None,
) -> MeshSnapshot:
    seams = seams or set()
    vertex_count = max(vertex for face in faces for vertex in face) + 1
    vertices = tuple((float(index % 2), float(index // 2), 0.0) for index in range(vertex_count))
    edge_index_by_key: dict[tuple[int, int], int] = {}
    edge_faces: list[list[int]] = []
    loops = []
    polygons = []
    uv_values = []
    vertex_to_edges = [set() for _ in range(vertex_count)]
    vertex_to_faces = [set() for _ in range(vertex_count)]

    for face_index, face in enumerate(faces):
        loop_indices = []
        for offset, vertex_index in enumerate(face):
            next_vertex = face[(offset + 1) % len(face)]
            edge_key = tuple(sorted((vertex_index, next_vertex)))
            if edge_key not in edge_index_by_key:
                edge_index_by_key[edge_key] = len(edge_faces)
                edge_faces.append([])
            edge_index = edge_index_by_key[edge_key]
            if face_index not in edge_faces[edge_index]:
                edge_faces[edge_index].append(face_index)
            loop_indices.append(len(loops))
            loops.append(LoopSnapshot(vertex_index=vertex_index, edge_index=edge_index))
            uv = (vertices[vertex_index][0], vertices[vertex_index][1])
            if split_uv_edge and vertex_index in split_uv_edge and face_index == 1:
                uv = (uv[0] + 2.0, uv[1])
            uv_values.append(uv)
            vertex_to_edges[vertex_index].add(edge_index)
            vertex_to_faces[vertex_index].add(face_index)
        polygons.append(
            PolygonSnapshot(
                index=face_index,
                vertices=face,
                loop_indices=tuple(loop_indices),
                normal=(0.0, 0.0, 1.0),
                material_index=materials[face_index] if materials else 0,
                area=0.5,
            )
        )

    edges_by_index = [None] * len(edge_index_by_key)
    for edge_key, edge_index in edge_index_by_key.items():
        edges_by_index[edge_index] = EdgeSnapshot(
            index=edge_index,
            vertices=edge_key,
            face_indices=tuple(sorted(edge_faces[edge_index])),
            seam=edge_key in seams,
            sharp=False,
            locked=False,
        )

    snapshot = MeshSnapshot(
        source_uuid="fixture",
        source_object_name="Fixture",
        source_mesh_name="FixtureMesh",
        vertices=vertices,
        edges=tuple(edges_by_index),
        loops=tuple(loops),
        polygons=tuple(polygons),
        vertex_to_edges=tuple(tuple(sorted(values)) for values in vertex_to_edges),
        vertex_to_faces=tuple(tuple(sorted(values)) for values in vertex_to_faces),
        uv_layers=(UVLayerSnapshot(name="UVMap", values=tuple(uv_values)),),
        attributes=(),
        material_slots=("Material",),
        has_custom_normals=False,
        custom_normals=(),
        modifier_types=(),
        matrix_world=(1.0,) * 16,
        scale=(1.0, 1.0, 1.0),
        parent_reference="",
        fingerprint="",
    )
    return snapshot


class AuditTests(unittest.TestCase):
    def test_closed_triangulated_mesh(self):
        snapshot = make_snapshot(
            ((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3))
        )
        audit = audit_snapshot(snapshot)
        self.assertEqual(audit.classification, MeshClassification.CLEAN_TRIANGULATED)
        self.assertEqual(audit.boundary_edge_count, 0)

    def test_open_triangulated_mesh(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        audit = audit_snapshot(snapshot)
        self.assertEqual(audit.classification, MeshClassification.OPEN_TRIANGULATED)
        self.assertEqual(audit.triangle_count, 2)
        self.assertEqual(audit.boundary_edge_count, 4)
        self.assertEqual(len(audit.connected_components), 1)

    def test_mixed_mesh(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 3, 4, 5)))
        audit = audit_snapshot(snapshot)
        self.assertEqual(audit.classification, MeshClassification.MIXED_TRI_QUAD)
        self.assertEqual((audit.triangle_count, audit.quad_count), (1, 1))

    def test_true_non_manifold_edge(self):
        snapshot = make_snapshot(((0, 1, 2), (1, 0, 3), (0, 1, 4)))
        audit = audit_snapshot(snapshot)
        self.assertEqual(audit.classification, MeshClassification.TRUE_NON_MANIFOLD)
        self.assertEqual(audit.true_non_manifold_edge_count, 1)
        regions = build_triangle_regions(snapshot, RegionSettings())
        self.assertEqual(len(regions), 3)
        self.assertTrue(all(not region.candidate_edge_indices for region in regions))

    def test_degenerate_and_duplicate_faces(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 0)))
        audit = audit_snapshot(snapshot)
        self.assertEqual(audit.classification, MeshClassification.DEGENERATE)
        self.assertEqual(audit.duplicate_face_indices, (1,))

    def test_degenerate_faces_are_isolated_as_barrier_regions(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3), (3, 1, 4)))
        polygons = list(snapshot.polygons)
        polygons[1] = PolygonSnapshot(
            index=1,
            vertices=polygons[1].vertices,
            loop_indices=polygons[1].loop_indices,
            normal=polygons[1].normal,
            material_index=polygons[1].material_index,
            area=0.0,
        )
        snapshot = MeshSnapshot(
            source_uuid=snapshot.source_uuid,
            source_object_name=snapshot.source_object_name,
            source_mesh_name=snapshot.source_mesh_name,
            vertices=snapshot.vertices,
            edges=snapshot.edges,
            loops=snapshot.loops,
            polygons=tuple(polygons),
            vertex_to_edges=snapshot.vertex_to_edges,
            vertex_to_faces=snapshot.vertex_to_faces,
            uv_layers=snapshot.uv_layers,
            attributes=snapshot.attributes,
            material_slots=snapshot.material_slots,
            has_custom_normals=snapshot.has_custom_normals,
            custom_normals=snapshot.custom_normals,
            modifier_types=snapshot.modifier_types,
            matrix_world=snapshot.matrix_world,
            scale=snapshot.scale,
            parent_reference=snapshot.parent_reference,
            fingerprint=snapshot.fingerprint,
        )
        regions = build_triangle_regions(snapshot, RegionSettings())
        unsafe_region = next(region for region in regions if region.face_indices == (1,))
        self.assertFalse(unsafe_region.candidate_edge_indices)


class RegionTests(unittest.TestCase):
    def test_continuous_pair_forms_one_region(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        regions = build_triangle_regions(snapshot, RegionSettings())
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].face_indices, (0, 1))
        self.assertEqual(len(regions[0].candidate_edge_indices), 1)

    def test_seam_material_and_uv_are_hard_barriers(self):
        shared_edge = (1, 2)
        seam_snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)), seams={shared_edge})
        material_snapshot = make_snapshot(
            ((0, 1, 2), (2, 1, 3)),
            materials=(0, 1),
        )
        uv_snapshot = make_snapshot(
            ((0, 1, 2), (2, 1, 3)),
            split_uv_edge=shared_edge,
        )
        for snapshot in (seam_snapshot, material_snapshot, uv_snapshot):
            self.assertEqual(len(build_triangle_regions(snapshot, RegionSettings())), 2)

    def test_fingerprint_changes_with_geometry(self):
        snapshot = make_snapshot(((0, 1, 2),))
        first = fingerprint_snapshot(snapshot)
        changed = MeshSnapshot(
            source_uuid=snapshot.source_uuid,
            source_object_name=snapshot.source_object_name,
            source_mesh_name=snapshot.source_mesh_name,
            vertices=((0.1, 0.0, 0.0), *snapshot.vertices[1:]),
            edges=snapshot.edges,
            loops=snapshot.loops,
            polygons=snapshot.polygons,
            vertex_to_edges=snapshot.vertex_to_edges,
            vertex_to_faces=snapshot.vertex_to_faces,
            uv_layers=snapshot.uv_layers,
            attributes=snapshot.attributes,
            material_slots=snapshot.material_slots,
            has_custom_normals=snapshot.has_custom_normals,
            custom_normals=snapshot.custom_normals,
            modifier_types=snapshot.modifier_types,
            matrix_world=snapshot.matrix_world,
            scale=snapshot.scale,
            parent_reference=snapshot.parent_reference,
            fingerprint="",
        )
        self.assertNotEqual(first, fingerprint_snapshot(changed))

    def test_open_faces_can_be_excluded_without_skipping_audit(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        regions = build_triangle_regions(
            snapshot,
            RegionSettings(process_open_meshes=False),
        )
        self.assertEqual(regions, ())

    def test_core_results_are_deterministic(self):
        snapshot = make_snapshot(((0, 1, 2), (2, 1, 3)))
        settings = RegionSettings()
        self.assertEqual(audit_snapshot(snapshot), audit_snapshot(snapshot))
        self.assertEqual(
            build_triangle_regions(snapshot, settings),
            build_triangle_regions(snapshot, settings),
        )
        self.assertEqual(fingerprint_snapshot(snapshot), fingerprint_snapshot(snapshot))


if __name__ == "__main__":
    unittest.main()
