# LC Workflow Helper 0.5.9

This release lets Bakers work on selected objects, and lets the shape key value go above 1.

## Bakers (Substance)

- **New input option: Selected Objects.** Under Scope → Input you can now bake the selected mesh objects instead of a collection. Collection stays the default, and existing profiles work as before.
  - The grouping option is now labeled **Group By** and still offers by object, by material, and one map set.
  - Selected meshes are exported to an internal FBX. Your selection, active object, mode, materials and UVs stay as they were, also when the export fails.
  - Maps from Selected Objects go to the `Selected_Objects` subfolder. Two different selections with the same material names share map names, so set a different Output Root for separate sets.
  - High-poly and cage are still taken from their own collections.
- Preview exports no longer overwrite each other when you run Preview twice in the same second.

## Shape Keys

- **Shape Key Value goes up to 10.** "Set Active Shape Key Value Across Selection" now accepts 0–10. Each shape key limits the value to its own Range Min/Max, so a key with a maximum of 1 gets 1, and a key with a maximum of 3 gets 3.

## Validation

- All 158 unit tests pass.
- In Blender 5.2: the new native test `tests/blender_substance_selection.py` passed, including a real AO bake in every grouping mode. The existing Substance tests and the panel draw test pass too. The Selected Objects input was also checked by the user in the Blender UI.
- Shape key values were checked in Blender 5.2.3 on keys with maximums of 1, 3 and 10.
- The extension ZIP was built and validated with the official Blender 5.2 `extension build/validate`, and an isolated install was tested.
