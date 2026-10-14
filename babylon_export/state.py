"""Restore originals and context even after a failed export/bake."""
from dataclasses import dataclass
import bpy
from .simplebake_adapter import bake_properties


SIMPLEBAKE_PROPERTIES = (
    'global_mode', 'tex_per_mat', 'prefer_existing_sbmap', 'new_uv_option',
    'restore_orig_uv_map', 'batch_name', 'save_bakes_external', 'export_path',
    'copy_and_apply', 'apply_bakes_to_original', 'merged_bake',
    'selected_col', 'selected_metal', 'selected_rough', 'selected_normal',
    'selected_trans', 'selected_transrough', 'selected_emission',
    'selected_emission_strength', 'selected_sss', 'selected_sss_scale',
    'selected_ssscol', 'selected_clearcoat', 'selected_clearcoat_rough',
    'selected_specular', 'selected_alpha', 'selected_bump',
    'selected_displacement', 'selected_col_mats', 'selected_col_vertex',
    'selected_ao', 'selected_thickness', 'selected_curvature', 'selected_lightmap',
)
SIMPLEBAKE_OBJECT_FIELDS = ('obj_point', 'name', 'expanded')


def _simplebake_snapshot(group):
    """Capture only the explicitly supported phase 2 settings, never all RNA."""
    values = {name: getattr(group, name) for name in SIMPLEBAKE_PROPERTIES if hasattr(group, name)}
    if hasattr(group, 'objects_list'):
        values['objects_list'] = [
            {name: getattr(item, name) for name in SIMPLEBAKE_OBJECT_FIELDS if hasattr(item, name)}
            for item in group.objects_list]
    return values


def _simplebake_restore(group, values):
    for name in SIMPLEBAKE_PROPERTIES:
        if name in values and getattr(group, name) != values[name]:
            setattr(group, name, values[name])
    if 'objects_list' not in values:
        return
    items, records = group.objects_list, values['objects_list']
    # Preserve unchanged rows and avoid callbacks caused by clearing/recreating
    # the entire list. New rows receive only values different from defaults.
    while len(items) > len(records):
        items.remove(len(items) - 1)
    while len(items) < len(records):
        items.add()
    for item, record in zip(items, records):
        for name in SIMPLEBAKE_OBJECT_FIELDS:
            if name in record and getattr(item, name) != record[name]:
                value = record[name]
                setattr(item, name, value)


@dataclass
class State:
    slots: list
    uv: list
    selected: list
    active: object
    mode: str
    view_layer: object
    simplebake: object
    simplebake_values: dict
    frames: list
    mesh_materials: list


def snapshot_state(plan, context=None, *, include_simplebake=False):
    """Export never accesses SimpleBake; phase 2 must explicitly opt in."""
    context = context or bpy.context
    sbp = bake_properties(context.scene) if include_simplebake else None
    active = context.view_layer.objects.active
    return State(
        [(o, [(s.link, s.material) for s in o.material_slots]) for o in plan.objects],
        [(o.data, o.data.uv_layers.active_index, [uv.active_render for uv in o.data.uv_layers])
         for o in plan.objects], list(context.selected_objects), active,
        active.mode if active else 'OBJECT', context.view_layer, sbp,
        _simplebake_snapshot(sbp) if sbp is not None else {},
        [(scene, scene.frame_current, scene.frame_subframe) for scene in bpy.data.scenes],
        [(mesh, list(mesh.materials)) for mesh in dict.fromkeys(o.data for o in plan.objects)])


def restore_state(state):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for scene, frame, subframe in state.frames:
        if scene.frame_current != frame or scene.frame_subframe != subframe:
            scene.frame_set(frame, subframe=subframe)
    for mesh, materials in state.mesh_materials:
        if list(mesh.materials) != materials:
            mesh.materials.clear()
            for material in materials:
                mesh.materials.append(material)
    for obj, slots in state.slots:
        for slot, (link, material) in zip(obj.material_slots, slots):
            # Avoid writing identical values to linked/library datablocks.
            if slot.link != link:
                slot.link = link
            if slot.material != material:
                slot.material = material
    for mesh, active, render in state.uv:
        if mesh.uv_layers and mesh.uv_layers.active_index != active:
            mesh.uv_layers.active_index = active
        for uv, flag in zip(mesh.uv_layers, render):
            if uv.active_render != flag:
                uv.active_render = flag
    for obj in state.view_layer.objects:
        desired = obj in state.selected
        if obj.select_get(view_layer=state.view_layer) != desired:
            obj.select_set(desired, view_layer=state.view_layer)
    state.view_layer.objects.active = state.active
    if state.simplebake is not None:
        _simplebake_restore(state.simplebake, state.simplebake_values)
    if state.active and state.mode != 'OBJECT':
        with bpy.context.temp_override(view_layer=state.view_layer, active_object=state.active,
                                       object=state.active):
            bpy.ops.object.mode_set(mode=state.mode)
