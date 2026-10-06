# LC Workflow helper

`LC Workflow helper` is a Blender 5.2 LTS Extension add-on focused on day-to-day production helpers for LC workflows. Blender 5.2.0 is the minimum supported version.

The add-on groups tools into practical N-panel categories:

- `Shape Keys`
- `Materials`
- `Colors`
- `UV`
- `Mesh Utilities`
- `Workflow Presets`
- `Kalibra Tools`
- `Quad Reconstruction`
- `CAD Mesh Reconstruction`
- `GN Library`

## Current Scope

The extension provides:

- modular operators instead of one monolithic script
- session-only panel inputs for per-tool parameters
- workflow presets stored in each `.blend` file
- color picker based vertex color tools using `color_attributes`
- file path inputs instead of hardcoded export paths
- deterministic batch quad reconstruction for triangulated and mixed meshes
- bundled Geometry Nodes groups that can be appended to the current `.blend` file

The GN Library initially includes `GN_Screw_Replace_By_Geometry`. The source collection and replacement object are assigned in the Geometry Nodes modifier after insertion.

## Installation

### From a packaged `.zip`

1. Build the extension package.
2. In Blender 5.2 LTS, open `Edit > Preferences > Extensions`.
3. Use `Install from Disk`.
4. Select the generated `.zip` package.
5. Enable `LC Workflow helper`.

### From source during development

1. Copy or symlink this folder into your Blender extensions development area.
2. Keep `blender_manifest.toml` in the add-on root.
3. Reload Blender or re-scan Extensions after changes.

## Packaging

The repository includes a PowerShell helper:

```powershell
.\scripts\build_extension.ps1
```

Behavior:

- prefers the official Blender CLI build command when `blender.exe` is available
- falls back to creating a local release `.zip` from the add-on contents
- writes the output to `dist\`

## Workflow Presets

Workflow presets are saved with the current `.blend` file. If legacy global presets still exist in Add-on Preferences, the N-panel shows an `Import Missing Legacy Presets` button to copy them into the open scene without duplicating presets that already exist there.

Manual persistence check:

1. Create a workflow preset in the N-panel.
2. Add at least one action and edit one visible action parameter.
3. Save the `.blend` file.
4. Close Blender and reopen the same `.blend` file.
5. Confirm the preset, action list, and edited action parameter are still present.
6. Run the preset once to confirm the saved action chain is executable.

## Development Notes

- Target Blender version: `5.2 LTS` (minimum 5.2.0)
- Main UI location: `3D View > N-panel > LC Workflow`
- Project-specific tools remain isolated in `Kalibra Tools`
- Workflow presets are stored in the current `.blend` file via scene state
- Quad Reconstruction user, developer and benchmark documentation is available in `docs/`

## Quad Reconstruction

The add-on includes deterministic offline reconstruction of likely quad topology for triangulated and mixed mesh collections. It creates independent output meshes, preserves hard boundaries, reports confidence and unresolved faces, and supports exact blossom matching for bounded regions plus a deterministic fallback for large regions.

See:

- `docs/quad-reconstruction-user-guide.md`
- `docs/quad-reconstruction-developer-guide.md`
- `docs/quad-reconstruction-benchmarks.md`
- `quad_reconstruction/matching/DECISION.md`

## CAD Mesh Reconstruction

Simplifies triangulated CAD exports (mainly sheet-metal machine cladding) into lighter, editable meshes: circular holes, arcs and outer cylinders are re-sampled analytically, flat areas become n-gons, and every candidate is validated against the untouched source (topology, intersections, sampled deviation). Work runs in separate background Blender processes; the source object is never modified and nothing is saved automatically.

- **Auto** compares up to four validated variants per solid. Objective **Lightweight** keeps the fewest triangles; **Editable** keeps more reconstructed regions and support loops around holes.
- **Power user** exposes the individual operations.
- **Protected Regions** (Edit Mode) marks faces that must stay exactly as authored.
- **UV Preparation** builds a packed UV map for the selected meshes.

Details, guarantees and limits: `docs/cad-mesh-reconstruction.md`.

## Validation Status

Automated validation completed:

- Python modules compile successfully
- pure-core unit tests pass
- registration, reconstruction, safety and validation fixtures pass in Blender 5.2.1 LTS
- the extension manifest and packaged ZIP validate successfully

Manual UI validation remains useful for:

- operator context edge cases
- workflow preset execution chains and `.blend` persistence
- project-specific `Kalibra Tools`

## Repository Layout

```text
LC_workflow_addon/
  __init__.py
  blender_manifest.toml
  constants.py
  preferences.py
  properties.py
  operators/
  quad_reconstruction/
  docs/
  ui/
  utils/
  scripts/
```
