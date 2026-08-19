from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

from LC_workflow_addon.quad_reconstruction.audit import audit_snapshot
from LC_workflow_addon.quad_reconstruction.blender_seed import build_native_seed_edges
from LC_workflow_addon.quad_reconstruction.candidates import (
    CandidateSettings,
    generate_candidates,
)
from LC_workflow_addon.quad_reconstruction.matching import solve_matching
from LC_workflow_addon.quad_reconstruction.reconstruction import apply_matching_to_mesh
from LC_workflow_addon.quad_reconstruction.regions import (
    RegionSettings,
    build_triangle_regions,
)
from LC_workflow_addon.quad_reconstruction.topology_snapshot import snapshot_object
from LC_workflow_addon.quad_reconstruction.validation import validate_reconstruction


def arguments():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="1000,10000,100000")
    parser.add_argument("--output", default="")
    return parser.parse_args(values)


def create_grid(target_triangles: int):
    cell_count = max(1, math.ceil(target_triangles / 2))
    columns = max(2, math.ceil(math.sqrt(cell_count)) + 1)
    rows = max(2, math.ceil(cell_count / (columns - 1)) + 1)
    vertices = [
        (float(column), float(row), 0.0)
        for row in range(rows)
        for column in range(columns)
    ]
    faces = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            if len(faces) >= target_triangles:
                break
            lower_left = row * columns + column
            lower_right = lower_left + 1
            upper_left = lower_left + columns
            upper_right = upper_left + 1
            faces.append((lower_left, lower_right, upper_left))
            if len(faces) < target_triangles:
                faces.append((upper_left, lower_right, upper_right))
    mesh = bpy.data.meshes.new(f"AIQ_Benchmark_{target_triangles}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def timed(timings, name, function):
    started = time.perf_counter()
    value = function()
    timings[name] = time.perf_counter() - started
    return value


def run_case(size: int):
    timings = {}
    source = create_grid(size)
    output = None
    output_mesh = None
    started = time.perf_counter()
    try:
        snapshot = timed(timings, "snapshot", lambda: snapshot_object(source, str(size)))
        source_fingerprint = snapshot.fingerprint
        audit = timed(timings, "audit", lambda: audit_snapshot(snapshot))
        region_settings = RegionSettings()
        regions = timed(
            timings,
            "regions",
            lambda: build_triangle_regions(snapshot, region_settings),
        )
        candidate_settings = CandidateSettings(profile="STRICT")
        candidates = timed(
            timings,
            "candidates_scoring",
            lambda: generate_candidates(snapshot, regions, candidate_settings),
        )
        seed_edges = timed(
            timings,
            "native_seed",
            lambda: build_native_seed_edges(
                source.data,
                protect_materials=True,
                protect_uv=True,
                protect_seams=True,
                protect_sharp_edges=True,
                topology_influence=0.5,
            ),
        )
        matching = timed(
            timings,
            "matching",
            lambda: solve_matching(
                "SEED_AUGMENT",
                regions,
                candidates,
                seed_edge_indices=seed_edges,
                maximum_iterations=8,
            ),
        )
        output_mesh = source.data.copy()
        output = source.copy()
        output.data = output_mesh
        bpy.context.scene.collection.objects.link(output)
        timed(
            timings,
            "application",
            lambda: apply_matching_to_mesh(output_mesh, snapshot, candidates, matching),
        )
        validation = timed(
            timings,
            "validation",
            lambda: validate_reconstruction(
                source,
                snapshot,
                output,
                candidates,
                matching,
                run_subdivision=False,
            ),
        )
        unchanged = snapshot_object(source, str(size)).fingerprint == source_fingerprint
        assert unchanged
        assert validation.valid
        return {
            "requested_triangles": size,
            "triangles": audit.triangle_count,
            "vertices": audit.vertex_count,
            "regions": len(regions),
            "candidates": len(candidates),
            "matching_pairs": matching.cardinality,
            "coverage": (
                matching.cardinality * 2 / audit.triangle_count
                if audit.triangle_count
                else 1.0
            ),
            "solver_exact": matching.exact,
            "source_fingerprint_unchanged": unchanged,
            "surface_deviation_max": validation.surface_deviation.maximum,
            "timings_seconds": timings,
            "total_seconds": time.perf_counter() - started,
        }
    finally:
        if output is not None:
            bpy.data.objects.remove(output, do_unlink=True)
        if output_mesh is not None and output_mesh.users == 0:
            bpy.data.meshes.remove(output_mesh)
        source_mesh = source.data
        bpy.data.objects.remove(source, do_unlink=True)
        if source_mesh.users == 0:
            bpy.data.meshes.remove(source_mesh)


try:
    args = arguments()
    report = {
        "blender_version": bpy.app.version_string,
        "cases": [run_case(int(value)) for value in args.sizes.split(",") if value],
    }
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print("LCW_PHASE5_BENCHMARK_OK")
    print(encoded)
except Exception:
    traceback.print_exc()
    sys.exit(1)
