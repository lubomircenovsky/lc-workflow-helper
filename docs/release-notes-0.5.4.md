# LC Workflow helper 0.5.4

This release adds a bundled Geometry Nodes library to the LC Workflow panel.

## GN Library

- Add `GN_Screw_Replace_By_Geometry` to the current `.blend` file or put it directly on the active object as a Geometry Nodes modifier.
- Choose **Use Same Data** to reuse a group already loaded from the library, or **New Instance** to create an independent copy of both node groups.
- The asset includes its helper group and node-frame notes. Screw meshes and source collections are not bundled; set `Source Collection` and `Replacement Object` in the modifier.
- This library item requires Blender 5.2 or newer. The rest of the extension retains its Blender 4.2 minimum.

## Fixes

- Fixed the GN Library panel icon so the panel draws in Blender 5.2.
