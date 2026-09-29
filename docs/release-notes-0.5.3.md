# LC Workflow Helper 0.5.3

This release adds CAD UV Preparation as a separate tool within the CAD Mesh Reconstruction panel.

## CAD UV Preparation

- Analyze selected mesh objects before generating UVs, then create a new UV map for each object and pack its islands into the 0-1 UV space.
- Keep broad connected surfaces continuous across smooth bends, while separating hole interiors and conservative geometric regions. Existing seams are used neither as input nor changed.
- Preserve existing UV maps, mesh geometry, and other attributes. Shared mesh data is made single-user before writing a new UV map so unselected objects remain unchanged.
- Isolate failures per object and clean up temporary unwrap data. The tool does not require the external Unwrap Me add-on or CAD-specific face-role metadata.

The generated layout is a starting point for manual UV cleanup, not a replacement for artistic review. The reference mesh `6x6_sasi_L.004` retained its two major connected surfaces in headless tests. Blender 4.5 and 5.2 integration tests, Python regression tests, and extension build/validation passed. The declared minimum remains Blender 4.2; an installed 4.2 runtime was not available for this release test.
