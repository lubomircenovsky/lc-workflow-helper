# LC Workflow Helper 0.5.6

This release helps you repair CAD sources that block reconstruction.

## CAD Reconstruction

- **Select Problem Areas** on a failed result opens the source in Edit Mode and selects the geometry that caused the failure, so you can fix it by hand:
  - **Intersecting source surfaces:** exactly the faces whose triangles cross another triangle are selected. They come from the diagnostics stored in the run folder and are mapped back to the source object when Separate Solids was used. If the source changed since the run, the stored indices no longer apply and the tool asks you to reconstruct again.
  - **Open or non-manifold topology:** open, wire and non-manifold edges and inconsistent normals are selected.
- Only the selection changes; the mesh is never modified.

## Tests

- Temporary test folders are now created in the system temp directory instead of the parent of the add-on folder.

## Validation

- All 109 unit tests pass.
- Native Blender 5.2.1 tests pass for the new tool (intersections, changed-source refusal, open topology) and for the panel, UI, protected-region and reconstruction regressions.
- On a production source with 1244 intersecting triangle pairs, the stored diagnostics map to 894 source faces in about 0.3 s.
- The extension ZIP was built and validated with the official Blender 5.2 `extension build/validate`, and an isolated install was tested.
