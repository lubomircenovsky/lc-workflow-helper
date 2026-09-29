"""Headless UV preparation: isolation, batching, and optional reference sample."""

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import uv_prep


def uv_values(mesh, layer):
    return tuple(tuple(item.uv) for item in layer.data)


def snapshot(mesh):
    return (
        tuple(tuple(vertex.co) for vertex in mesh.vertices),
        tuple(tuple(poly.vertices) for poly in mesh.polygons),
        tuple(edge.use_seam for edge in mesh.edges),
        tuple((layer.name, uv_values(mesh, layer)) for layer in mesh.uv_layers),
    )


def island_sizes(mesh, layer):
    parent = list(range(len(mesh.polygons)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    edges = defaultdict(list)
    for poly in mesh.polygons:
        loop_indices = list(poly.loop_indices)
        for offset, loop_index in enumerate(loop_indices):
            following = loop_indices[(offset + 1) % len(loop_indices)]
            a = mesh.loops[loop_index].vertex_index
            b = mesh.loops[following].vertex_index
            edges[mesh.loops[loop_index].edge_index].append(
                (poly.index, {a: tuple(layer.data[loop_index].uv),
                              b: tuple(layer.data[following].uv)}))
    for records in edges.values():
        if len(records) != 2:
            continue
        (a, first), (b, second) = records
        if all(sum((first[vertex][axis] - second[vertex][axis]) ** 2
                   for axis in (0, 1)) <= 1e-12 for vertex in first):
            a, b = find(a), find(b)
            if a != b:
                parent[b] = a
    return sorted(Counter(find(index) for index in range(len(parent))).values(), reverse=True)


def overlap_count(mesh, layer):
    def twice_area(points):
        return sum(a[0] * b[1] - a[1] * b[0]
                   for a, b in zip(points, points[1:] + points[:1]))

    def intersection_area(subject, clip):
        direction = 1 if twice_area(clip) >= 0 else -1
        for a, b in zip(clip, clip[1:] + clip[:1]):
            def side(point):
                return direction * ((b[0] - a[0]) * (point[1] - a[1])
                                    - (b[1] - a[1]) * (point[0] - a[0]))
            result = []
            if not subject:
                return 0.0
            for start, end in zip(subject, subject[1:] + subject[:1]):
                first, second = side(start), side(end)
                if (first >= 0) != (second >= 0):
                    factor = first / (first - second)
                    result.append((start[0] + factor * (end[0] - start[0]),
                                   start[1] + factor * (end[1] - start[1])))
                if second >= 0:
                    result.append(end)
            subject = result
        return abs(twice_area(subject)) * .5 if subject else 0.0

    mesh.calc_loop_triangles()
    triangles = [tuple(tuple(layer.data[index].uv) for index in tri.loops)
                 for tri in mesh.loop_triangles]
    bins = defaultdict(list)
    overlaps = set()
    cells = 64
    for index, points in enumerate(triangles):
        minimum = [min(point[axis] for point in points) for axis in (0, 1)]
        maximum = [max(point[axis] for point in points) for axis in (0, 1)]
        for x in range(max(0, int(minimum[0] * cells)), min(cells - 1, int(maximum[0] * cells)) + 1):
            for y in range(max(0, int(minimum[1] * cells)), min(cells - 1, int(maximum[1] * cells)) + 1):
                for other in bins[(x, y)]:
                    pair = (other, index)
                    if pair not in overlaps and intersection_area(list(triangles[other]), list(points)) > 1e-9:
                        overlaps.add(pair)
                bins[(x, y)].append(index)
    return len(overlaps)


def run_object(obj):
    for item in bpy.context.selected_objects:
        item.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    state = bpy.context.scene.lcw_cad_reconstruction
    state.uv_prep_map_name = "LCW_CAD_UV"
    state.uv_prep_margin = 0.005
    before = snapshot(obj.data)
    before_sync = bpy.context.scene.tool_settings.use_uv_select_sync
    before_render = next((layer.name for layer in obj.data.uv_layers
                          if layer.active_render), None)
    assert bpy.ops.lcw.cad_analyze_uv() == {"FINISHED"}
    assert snapshot(obj.data) == before
    result = bpy.ops.lcw.cad_prepare_uv()
    assert result == {"FINISHED"}, (obj.name, result, state.uv_prep_summary)
    assert snapshot(obj.data)[:3] == before[:3]
    assert snapshot(obj.data)[3][:-1] == before[3]
    assert obj.data.uv_layers.active.name.startswith("LCW_CAD_UV")
    assert len(obj.data.uv_layers) == len(before[3]) + 1
    assert bpy.context.scene.tool_settings.use_uv_select_sync == before_sync
    if before_render is not None:
        assert obj.data.uv_layers[before_render].active_render
    values = uv_values(obj.data, obj.data.uv_layers.active)
    assert all(math.isfinite(value) and -1e-5 <= value <= 1.00001
               for pair in values for value in pair)
    assert bpy.context.view_layer.objects.active == obj and obj.select_get()
    sizes = island_sizes(obj.data, obj.data.uv_layers.active)
    print("CAD_UV_OBJECT_OK", obj.name, len(obj.data.polygons), len(values),
          "islands", len(sizes), "largest", sizes[:2],
          "UV triangle overlaps", overlap_count(obj.data, obj.data.uv_layers.active))


addon.register()
try:
    sample = bpy.data.objects.get("6x6_sasi_L.004")
    if sample is not None:
        run_object(sample)
        print("CAD_UV_REFERENCE_OK")
    else:
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.object
        old_mesh = cube.data
        other = cube.copy()
        bpy.context.scene.collection.objects.link(other)
        for item in bpy.context.selected_objects:
            item.select_set(False)
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        before = snapshot(other.data)
        run_object(cube)
        assert cube.data != old_mesh
        assert other.data == old_mesh
        assert snapshot(other.data) == before
        print("CAD_UV_SHARED_MESH_OK")

        segments = 12
        vertices = [
            (radius * math.cos(2 * math.pi * i / segments),
             radius * math.sin(2 * math.pi * i / segments), float(z))
            for radius, z in ((2, 1), (1, 1), (1, 0), (2, 0))
            for i in range(segments)
        ]
        faces = []
        for i in range(segments):
            following = (i + 1) % segments
            faces.extend((
                (i, following, following + segments, i + segments),
                (i + segments, following + segments,
                 following + 2 * segments, i + 2 * segments),
                (i + 2 * segments, following + 2 * segments,
                 following + 3 * segments, i + 3 * segments),
                (i + 3 * segments, following + 3 * segments, following, i),
            ))
        tube_mesh = bpy.data.meshes.new("Sheet With Round Opening")
        tube_mesh.from_pydata(vertices, [], faces)
        tube_mesh.update()
        tube = bpy.data.objects.new("Sheet With Round Opening", tube_mesh)
        bpy.context.scene.collection.objects.link(tube)
        run_object(tube)
        tube_islands = island_sizes(tube.data, tube.data.uv_layers.active)
        assert len(tube_islands) == 4, tube_islands
        assert overlap_count(tube.data, tube.data.uv_layers.active) == 0
        print("CAD_UV_ROUND_HOLE_OK", tube_islands)

        bad = bpy.data.objects.new("Empty CAD Mesh", bpy.data.meshes.new("Empty CAD Mesh"))
        bpy.context.scene.collection.objects.link(bad)
        for item in bpy.context.selected_objects:
            item.select_set(False)
        bad.select_set(True)
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        old_count = len(cube.data.uv_layers)
        assert bpy.ops.lcw.cad_prepare_uv() == {"FINISHED"}
        assert len(cube.data.uv_layers) == old_count + 1
        assert not bad.data.uv_layers
        assert "1 skipped" in bpy.context.scene.lcw_cad_reconstruction.uv_prep_summary
        print("CAD_UV_BATCH_FAILURE_ISOLATION_OK")

        for item in bpy.context.selected_objects:
            item.select_set(False)
        cube.select_set(True)
        bpy.context.view_layer.objects.active = cube
        before_failure = snapshot(cube.data)
        before_sync = bpy.context.scene.tool_settings.use_uv_select_sync
        original_validator = uv_prep._validate_working_uv
        def injected_failure(*_args):
            raise ValueError("Injected UV validation failure")
        try:
            uv_prep._validate_working_uv = injected_failure
            assert bpy.ops.lcw.cad_prepare_uv() == {"CANCELLED"}
        finally:
            uv_prep._validate_working_uv = original_validator
        assert snapshot(cube.data) == before_failure
        assert bpy.context.scene.tool_settings.use_uv_select_sync == before_sync
        assert bpy.context.view_layer.objects.active == cube and cube.select_get()
        assert not any(obj.name.startswith("LCW UV Prep Temporary") for obj in bpy.data.objects)
        print("CAD_UV_ROLLBACK_OK")
finally:
    addon.unregister()
