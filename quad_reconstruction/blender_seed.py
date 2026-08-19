from __future__ import annotations

import math
import time

import bmesh
import bpy

from .models import NativeBaselineResult


def build_native_seed_edges(
    mesh: bpy.types.Mesh,
    *,
    protect_materials: bool,
    protect_uv: bool,
    protect_seams: bool,
    protect_sharp_edges: bool,
    topology_influence: float,
) -> tuple[int, ...]:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.edges.index_update()
        source_layer = bm.edges.layers.int.new("lcw_aiq_source_edge")
        for edge in bm.edges:
            edge[source_layer] = edge.index
        triangle_faces = [face for face in bm.faces if len(face.verts) == 3]
        bmesh.ops.join_triangles(
            bm,
            faces=triangle_faces,
            cmp_seam=protect_seams,
            cmp_sharp=protect_sharp_edges,
            cmp_uvs=protect_uv,
            cmp_vcols=True,
            cmp_materials=protect_materials,
            angle_face_threshold=math.pi,
            angle_shape_threshold=math.pi,
            topology_influence=topology_influence,
            deselect_joined=False,
        )
        remaining_source_edges = {
            edge[source_layer]
            for edge in bm.edges
            if edge.is_valid and edge[source_layer] >= 0
        }
        return tuple(
            edge_index
            for edge_index in range(len(mesh.edges))
            if edge_index not in remaining_source_edges
        )
    finally:
        bm.free()


def run_native_baselines(
    mesh: bpy.types.Mesh,
    *,
    protect_materials: bool,
    protect_uv: bool,
    protect_seams: bool,
    protect_sharp_edges: bool,
    topology_influence: float,
) -> tuple[NativeBaselineResult, ...]:
    hypotheses = (
        ("Protected Conservative", math.radians(40.0), math.radians(40.0), 0.0),
        ("Protected Topology", math.pi, math.pi, topology_influence),
        ("Protected Permissive", math.pi, math.pi, 1.0),
    )
    results = []
    for name, face_threshold, shape_threshold, hypothesis_influence in hypotheses:
        started = time.perf_counter()
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            bm.faces.ensure_lookup_table()
            bm.faces.index_update()
            original_face_count = len(bm.faces)
            triangle_faces = sorted(
                (face for face in bm.faces if len(face.verts) == 3),
                key=lambda face: face.index,
            )
            bmesh.ops.join_triangles(
                bm,
                faces=triangle_faces,
                cmp_seam=protect_seams,
                cmp_sharp=protect_sharp_edges,
                cmp_uvs=protect_uv,
                cmp_vcols=True,
                cmp_materials=protect_materials,
                angle_face_threshold=face_threshold,
                angle_shape_threshold=shape_threshold,
                topology_influence=hypothesis_influence,
                deselect_joined=False,
            )
            remaining_triangles = sum(len(face.verts) == 3 for face in bm.faces)
            resulting_quads = sum(len(face.verts) == 4 for face in bm.faces)
            results.append(
                NativeBaselineResult(
                    name=name,
                    topology_influence=hypothesis_influence,
                    joined_pairs=max(0, original_face_count - len(bm.faces)),
                    remaining_triangles=remaining_triangles,
                    resulting_quads=resulting_quads,
                    runtime_seconds=time.perf_counter() - started,
                )
            )
        except Exception as exc:
            results.append(
                NativeBaselineResult(
                    name=name,
                    topology_influence=hypothesis_influence,
                    joined_pairs=0,
                    remaining_triangles=0,
                    resulting_quads=0,
                    runtime_seconds=time.perf_counter() - started,
                    error=str(exc),
                )
            )
        finally:
            bm.free()
    return tuple(results)
