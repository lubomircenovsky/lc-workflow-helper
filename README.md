# LC Workflow helper

`LC Workflow helper` is a Blender 4.2 LTS Extension add-on focused on day-to-day production helpers for LC workflows.

The add-on groups tools into practical N-panel categories:

- `Shape Keys`
- `Materials`
- `Colors`
- `UV`
- `Mesh Utilities`
- `Workflow Presets`
- `Kalibra Tools`

## Current Scope

This first version converts the original standalone scripts into a single Blender Extension add-on with:

- modular operators instead of one monolithic script
- session-only panel inputs for per-tool parameters
- workflow presets stored in each `.blend` file
- color picker based vertex color tools using Blender 4.2 `color_attributes`
- file path inputs instead of hardcoded export paths

## Installation

### From a packaged `.zip`

1. Build the extension package.
2. In Blender 4.2, open `Edit > Preferences > Extensions`.
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

- Target Blender version: `4.2 LTS`
- Main UI location: `3D View > N-panel > LC Workflow`
- Project-specific tools remain isolated in `Kalibra Tools`
- Workflow presets are stored in the current `.blend` file via scene state

## Validation Status

Static validation completed:

- Python modules compile successfully
- add-on structure is ready for Blender Extension packaging

Runtime validation is still needed inside Blender 4.2 for:

- registration and panel rendering
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
  ui/
  utils/
  scripts/
```
