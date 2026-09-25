# LC Workflow Helper 0.5.2

This release improves CAD mesh reconstruction and review without changing the source mesh.

## CAD Reconstruction

- Source custom split normals are ignored during reconstruction. The generated mesh uses geometry-based shading, so authored custom normals no longer block otherwise safe perimeter work.
- Existing sharp edges are retained where possible. If a geometrically valid reconstruction removes a sharp edge, the result is marked **PARTIAL / REVIEW**, not FAIL. The report lists affected source vertex pairs, and mappable areas receive a `CAD_Review_SharpEdges` vertex group.
- Added **Clearance (mm)** beside Perimeter Loops for circular openings. `0` preserves automatic sizing; a positive value sets the preferred nominal gap. If it does not fit, the tool tries smaller safe gaps. The report records requested and selected values.
- Reorganized the Reconstruction Options panel: Circular Holes spans its own row; Perimeter Loops and Clearance share a row.
- Made skipped-feature shading diagnostics more readable in Results and reports.

Geometric topology, intersection and surface-deviation checks remain mandatory. The original object is never modified or saved automatically. The extension still declares Blender 4.2 as its minimum; this release was regression-tested in Blender 4.5 and 5.2.
