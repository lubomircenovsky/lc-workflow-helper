from __future__ import annotations

import os
import sys
import traceback

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
TEST_BLEND = os.path.join(
    WORKSPACE_ROOT,
    "LC_workflow_addon",
    "tests",
    "blender",
    "_color-palette-persistence.blend",
)
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon


try:
    addon.register()
    scene_state = bpy.context.scene.lcw_scene_state
    window_state = bpy.context.window_manager.lcw_state
    expected = (0.12, 0.34, 0.56, 0.78)
    scene_state.vertex_color_palette_3 = expected

    result = bpy.ops.lcw.vertex_color_palette_activate(slot=3)
    assert result == {"FINISHED"}
    assert all(
        abs(actual - wanted) < 1e-6
        for actual, wanted in zip(window_state.color_value, expected, strict=True)
    )

    mesh = bpy.data.meshes.new("PaletteApplyMesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    obj = bpy.data.objects.new("PaletteApplyObject", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    mesh.polygons[0].select = True
    attribute = mesh.color_attributes.new("Color", "FLOAT_COLOR", "CORNER")
    result = bpy.ops.lcw.color_attribute_apply(
        color=window_state.color_value,
        mask_type="FACE",
        blend_mode="SET",
        attribute_name="Color",
    )
    assert result == {"FINISHED"}
    for element in attribute.data:
        assert all(
            abs(actual - wanted) < 2e-5
            for actual, wanted in zip(element.color_srgb, expected, strict=True)
        )

    bpy.ops.wm.save_as_mainfile(filepath=TEST_BLEND)
    scene_state.vertex_color_palette_3 = (1.0, 1.0, 1.0, 1.0)
    bpy.ops.wm.open_mainfile(filepath=TEST_BLEND)
    restored = bpy.context.scene.lcw_scene_state.vertex_color_palette_3
    assert all(
        abs(actual - wanted) < 1e-6
        for actual, wanted in zip(restored, expected, strict=True)
    )
    print("LCW_COLOR_PALETTE_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
    if os.path.exists(TEST_BLEND):
        os.remove(TEST_BLEND)
