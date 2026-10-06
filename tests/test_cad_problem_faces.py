"""Stored intersection pairs map to polygons of the original source mesh."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_reconstruction.problem_faces import intersection_polygons, load_intersections, triangle_polygons

# Two quads (0, 1) and a triangle (2); quads are split into two triangles each.
FULL = dict(
    faces=[[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10]],
    triangles=[[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [8, 9, 10]],
    triangle_polygons=[0, 0, 1, 1, 2],
)


class ProblemFacesTest(unittest.TestCase):
    def test_explicit_triangle_map(self):
        validation = {"intersections": [{"a": 1, "b": 4, "type": "proper_crossing"}]}
        self.assertEqual(intersection_polygons(FULL, validation), ([0, 2], 1))

    def test_separate_solid_maps_back_to_source_polygons(self):
        # Sub-mesh of polygons 5 and 9: no triangle_polygons, vertices renumbered.
        solid = dict(
            faces=[[0, 1, 2, 3], [2, 1, 4]],
            triangles=[[0, 1, 2], [0, 2, 3], [2, 1, 4]],
            source_face_ids=[5, 9],
        )
        self.assertEqual(triangle_polygons(solid), [[0], [0], [1]])
        validation = {"intersections": [{"a": 0, "b": 2}, {"a": 1, "b": 2}]}
        self.assertEqual(intersection_polygons(solid, validation), ([5, 9], 2))

    def test_no_pairs_selects_nothing(self):
        self.assertEqual(intersection_polygons(FULL, {"intersections": []}), ([], 0))

    def test_invalid_triangle_index_is_rejected(self):
        with self.assertRaises(ValueError):
            intersection_polygons(FULL, {"intersections": [{"a": 0, "b": 99}]})

    def test_triangle_outside_every_polygon_is_rejected(self):
        broken = dict(faces=[[0, 1, 2]], triangles=[[0, 1, 3]])
        with self.assertRaises(ValueError):
            triangle_polygons(broken)

    def test_load_from_run_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "source.json").write_text(json.dumps(dict(FULL, source_hash="h")), encoding="utf-8")
            (run / "validation_source.json").write_text(
                json.dumps({"intersections": [{"a": 2, "b": 3}]}), encoding="utf-8")
            self.assertEqual(load_intersections(run), ("h", [1], 1))
            (run / "validation_source.json").unlink()
            with self.assertRaises(FileNotFoundError):
                load_intersections(run)


if __name__ == "__main__":
    unittest.main()
