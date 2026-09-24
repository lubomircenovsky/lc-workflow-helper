"""Headless multi-process CAD batch, ordered results and pool-wide cancel."""

import json
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint
from LC_workflow_addon.cad_mesh_tool.rebuild import tessellation

try:
    from _bpy_restrict_state import RestrictBlend
except ImportError:
    from bpy_restrict_state import RestrictBlend


def source_object(name, defect=False):
    outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
    angles = np.arange(24) * math.tau / 24
    hole = .0065 * np.column_stack((np.cos(angles), np.sin(angles)))
    points, triangles = tessellation([outer, hole])
    count = len(points)
    vertices = [(x, y, z) for z in (0., .01) for x, y in points]
    faces = [list(reversed(face)) for face in triangles]
    faces += [[count + i for i in face] for face in triangles]
    for ring, reverse in ((range(4), False), (range(4, count), True)):
        ids = list(ring)
        for a, b in zip(ids, ids[1:] + ids[:1]):
            faces.append([b, a, a + count, b + count] if reverse else
                         [a, b, b + count, a + count])
    if defect:
        offset = len(vertices)
        vertices += [(.2, 0., 0.), (.2, 0., .01), (.215, 0., 0.),
                     (.2, .015, 0.), (.185, 0., 0.), (.2, -.015, 0.)]
        faces += [[offset + vi for vi in face] for face in (
            (0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3),
            (0, 4, 1), (0, 1, 5), (0, 5, 4), (1, 4, 5),
        )]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


with RestrictBlend():
    addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = "SELECTED"
    state.concurrent_workers = 4
    for name in ("circular_holes", "perimeter_loops", "arcs", "outer_cylinders",
                 "background_cleanup", "straight_walls"):
        setattr(state, name, name == "circular_holes")
    objects = [source_object(f"CAD Pool {index}", defect=index == 1) for index in range(4)]
    fingerprints = [fingerprint(obj) for obj in objects]
    with tempfile.TemporaryDirectory() as directory:
        count = len(state.results)
        batch = jobs.CADBatch(bpy.context, objects, Path(directory), preserve_nonmanifold=True)
        max_running = 0
        while batch.step():
            max_running = max(max_running, len(batch.running))
            time.sleep(.03)
        rows = list(state.results)[count:]
        assert max_running >= 3, max_running
        assert len(rows) == 4 and [row.source for row in rows] == objects
        assert [row.status for row in rows] == ["PASS", "REVIEW", "PASS", "PASS"]
        assert all(row.output is not None and row.elapsed_seconds > 0 for row in rows)
        assert all(fingerprint(obj) == before for obj, before in zip(objects, fingerprints))
        for row in rows:
            manifest = json.loads((Path(row.run_dir) / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["timings"]["attempts"]
        print("CAD_POOL_CONCURRENT_OK", max_running, [row.status for row in rows])
        retained = len(state.results)
        cancelled = jobs.CADBatch(bpy.context, objects, Path(directory), preserve_nonmanifold=True)
        for _ in range(3):
            assert cancelled.step()
        processes = [job["process"] for job in cancelled.running.values()]
        assert len(processes) == 3
        cancelled.cancel()
        assert not cancelled.running and not cancelled.step()
        assert all(process.poll() is not None for process in processes)
        assert len(state.results) == retained
        assert all(fingerprint(obj) == before for obj, before in zip(objects, fingerprints))
        print("CAD_POOL_CANCEL_OK", len(processes))
        state.concurrent_workers = 16
        issues = [(), ("Deliberately blocked source",), (), ()]
        mixed = jobs.CADBatch(bpy.context, objects, Path(directory),
                              preserve_nonmanifold=True, object_issues=issues)
        assert mixed.max_workers == 16
        while mixed.step():
            assert len(mixed.running) <= len(objects)
            time.sleep(.03)
        mixed_rows = list(state.results)[retained:]
        assert [row.status for row in mixed_rows] == ["PASS", "FAIL", "PASS", "PASS"]
        assert mixed_rows[1].stage == "preflight" and mixed_rows[1].output is None
        assert all(fingerprint(obj) == before for obj, before in zip(objects, fingerprints))
        print("CAD_POOL_ISOLATED_FAILURE_OK", [row.status for row in mixed_rows])
        input_collection = bpy.data.collections.new("CAD Pool Input")
        output_collection = bpy.data.collections.new("CAD Pool Output")
        bpy.context.scene.collection.children.link(input_collection)
        bpy.context.scene.collection.children.link(output_collection)
        for obj in objects[:2]:
            input_collection.objects.link(obj)
        state.mode = "COLLECTION"
        state.input_collection = input_collection
        state.output_collection = output_collection
        state.concurrent_workers = 2
        collection_batch = jobs.CADBatch(bpy.context, objects[:2], Path(directory),
                                         preserve_nonmanifold=True)
        while collection_batch.step():
            time.sleep(.03)
        collection_rows = list(state.results)[collection_batch.row_offset:]
        assert [row.status for row in collection_rows] == ["PASS", "REVIEW"]
        branches = list(output_collection.children)
        assert len(branches) == 1
        assert collection_rows[0].output.name in branches[0].children["PASS"].objects
        assert collection_rows[1].output.name in branches[0].children["REVIEW"].objects
        print("CAD_POOL_COLLECTION_ROUTING_OK", [row.status for row in collection_rows])
finally:
    with RestrictBlend():
        addon.unregister()
