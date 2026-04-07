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
- global workflow preset storage in add-on preferences
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

## Development Notes

- Target Blender version: `4.2 LTS`
- Main UI location: `3D View > N-panel > LC Workflow`
- Project-specific tools remain isolated in `Kalibra Tools`
- Workflow presets are stored globally in Add-on Preferences

## Validation Status

Static validation completed:

- Python modules compile successfully
- add-on structure is ready for Blender Extension packaging

Runtime validation is still needed inside Blender 4.2 for:

- registration and panel rendering
- operator context edge cases
- workflow preset execution chains
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
