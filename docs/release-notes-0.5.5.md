# LC Workflow Helper 0.5.5

This release is a large update to CAD mesh reconstruction: automatic variant selection, bend reconstruction, protected regions, collinear vertex cleanup and much faster processing. It also adds a GN Library asset and a material slot fix.

**Blender 5.2 or newer is now required** for the whole extension (`blender_version_min = 5.2.0`). Earlier releases declared Blender 4.2.

## CAD Reconstruction – workflow

- **Auto** and **Power user** modes. Auto compares up to four validated variants per solid and keeps the best one. Power user exposes the individual operations.
- **Objective** for Auto: **Lightweight** (default) keeps the fewest triangles; **Editable** keeps more reconstructed regions and support loops around holes.
- **Protected Regions** (Edit Mode): mark faces that must stay exactly as authored. Protected faces are locked and validated, and the result meshes carry the `cad_protected` attribute, so a result used as the next input stays protected.
- **Max. Worker Time (min)** (10 minutes by default, `0` = unlimited) for Auto, Power user and Analyze. On timeout the best fully validated candidate is kept as REVIEW and the queue continues.
- **Analyze** screens each intersection-free solid separately and summarises the recommended profile.
- **Hole Detail** and an independent **Hole Deviation (mm)** for circular holes. **Separate Solids** reconstructs independent shells separately. Source-intersection diagnostics are included.

## CAD Reconstruction – geometry

- **Bends**: cylindrical bends with skew-cut rims and with measured end contours are now detected and reconstructed. Unsupported shapes fall back to the established regions and are reported as REVIEW.
- **Perimeter Loops**: simpler square supports with fewer vertices. In Power user a positive **Clearance (mm)** is fixed and never silently changed. In Auto it is the preferred clearance: if a support does not fit, smaller clearances are tried (largest first) before a direct join.
- **Collinear crease vertices**: with Background Cleanup on, a final validated pass removes vertices that only split a straight crease (typically plane vertices pinned onto a bend rim by CAD tessellation). The surface does not move. Perimeter rings, protected and non-manifold faces and UV seams are never touched. Example: 1528 → 1358 triangles on a user test body.
- Skipped (kept-as-authored) features now block only changes to their own vertices, which unblocks holes next to them.
- Background Cleanup keeps a vertex map, so protected faces are no longer lost when Blender dissolves interior vertices. Lost authored sharp edges are informational only.

## Performance and robustness

- Auto runs independent solids and variants in parallel worker processes. The Collection 2 reference Auto batch went from 571 s to about 77 s with identical results.
- Faster exact geometry checks: vectorized intersection and support-ring tests, float64 spatial bounds for exact distance checks, batched least squares. The results are bit-identical.
- Progress survives interruption. Batches keep running through transient Windows report-file locks. Cancelling or timing out stops the whole worker process tree.
- Review warnings are retained in Auto result summaries.

## Other changes

- GN Library: added the `UV_scale` asset.
- Remove Unused Material Slots skips meshes without material slots in batch mode.

## Validation

- All 103 unit tests pass (`python -m unittest discover -s tests`).
- Native Blender 5.2.1 suite: 33 PASS / 5 SKIP (external production data not available) / 0 FAIL.
- Reference Collection 2 regression: all 27 bodies keep their statuses, loops and reductions. Triangles 64 714 → 63 458 (Power user) and 57 656 → 56 398 (Auto).
- The extension ZIP was built and validated with the official Blender 5.2 `extension build/validate`, and an isolated install was tested.

Geometric topology, intersection and surface-deviation checks remain mandatory, and PASS or REVIEW is not proof that every detail was recognised. The source object is never modified or saved automatically.
