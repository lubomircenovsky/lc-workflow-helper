"""Babylon operations on the Scene Collection store their typed outcome.

The master collection is embedded data: it cannot be assigned to a pointer
property, which used to make Check fail after it had finished its work.

blender --background --factory-startup --python tests/blender_babylon_scene_collection_report.py
"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.babylon_export.reporting import last_operation_status, store_outcome

addon.register()
try:
    scene = bpy.context.scene
    state = scene.lcw_babylon_export
    state.target_collection = None
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = view_layer.layer_collection
    master = scene.collection
    assert master.is_embedded_data

    bpy.ops.lcw.babylon_check()  # must not raise on the embedded collection
    assert state.last_operation == 'CHECK', state.last_operation
    assert state.last_outcome != 'UNKNOWN'
    assert state.report_scene_collection and state.report_collection is None
    kind, text = last_operation_status(state, master)
    assert text.startswith('Last Check'), text

    other = bpy.data.collections.new('Other target')
    scene.collection.children.link(other)
    kind, text = last_operation_status(state, other)
    assert (kind, text) == ('info', 'Last report: Scene Collection'), (kind, text)

    # A normal collection clears the flag again.
    store_outcome(state, other, 'EXPORT', 'OK')
    assert not state.report_scene_collection and state.report_collection == other
    assert last_operation_status(state, master)[0] == 'info'
    assert last_operation_status(state, other) == ('ok', 'Last Export: verified')
finally:
    addon.unregister()
print('PASS blender_babylon_scene_collection_report')
