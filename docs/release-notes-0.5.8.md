# LC Workflow Helper 0.5.8

This release fixes Substance bakes (Bakers) that finished without producing any maps.

## Bakers (Substance)

- **Multi-material meshes bake again.** Each material of a mesh is now sent to the baker as its own part, as the Substance baker requires. Before, a collection such as one where a door frame has several materials could finish as SUCCEEDED with 0 files. Meshes with a single material bake the same way as before.
- **A bake is only reported as successful when it really is.** The result is now a failure when:
  - the baker writes an error to its log, even if it exits normally,
  - a mesh is skipped because it lacks the selected UV set (for example UV1),
  - no new or updated image appears in the output folder. Images left over from an earlier bake no longer count as success.
- The error message names the baker, the group and the cause, and the log contains the same text.
- An unexpected error during a bake now shows as a failed job with its message in the panel and the full trace in the log. Before, the panel only said "Bake did not start."

## Validation

- All 158 unit tests pass, and the new native test `tests/blender_substance_baker.py` passes 8/8 in Blender 5.2.1.
- Real Substance baker runs in Blender 5.2.1, outside the user scene:
  - a multi-material door export baked by object (2 maps), by material (7) and with one material excluded (5),
  - a single-material export baked 1 map,
  - a small AO bake succeeded in every output format (png, tif, jpg, exr, tga, bmp) and again into a folder that already held the map.
- Not yet checked: a full 4096 bake in the Blender UI, and the other baker types and high-poly/cage projection on real data.
- The extension ZIP was built and validated with the official Blender 5.2 `extension build/validate`, and an isolated install was tested.
