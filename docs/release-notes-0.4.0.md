# LC Workflow Helper 0.4.0

Version 0.4.0 adds deterministic offline quad reconstruction and completes the recent mesh workflow improvements.

## Highlights

- Added collection-based Quad Reconstruction for triangulated and mixed meshes.
- Added Analyze, Reconstruct, Validate Outputs, cancellation, guarded cleanup and structured Text/JSON reports.
- Added Strict, Balanced, Aggressive and Analyze Only profiles.
- Added exact blossom matching for bounded regions and an explicitly inexact deterministic fallback for large regions.
- Added confidence scoring, unresolved-face diagnostics, attribute-relaxation flags and problem-face selection.
- Added source fingerprints, independent output datablocks, per-object rollback and source-preservation validation.
- Added sampled surface-deviation and temporary Catmull-Clark validation.
- Added optional external-process candidate generation without worker access to Blender data.
- Optimized fragmented production meshes by removing quadratic region and candidate scans.
- Preserved pre-existing degenerate and duplicate faces as hard barriers instead of rejecting the complete object.
- Added file-local workflow presets, UV seam rebuilding on batch UV switches and reviewed batch mesh-data relinking.

## Performance Evidence

- A 27,624-triangle production object completes in approximately 16-18 seconds and preserves its source fingerprint.
- A 107,980-triangle production object with 97 pre-existing unsafe faces completes in approximately 73 seconds with two workers; unsafe faces and the source fingerprint remain unchanged.
- The reproducible planar 100k-triangle benchmark completes in approximately 22.5 seconds in Blender 4.5.8 and 5.2.0 LTS.

## Compatibility

- Minimum supported Blender version remains 4.2.
- Automated runtime fixtures pass in Blender 4.5.8 and Blender 5.2.0 LTS.
- No network service, LLM or new runtime Python dependency is required.

## Known Limitations

- Seed + Augment is not mathematically exact on general odd-cycle graphs and is reported as such.
- External workers help only on sufficiently large inputs and increase peak memory usage.
- Pre-existing unsafe faces remain unresolved and can cause Catmull-Clark validation warnings.
