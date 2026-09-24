"""Perimeter and planar cleanup must not depend on curve decimation."""

import json
import math
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import prepare_selected
from cad_mesh_tool.detect import discover
from cad_mesh_tool.mesh_io import ROLES, capture, fingerprint
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.rebuild import tessellation
from cad_mesh_tool.worker import main as run_worker


outer = np.array([[-.05, -.05], [.05, -.05], [.05, .05], [-.05, .05]])
angles = np.arange(32) * math.tau / 32
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
cube_start = len(vertices)
vertices += [(x, y, z) for z in (0., .01) for x, y in
             ((.15, -.02), (.19, -.02), (.19, .02), (.15, .02))]
cube_face_start = len(faces)
for quad in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
    faces.extend([[cube_start + quad[i] for i in ids]
                  for ids in ((0, 1, 2), (0, 2, 3))])
mesh = bpy.data.meshes.new("CAD Preserve Source")
mesh.from_pydata(vertices, [], faces)
mesh.update()
roles = mesh.attributes.new("cad_role", "INT", "FACE")
roles.data.foreach_set("value", [ROLES.index("PROTECTED_OTHER")] * len(faces))
obj = bpy.data.objects.new("CAD Preserve Source", mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
source_hash = fingerprint(obj)
options = {name: False for name in DEFAULTS}
options["circular_holes"] = True
options["perimeter_loops"] = True
options["background_cleanup"] = True

with tempfile.TemporaryDirectory() as directory:
    for label, epsilon_mm, preserve in (("no_reduction", .001, True),
                                        ("preserve", .4, True)):
        plan = discover(source["vertices"], source["faces"], epsilon_mm / 1000)
        holes = [feature for feature in plan["features"] if feature["category"] == "circular_hole"]
        assert len(holes) == 1
        if label == "no_reduction":
            assert holes[0]["segments"] == holes[0]["segments_before"]
        else:
            assert holes[0]["segments"] < holes[0]["segments_before"]
        run = Path(directory) / label
        prepare_selected(run, obj=obj, epsilon_mm=epsilon_mm, operations=options,
                         preserve_curve_segmentation=preserve)
        run_worker(run)
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        candidate = json.loads((run / "candidate.json").read_text(encoding="utf-8"))
        cleanup = json.loads((run / "cleanup.json").read_text(encoding="utf-8"))
        assert manifest["geometry_status"] == "PASS"
        assert manifest["preserve_curve_segmentation"] == preserve
        assert any(p["layout"] != "direct_join" for p in candidate["perimeters"])
        assert cleanup["dissolved_edges"] > 0
        if preserve:
            mapped_cube_face = tuple(candidate["source_to_candidate"][vi]
                                     for vi in source["faces"][cube_face_start])
            assert candidate["roles"][candidate["faces"].index(list(mapped_cube_face))] == "BACKGROUND_PLANE"
            mapping = candidate["source_to_candidate"]
            candidate_faces = {tuple(face) for face in candidate["faces"]}
            for fi in holes[0]["faces"]:
                assert tuple(mapping[vi] for vi in source["faces"][fi]) in candidate_faces
            for vi in holes[0]["vertices"]:
                assert np.array_equal(np.asarray(candidate["vertices"][mapping[vi]]),
                                      np.asarray(source["vertices"][vi]))
        assert fingerprint(obj) == source_hash
        print("CAD_PRESERVE_LAYOUT_OK", label, len(candidate["perimeters"]),
              cleanup["dissolved_edges"])

    background_only = {name: name == "background_cleanup" for name in DEFAULTS}
    run = Path(directory) / "background_only"
    prepare_selected(run, obj=obj, operations=background_only,
                     preserve_curve_segmentation=True)
    run_worker(run)
    cleanup = json.loads((run / "cleanup.json").read_text(encoding="utf-8"))
    assert cleanup["dissolved_edges"] > 0
    assert fingerprint(obj) == source_hash
    print("CAD_BACKGROUND_ONLY_OK", cleanup["dissolved_edges"])

    disabled = {name: False for name in DEFAULTS}
    try:
        prepare_selected(Path(directory) / "disabled", obj=obj, operations=disabled,
                         preserve_curve_segmentation=True)
    except ValueError as exc:
        assert "Enable at least one" in str(exc)
    else:
        raise AssertionError("Preserve option must not count as an operation")
