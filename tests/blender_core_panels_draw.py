"""Draw every core LC Workflow panel with all sections open against Blender RNA.

blender --background --factory-startup --python tests/blender_core_panels_draw.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.ui import panels

FUNCTIONS = bpy.types.UILayout.bl_rna.functions


class Layout:
    """Records draw calls; validates keyword arguments, enums and RNA names."""

    def __init__(self, calls):
        self.calls = calls
        self.scale_y = 1.0

    def _child(self, *_args, **_kwargs):
        child = Layout(self.calls)
        self.calls.append(('child', child))
        return child

    row = column = box = split = grid_flow = _child

    def _check(self, name, kwargs):
        params = FUNCTIONS[name].parameters
        for key, value in kwargs.items():
            assert key in params, (name, key)
            if params[key].type == 'ENUM':
                assert value in {item.identifier for item in params[key].enum_items}, (name, key, value)

    def prop(self, data, name, **kwargs):
        assert name in data.bl_rna.properties, name
        self._check('prop', kwargs)
        self.calls.append(('prop', name, kwargs))

    def prop_enum(self, data, name, value, **kwargs):
        assert name in data.bl_rna.properties, name
        self.calls.append(('prop_enum', name, kwargs))

    def label(self, **kwargs):
        self._check('label', kwargs)
        self.calls.append(('label', kwargs.get('text', ''), kwargs, self))

    def operator(self, name, **kwargs):
        self._check('operator', kwargs)
        namespace, operator = name.split('.')
        getattr(getattr(bpy.ops, namespace), operator).get_rna_type()
        self.calls.append(('operator', name, kwargs, self))
        return SimpleNamespace()

    def separator(self, **kwargs):
        self._check('separator', kwargs)
        self.calls.append(('separator', kwargs.get('type', 'AUTO'), kwargs))

    def progress(self, **kwargs):
        self._check('progress', kwargs)
        self.calls.append(('progress', kwargs.get('text', ''), kwargs))

    def template_list(self, *args, **kwargs):
        self.calls.append(('list', args[0], kwargs))


def open_all(data):
    for prop in data.bl_rna.properties:
        if prop.type == 'BOOLEAN' and prop.identifier.endswith('_open') and not prop.is_readonly:
            setattr(data, prop.identifier, True)


def draw(panel_cls):
    calls = []
    panel_cls.draw(SimpleNamespace(layout=Layout(calls)), bpy.context)
    return calls


def labels(calls):
    return {c[1]: c[2] for c in calls if c[0] == 'label'}


addon.register()
# Loaded from the source tree, the add-on has no preferences entry; the panels
# only read these fields from it.
panels.addon_preferences = lambda _context: SimpleNamespace(
    baker_profiles=[], active_baker_profile_index=0, presets=(),
    substance_baker_backend_sal=True, substance_baker_backend_sora=False)
try:
    bpy.ops.mesh.primitive_cube_add()
    wm = bpy.context.window_manager.lcw_state
    scene = bpy.context.scene.lcw_scene_state
    for data in (wm, scene, scene.substance_designer_baker):
        open_all(data)
    bpy.ops.lcw.workflow_preset_add()
    bpy.ops.lcw.workflow_action_add()

    skipped = {panels.LCW_PT_quad_reconstruction, panels.LCW_PT_cad_reconstruction, panels.LCW_PT_babylon_export}
    for panel_cls in panels.CLASSES:
        if not issubclass(panel_cls, bpy.types.Panel) or panel_cls in skipped:
            continue
        draw(panel_cls)

    found = labels(draw(panels.LCW_PT_materials))
    for text, icon in (('Material Links', 'LINKED'), ('Assign Material', 'MATERIAL'), ('Cleanup', 'TRASH')):
        assert found.get(text, {}).get('icon') == icon, (text, found.get(text))

    calls = draw(panels.LCW_PT_substance_designer_baker)
    found = labels(calls)
    for text in ('Output', 'UV & Padding', 'Last Run'):
        assert text in found, text
    assert sum(1 for c in calls if c[:2] == ('separator', 'LINE')) >= 2
    bake = next(c for c in calls if c[:2] == ('operator', 'lcw.sdb_bake_ao'))
    assert bake[3].scale_y == 1.3, 'primary bake action is emphasised'
    # Baker cards: a neutral icon, never a validation checkmark.
    from LC_workflow_addon.ui.panels import SDB_BAKER_SUMMARIES
    for summary in SDB_BAKER_SUMMARIES.values():
        assert found[summary]['icon'] == 'TEXTURE', summary

    assert 'Palette' in labels(draw(panels.LCW_PT_colors))

    calls = draw(panels.LCW_PT_uv)
    assert labels(calls)['Active UV Channel']['icon'] == 'GROUP_UVS'
    assert ('separator', 'LINE', {'type': 'LINE'}) in calls

    calls = draw(panels.LCW_PT_workflow_presets)
    run = next(c for c in calls if c[:2] == ('operator', 'lcw.workflow_preset_run'))
    assert run[3].scale_y == 1.3
    assert labels(calls)['Action Settings']['icon'] == 'TOOL_SETTINGS'
finally:
    addon.unregister()
print('PASS blender_core_panels_draw')
