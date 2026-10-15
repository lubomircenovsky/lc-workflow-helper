# LC Workflow Helper 0.5.7

This release adds Babylon Bake & Export and makes the N-panel easier to scan.

## Babylon Bake & Export (new)

- Bakes the ticked materials of a collection with the optional SimpleBake 2.9 add-on: one pass for the default state and one per glTF material variant. It uses the SimpleBake settings of the open file; a preset is optional.
- Builds glTF-ready `*_baked` materials and exports the collection as a GLB through its glTF Collection Exporter, with one UV map, no Draco and all variants. Unticked materials export unchanged, and the GLB is verified after export.
- Your file is protected: SimpleBake settings, preferences, material slots, face assignments and UVs are restored after every bake, also after a failure or cancel. A bake can be cancelled after the current pass.
- **Check** lists blocking problems before you bake. The panel shows the result of the last operation (Check, Export, Bake, Bake & Export, Clean Up) with its state.
- Details: `docs/babylon-bake-export.md`.

## Clearer N-panel

- **Category icons** in every panel header and in Main Category Order. Favorites has a gold star; the other category icons are monochrome.
- **Grouped default layout:** Scene Info and Favorites, then General tools, Specialized tools, Project specific tools and ETC.
- **Separators:** Main Category Order can add separators with an optional group name, move them with the arrows and remove them. The layout is saved in each `.blend` file. **Reset to Default** restores the default layout.
- **Kalibra Tools** and **Babylon Bake & Export** are separate categories. Files with a saved order keep it; the former "Project specific tools" entry becomes these two categories in the same place.
- **Result states** in CAD, Quad and Babylon use one set of icons. Each state has its own shape and color and is also written as text.
  - A Quad result is green only when its output is validated with an exact solver, HIGH confidence and no relaxations, unresolved triangles or warnings. An analysis is never shown as a pass.
- **Sections and primary actions:** headings, separator lines and taller main buttons in Materials, Bakers, Colors, UV, Workflow Presets, CAD, Quad and Babylon.
- CAD and Quad panels open collapsed. The CAD run button is always visible, and CAD UV Preparation moved to the UV panel. Quad progress is a read-only bar.
- A preference **Colored Panel Icons** switches back to Blender's built-in icons.

## Validation

- All 158 unit tests pass.
- Native Blender 5.2.1 tests pass for panel drawing (all core panels, CAD, Quad, Babylon), icons, separators, the default layout, layout reset and migration of old orders. They also pass for Babylon bake (simulated SimpleBake) and export.
- An earlier build was tested end to end with SimpleBake 2.9.11 in Blender 5.2.1. Later fixes are covered by the simulated tests only.
- The extension ZIP was built and validated with the official Blender 5.2 `extension build/validate`, and an isolated install was tested.
