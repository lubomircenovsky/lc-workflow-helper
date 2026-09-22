# CAD Mesh Reconstruction

This panel wraps the bundled CAD Mesh Tool 0.4.1 method A. It does not use Geometry Nodes, a network service, or an LLM. The original object and its mesh are read-only. The addon never saves the current `.blend` automatically.

Choose **Collection** to process every distinct mesh in the input collection and its children. Results go below the chosen output collection, into a branch for that input collection and shared `PASS`, `REVIEW`, and `FAIL` status collections. Choose **Selected Objects** to process the selected meshes and link each result beside its source. Previous results are kept on retry. Set a persistent Run Folder before starting; for an unsaved `.blend`, use an absolute path.

**Analyze** checks basic eligibility and warns about boundaries, non-manifold edges, degenerates, and negative scale, but cannot predict every reconstruction failure. **Reconstruct** prepares an immutable input for each source, runs a separate background Blender worker, and imports only the visible final or review mesh. Checkpoints remain in the worker artifact and never appear in the scene. Cancel stops the active worker; previously completed outputs remain. Each result shows its run folder and failure stage/reason. The folder contains `worker.log`, `failure.json` when applicable, and detailed validation files.

The worker records the result's world transform in its manifest. Import restores it before parenting so generated geometry remains in the same scene location as its source, including translated/rotated parent hierarchies. An artifact without a valid transform is rejected rather than silently placed at the world origin.

Green `PASS` means geometry validation passed, **not** that every CAD detail was identified. Its coverage still requires visual review. Yellow `REVIEW` is a failed validation with an inspectable candidate. Red `FAIL` means no trustworthy output mesh was imported; select the source and inspect its report. Neither yellow nor red is a production-approved result.

Imported `PASS` and `REVIEW` results receive object colors. **Show** enables a colored wireframe overlay only on generated CAD results in the active viewport; **Hide** removes it. Neither button changes Solid/Wireframe shading modes or colors unrelated objects. The overlay is viewport-local and is cleared when the addon unregisters or another `.blend` loads.

**Retry** starts a new run. The default normal check uses Blender-topology roundtrip calibration. Advanced Manual Normal Limit accepts any positive finite angle in degrees after risk acknowledgement. Above 0.05 degrees, shading may visibly change. This overrides only the straight-wall corner-normal limit; topology, intersection, deviation, and other geometry checks remain enabled. A higher limit cannot guarantee success. The chosen value is stored in the run profile and report.

## Development notes

The `cad_mesh_tool` package is a vendored copy of the user's local CAD Mesh Tool 0.4.1 source (`E:\WORK\00_VIBE\Blender_geo_nodes\cad_mesh_tool`), with only these integration changes: optional checkpoint-free `apply_result`, a manual normal-limit option, failure stage metadata, and normal-limit reporting. Keep the bundled worker and API from the same revision: `code_hash()` binds preparation to worker/import. The addon module `cad_reconstruction` owns Scene settings, modal orchestration, placement and UI. The worker executes in a separate Blender process, never a Python thread accessing live `bpy` data.

Run `tests/blender_cad_reconstruction.py` in headless Blender and verify the extension build before distributing. Worker run artifacts live outside the extension directory. Rollback is to remove this module and bundled package and restore their registration/build entries; existing source meshes need no migration.
