"""Snapshot and restore of the user's Blender data around an export or bake.

SimpleBake settings are not handled here; ``simplebake_adapter.save_settings``
/ ``restore_settings`` snapshot them with SimpleBake's own preset mechanism.
Restore runs every section even if one fails and reports all failures.
"""
from array import array
from dataclasses import dataclass, field
import bpy


@dataclass
class State:
    slots: list
    uv: list
    selected: list
    active: object
    mode: str
    view_layer: object
    frames: list
    mesh_materials: list
    face_material_indices: list = field(default_factory=list)


def _face_indices(mesh):
    values = array('i', [0]) * len(mesh.polygons)
    mesh.polygons.foreach_get('material_index', values)
    return values


def snapshot_state(plan, context=None):
    context = context or bpy.context
    active = context.view_layer.objects.active
    meshes = list(dict.fromkeys(o.data for o in plan.objects))
    # Active and render UV of every mesh in the file: a SimpleBake preset can
    # change the active UV of objects outside the plan as well.
    uv_meshes = [mesh for mesh in bpy.data.meshes if mesh.library is None]
    return State(
        slots=[(o, [(s.link, s.material) for s in o.material_slots]) for o in plan.objects],
        uv=[(mesh, mesh.uv_layers.active_index, [uv.active_render for uv in mesh.uv_layers])
            for mesh in uv_meshes],
        selected=list(context.selected_objects),
        active=active,
        mode=active.mode if active else 'OBJECT',
        view_layer=context.view_layer,
        frames=[(scene, scene.frame_current, scene.frame_subframe) for scene in bpy.data.scenes],
        mesh_materials=[(mesh, list(mesh.materials)) for mesh in meshes],
        face_material_indices=[(mesh, _face_indices(mesh)) for mesh in meshes],
    )


def _restore_mesh_materials(state):
    for (mesh, materials), (_mesh, face_indices) in zip(state.mesh_materials, state.face_material_indices):
        current = list(mesh.materials)
        if current == materials:
            continue
        if len(current) == len(materials):
            # Per-slot assignment keeps polygon material indices intact.
            for index, material in enumerate(materials):
                if mesh.materials[index] != material:
                    mesh.materials[index] = material
            continue
        # A different slot count needs clear(), which resets every polygon's
        # material_index to 0 - put the saved indices back afterwards.
        mesh.materials.clear()
        for material in materials:
            mesh.materials.append(material)
        if len(face_indices) == len(mesh.polygons):
            mesh.polygons.foreach_set('material_index', face_indices)
            mesh.update()


def _restore_slots(state):
    for obj, slots in state.slots:
        for slot, (link, material) in zip(obj.material_slots, slots):
            # Avoid writing identical values to linked/library datablocks.
            if slot.link != link:
                slot.link = link
            if slot.material != material:
                slot.material = material


def _restore_uvs(state):
    for mesh, active, render in state.uv:
        if mesh.uv_layers and mesh.uv_layers.active_index != active:
            mesh.uv_layers.active_index = active
        for uv, flag in zip(mesh.uv_layers, render):
            if uv.active_render != flag:
                uv.active_render = flag


def _restore_frames(state):
    for scene, frame, subframe in state.frames:
        if scene.frame_current != frame or scene.frame_subframe != subframe:
            scene.frame_set(frame, subframe=subframe)


def _restore_selection(state):
    layer = state.view_layer
    for obj in layer.objects:
        desired = obj in state.selected
        if obj.select_get(view_layer=layer) != desired:
            obj.select_set(desired, view_layer=layer)
    layer.objects.active = state.active


def _restore_mode(state):
    if state.active and state.mode != 'OBJECT':
        with bpy.context.temp_override(view_layer=state.view_layer, active_object=state.active,
                                       object=state.active):
            bpy.ops.object.mode_set(mode=state.mode)


def restore_state(state):
    """Restore everything; raise one RuntimeError listing every failed part."""
    errors = []
    sections = (('object mode', lambda s: bpy.context.object and bpy.context.object.mode != 'OBJECT'
                 and bpy.ops.object.mode_set(mode='OBJECT')),
                ('frames', _restore_frames), ('mesh materials', _restore_mesh_materials),
                ('material slots', _restore_slots), ('UV maps', _restore_uvs),
                ('selection', _restore_selection), ('mode', _restore_mode))
    for label, restore in sections:
        try:
            restore(state)
        except Exception as exc:  # noqa: BLE001 - keep restoring the other parts
            errors.append(f'{label}: {exc}')
    if errors:
        raise RuntimeError('Restoring the original state failed for ' + '; '.join(errors))
