# Babylon Bake & Export

Bakes the materials of a collection with SimpleBake, builds glTF-ready `*_baked` materials and exports the collection as a GLB with every glTF material variant. Find it in the N-panel: **LC Workflow → Project specific tools → Babylon Bake & Export**.

## Requirements

- Blender 5.2 with the bundled glTF exporter. Turn on **Material Variants** in the glTF exporter preferences if you use variants.
- **SimpleBake 2.9.x** (optional third-party add-on), needed only for baking. Export of already baked materials works without it.
- The `.blend` file must be saved, because textures are written relative to it.
- A **glTF Collection Exporter** on the collection, with an output path and the GLB format. The exporter's settings are used for the export.

## Prepare the collection

1. Put the objects to export in one collection; child collections are included.
2. Give every object whose materials will be baked a UV map named like **Bake UV** (default `SimpleBake`). Bake textures are made on this map, and it becomes the only UV map in the GLB. The add-on never creates or changes it.
3. Set up glTF material variants as usual (glTF Variants panel). The default state and every variant are baked.
4. In the SimpleBake panel choose the channels and resolution. The Babylon panel shows a summary, for example `SimpleBake: Diffuse, Roughness, Normal · 4096×4096 px`. Channels glTF uses are Diffuse, Metalness, Roughness, Normal, Alpha, Emission and AO; Check warns about others (for example Bump). Alternatively name a SimpleBake local preset in **SimpleBake Preset**; it is loaded for the bake only.

## Choose what to bake

Open the panel, pick the **Collection** and press **Refresh Material List**. **Bake** is ticked by default for materials used in glTF variants and for materials with image textures or node groups. Change any tick; your choice is kept (marked *Custom*).

Materials that are not ticked are exported as they are. Objects with no baked material keep one UV map and do not need the bake UV.

## Run

- **Check** lists problems separately for baking and for export.
- **Bake** bakes the ticked materials. It runs one pass for the default state and one per variant that brings a not yet baked material, and bakes only the materials needed in each pass. Afterwards it creates or updates `<material>_baked` (fake user, textures from the texture folder). A material shared by several objects gets one texture set per object.
- **Bake & Export** bakes, then exports and verifies the GLB.
- **Export** exports with the existing `*_baked` materials.
- **Cancel After This Pass** stops between passes. SimpleBake cannot be interrupted safely inside a pass; do not press Esc while it bakes.
- **Clean Up** removes temporary export data left by a crash.

Do not edit or save the file while a bake runs; the panel shows a reminder.

## What the bake changes and restores

While baking, the add-on temporarily assigns variant materials to the slots, activates the bake UV and sets the SimpleBake options the workflow needs:

- PBR mode, texture per material, existing UV maps (no new or repacked UVs, no UDIM tiles),
- Roughness (not Glossy), OpenGL normals,
- external saving into **Texture Folder**, images kept in the file, replace previous bakes,
- no copy-and-apply, no hiding of source objects, foreground bake.

SimpleBake preferences that would save the file, purge orphan data or switch the viewport to Solid (*Save blend file prior to bake*, *purge after bake*, *solid shading on bake*) are switched off for the run.

When the bake finishes, fails or is cancelled, the add-on restores the original slot materials, face material assignments, UV maps, selection, mode and frame, every SimpleBake setting (saved and loaded with SimpleBake's own preset mechanism) and the SimpleBake preferences. Baked materials and textures stay. If SimpleBake stops inside a pass without finishing (an internal error or Esc), the add-on notices that Blender no longer bakes, restores the original state and reports the failure.

## Safety checks before baking

Check blocks the bake when:

- SimpleBake's *Disable other add-ons* preference is on (it would disable LC Workflow),
- the SimpleBake image name format lacks `%OBJ%` or `%BATCH%` (bakes would overwrite each other),
- SimpleBake *fake background* is on,
- a material on a baked object starts with `SBW_` or `SBM_` (reserved by SimpleBake),
- an existing image uses this collection's bake name (`LCW_<collection>`) but was not made by this tool – SimpleBake would replace it,
- a baked object has no bake UV, or no material is ticked.

It warns about unsaved changes, bake UVs outside the 0–1 square, baked objects sharing one mesh and channels glTF does not use.

## GLB result

- One UV set (`TEXCOORD_0`) per primitive, no Draco compression, PNG textures.
- All scene variants in `KHR_materials_variants`, mapped to `*_baked` materials.
- Temporary copies are removed after the export; the report shows the file size and counts.

## Limits

- SimpleBake must run with the Blender UI open (not `--background`).
- The bake UV must not overlap within one material; the add-on does not check UV layouts.
