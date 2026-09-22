# LC Workflow Helper 0.5.0

Version 0.5.0 adds the CAD Mesh Reconstruction workflow and the related production safeguards.

## CAD Mesh Reconstruction

- Added a dedicated CAD Mesh Reconstruction panel with Collection and Selected Objects workflows.
- Added batch Analyze, Reconstruct, Cancel, Retry, source selection and run-folder access.
- Added PASS, REVIEW and FAIL result handling with preserved diagnostics and per-object failure isolation.
- Added collection-aware output placement and Selected Objects output placement beside the source hierarchy.
- Added immutable source preparation, external Blender worker execution and checkpoint-free scene import.
- Added scoped CAD status wire overlay that affects only generated CAD results in the active viewport.
- Added collapsible Input, Reconstruction Options, Run and Results UI sections.
- Added manual normal-limit controls with explicit shading-risk acknowledgement.
- Added validation for source fingerprints, output integrity, geometry status and worker artifacts.
- Preserved source transforms and parent hierarchies, including translated and rotated parents, during result import.

## Compatibility

- Minimum supported Blender version remains 4.2.
- The addon remains offline and does not use LLMs, network services or remote APIs.
- Existing workflow presets, baker profiles, UV seam tools, mesh relink tools, quad reconstruction and vertex-color palette remain compatible.
