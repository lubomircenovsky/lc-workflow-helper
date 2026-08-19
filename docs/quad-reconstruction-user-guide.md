# Quad Reconstruction User Guide

Quad Reconstruction estimates likely quad pairs in triangulated or mixed meshes. It is deterministic, offline, and never applies source modifiers or edits the source mesh datablock.

## Basic Workflow

1. Open `3D View > N-panel > LC Workflow > Quad Reconstruction`.
2. Choose an `Input Collection`. Child collections are processed recursively.
3. Optionally choose an `Output Collection`. Otherwise the add-on creates `AIQ Reconstruction Output`.
4. Choose a profile and solver.
5. Run `Analyze` first for unfamiliar assets.
6. Run `Reconstruct` and monitor object/region progress.
7. Review confidence, unresolved triangles, relaxations and warnings in Results.
8. Use `Select Problem Faces`, `Focus Output`, or `Export Report JSON` as needed.

`Esc` or `Cancel Active Run` requests cooperative cancellation. The active generated run is removed at the next safe job boundary.

## Profiles

- `Strict`: UV, seam, sharp, material and unsupported attribute conflicts are hard barriers.
- `Balanced`: materials remain protected; supported UV, seam and sharp relaxations are reported.
- `Aggressive`: maximizes hard-valid coverage while marking every allowed relaxation.
- `Analyze Only`: creates reports but no mesh outputs.

## Solvers

- `Auto`: exact blossom up to the component limit, deterministic fallback above it.
- `Exact Blossom`: mathematically exact only within the configured limit; oversized regions remain unresolved.
- `Seed + Augment`: dependency-free fallback. It does not guarantee maximum matching on every odd-cycle graph.
- `Native Baseline`: comparison/seed behavior, not proof of correct topology.

## Reading Results

Confidence combines coverage, cost, warp, relaxations, solver exactness, hypothesis margin, surface deviation and subdivision validation. A validation error always produces `FAILED`.

Diagnostic face attributes include `AIQ_UnresolvedTriangle`, `AIQ_LowConfidence`, relaxation flags, high warp and high cost. Existing quads and ngons are preserved by default.

Pre-existing degenerate or duplicate faces no longer block the complete object. They are preserved unchanged, isolated as hard reconstruction barriers and reported as unresolved. A changed or newly created unsafe face remains a hard validation failure. Catmull-Clark failure caused by an exactly preserved unsafe source face is reported as a warning and lowers confidence.

## Performance

`Parallel Core Processing` uses isolated Blender-Python worker processes for pure candidate generation. Blender mesh access, BMesh changes, matching application and validation remain on the main thread because Blender data is not thread-safe.

The default threshold is 50,000 processable triangles. Below it, the optimized serial path is normally faster because workers must serialize the immutable snapshot and start separate Python processes. Two workers are a conservative default; additional workers increase peak memory because each receives its own snapshot copy.

## Safety and Cleanup

Generated objects and meshes are independent copies. `Clear Generated Results` deletes only data carrying the matching internal run ID. Blender Undo covers operators, but keeping the exported JSON/Text report is recommended before manual edits to a generated result.

The add-on never saves the `.blend` file automatically. To abandon all local feature changes at repository level, see the rollback section in the developer guide.

## Known Limitations

- Geometry can be ambiguous; unresolved triangles are intentional in conservative profiles.
- Seed + Augment is not mathematically exact on general graphs.
- Snapshot and audit of one object remain main-thread work. Candidate generation can use external workers above the configured threshold; matching, application and validation still yield only at safe stage or region boundaries.
- Surface deviation uses deterministic bidirectional samples, not an exhaustive continuous Hausdorff proof.
- A clean Catmull-Clark test does not imply that Blender `Un-Subdivide` can recover the source topology.
- Custom corner/face data may require explicit relaxation outside Strict mode.
