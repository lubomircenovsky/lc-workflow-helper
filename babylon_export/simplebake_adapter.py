"""The only module that talks to SimpleBake (optional third-party add-on).

No SimpleBake code is copied or imported at module level. Everything here was
checked against SimpleBake 2.9.11; ``availability()`` gates other versions.

Facts this adapter relies on (SimpleBake 2.9.11 source):
- ``simplebake.bake_operation_pbr`` accepts ``bake_id_override``; every image it
  creates carries ``SB_bake_operation_id`` with that id, plus ``SB_bake_object``,
  ``SB_this_bake`` and, with ``tex_per_mat``, ``SB_bake_material``.
- The operator returns RUNNING_MODAL and bakes through a macro;
  ``background_and_progress.BakeInProgress.is_baking`` is reset only by the
  finishing step, so an aborted macro leaves it True (see ``bake.py`` watchdog).
- ``tex_per_mat`` bakes only materials enabled in ``mat_bake_list``.
- ``tex_per_mat`` + ``expand_mat_uvs`` REPLACES an existing UV map called
  SimpleBake, and ``new_uv_option`` creates new UVs; both are forced off.
- Property update callbacks cascade into other settings unless
  ``utils.suppress_for_preset_load`` is set; SimpleBake sets it itself when it
  loads a preset. Settings are therefore saved/restored with SimpleBake's own
  local preset save/load (all panel settings, lists and related scene settings).
- ``--background`` makes SimpleBake copy-and-apply; baking must run in the UI.
"""
from contextlib import contextmanager
import sys

import addon_utils
import bpy

SUPPORTED_VERSION = (2, 9)
RESTORE_PRESET = 'LCW_BBE_restore'

# Settings the workflow depends on; written (with callbacks suppressed) before
# each pass. Everything is restored from the RESTORE_PRESET snapshot afterwards.
FORCED_SETTINGS = {
    'global_mode': 'PBR',
    'tex_per_mat': True,
    'merged_bake': False,
    'new_uv_option': False,
    'prefer_existing_sbmap': False,  # we activate the bake UV ourselves
    'expand_mat_uvs': False,  # would rebuild the SimpleBake UV map
    'restore_orig_uv_map': True,
    'copy_and_apply': False,
    'apply_bakes_to_original': False,
    'hide_source_objects': False,
    'hide_source_objects_viewport_disable': False,
    'hide_source_objects_render': False,
    'save_obj_external': False,
    'save_bakes_external': True,
    'keep_internal_after_export': True,  # False deletes the images we collect
    'del_cptex_components': False,  # channel packing must not delete our maps
    'replace_previous_bakes': True,
    'clear_image': True,
    'auto_detect_udims': False,  # glTF cannot use UDIM tiles
    'join_objs_to_proxy': False,
    'selected_s2a': False,
    'cycles_s2a': False,
    'bgbake': 'fg',
    'fake_background': False,
    'suppress_report': True,
    'rough_glossy_switch': 'Roughness',
    'normal_format_switch': 'OpenGL',
    'multiply_diffuse_ao': 'purediffuse',
}

# Add-on preferences that save the file, purge orphan data or change every
# viewport during a bake; switched off for the run and restored afterwards.
SUSPENDED_PREFERENCES = {'saveonbake': False, 'purge_after_bake': False, 'solidshadingonbake': False}

# SB_this_bake value -> channel used by materials.build_baked_material.
CHANNEL_MAP = {
    'Diffuse': 'base_color',
    'Metalness': 'metallic',
    'Roughness': 'roughness',
    'Normal': 'normal',
    'Alpha': 'alpha',
    'Emission': 'emission',
    'Ambient Occlusion': 'ao',
}
# Panel toggle -> channel, for the maps glTF can use.
USED_SELECTIONS = {
    'selected_col': 'base_color', 'selected_metal': 'metallic', 'selected_rough': 'roughness',
    'selected_normal': 'normal', 'selected_alpha': 'alpha', 'selected_emission': 'emission',
    'selected_ao': 'ao',
}
CHANNEL_LABELS = {'base_color': 'Diffuse', 'metallic': 'Metalness', 'roughness': 'Roughness',
                  'normal': 'Normal', 'alpha': 'Alpha', 'emission': 'Emission', 'ao': 'AO'}
# Panel toggles that produce maps glTF cannot use; reported as warnings.
UNUSED_SELECTIONS = {
    'selected_bump': 'Bump', 'selected_displacement': 'Displacement',
    'selected_specular': 'Specular', 'selected_trans': 'Transmission',
    'selected_transrough': 'Transmission Roughness', 'selected_clearcoat': 'Clearcoat',
    'selected_clearcoat_rough': 'Clearcoat Roughness', 'selected_sss': 'SSS',
    'selected_sss_scale': 'SSS Scale', 'selected_ssscol': 'SSS Colour',
    'selected_emission_strength': 'Emission Strength', 'selected_thickness': 'Thickness',
    'selected_curvature': 'Curvature', 'selected_lightmap': 'Lightmap',
    'selected_col_mats': 'Colour ID', 'selected_col_vertex': 'Vertex Colour',
}
WORKING_PREFIXES = ('SBW_', 'SBM_')  # SimpleBake strips these from material names


def availability():
    """Return (module name, version) only for an enabled SimpleBake addon."""
    enabled = bpy.context.preferences.addons
    for module in addon_utils.modules():
        info = getattr(module, 'bl_info', {})
        if ('simplebake' in module.__name__.lower() or info.get('name', '').lower() == 'simplebake'):
            if module.__name__ in enabled:
                return module.__name__, tuple(info.get('version', ()))
    return None, ()


def bake_properties(scene):
    return getattr(scene, 'SimpleBake_Props', None) if availability()[0] else None


def addon_preferences():
    module = availability()[0]
    addon = bpy.context.preferences.addons.get(module) if module else None
    return addon.preferences if addon else None


def has_preset(sbp, name):
    return bool(name) and f'SB_local_preset_{name}' in sbp.keys()


def expected_channels(sbp):
    """Channels glTF can use that SimpleBake will bake with its current settings."""
    return {channel for name, channel in USED_SELECTIONS.items() if getattr(sbp, name, False)}


def unused_channel_labels(sbp):
    return [label for name, label in UNUSED_SELECTIONS.items() if getattr(sbp, name, False)]


def settings_summary(sbp):
    """Short read-only description for the panel."""
    channels = ', '.join(CHANNEL_LABELS[c] for c in CHANNEL_LABELS if c in expected_channels(sbp))
    return f"{channels or 'no glTF channels'} · {getattr(sbp, 'imgwidth', '?')}×{getattr(sbp, 'imgheight', '?')} px"


def _submodule(name):
    module = availability()[0]
    return sys.modules.get(f'{module}.{name}') if module else None


@contextmanager
def _callbacks_suppressed():
    """Use SimpleBake's own preset-load switch so updates do not cascade."""
    utils = _submodule('utils')
    if utils is None or not hasattr(utils, 'suppress_for_preset_load'):
        yield
        return
    previous = utils.suppress_for_preset_load
    utils.suppress_for_preset_load = True
    try:
        yield
    finally:
        utils.suppress_for_preset_load = previous


def is_baking():
    """True while SimpleBake considers a bake active."""
    progress = _submodule('background_and_progress')
    holder = getattr(progress, 'BakeInProgress', None)
    if holder is not None:
        return bool(holder.is_baking)
    return not bpy.ops.simplebake.bake_operation_pbr.poll()


def clear_stuck_bake():
    """Reset SimpleBake's flag after its macro aborted, so baking works again.

    Only called once no Blender bake job has run for a long time while the
    flag stayed set (see bake.BakeJob._stalled).
    """
    progress = _submodule('background_and_progress')
    holder = getattr(progress, 'BakeInProgress', None)
    if holder is not None:
        holder.is_baking = False


def bake_job_running():
    """True while Blender actually renders a bake (Cycles OBJECT_BAKE job)."""
    return bpy.app.is_job_running('OBJECT_BAKE')


def save_settings(sbp):
    """Snapshot every SimpleBake setting with SimpleBake's own preset saver."""
    bpy.ops.simplebake.local_preset_save_override(name_override=RESTORE_PRESET)
    return RESTORE_PRESET if has_preset(sbp, RESTORE_PRESET) else None


def restore_settings(sbp, token):
    """Load the snapshot (callbacks suppressed by SimpleBake) and remove it."""
    if not token or not has_preset(sbp, token):
        return
    try:
        bpy.ops.simplebake.local_preset_load_override(name_override=token)
    finally:
        del sbp[f'SB_local_preset_{token}']


def suspend_preferences():
    """Turn off preferences listed in SUSPENDED_PREFERENCES; return previous values."""
    prefs = addon_preferences()
    previous = {}
    if prefs is None:
        return previous
    for name, value in SUSPENDED_PREFERENCES.items():
        if hasattr(prefs, name) and getattr(prefs, name) != value:
            previous[name] = getattr(prefs, name)
            setattr(prefs, name, value)
    return previous


def restore_preferences(previous):
    prefs = addon_preferences()
    if prefs is None or not previous:
        return
    for name, value in previous.items():
        if getattr(prefs, name, value) != value:
            setattr(prefs, name, value)


def configure_simplebake(sbp, *, preset, texture_dir, batch_name, objects, enabled_pairs):
    """Prepare one pass: optional preset, forced settings, objects, materials.

    ``enabled_pairs`` is the set of (object, material) pairs to bake in this
    pass; every other material of those objects is disabled in mat_bake_list.
    The caller activates the bake UV afterwards (a preset can change it).
    """
    if preset:
        if not has_preset(sbp, preset):
            raise RuntimeError(f'SimpleBake preset "{preset}" does not exist.')
        bpy.ops.simplebake.local_preset_load_override(name_override=preset)
    with _callbacks_suppressed():
        for name, value in FORCED_SETTINGS.items():
            if hasattr(sbp, name) and getattr(sbp, name) != value:
                setattr(sbp, name, value)
        if sbp.export_path != texture_dir:
            sbp.export_path = texture_dir
        if sbp.batch_name != batch_name:
            sbp.batch_name = batch_name
        sbp.objects_list.clear()
        for obj in objects:
            item = sbp.objects_list.add()
            item.obj_point = obj
            item.name = obj.name
        sbp.mat_bake_list.clear()
        enabled = {(obj.name, mat.name) for obj, mat in enabled_pairs}
        for obj in objects:
            seen = set()
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or mat.name in seen:
                    continue
                seen.add(mat.name)
                entry = sbp.mat_bake_list.add()
                entry.obj_name, entry.mat_name = obj.name, mat.name
                entry.enabled = (obj.name, mat.name) in enabled


def start_bake(operation_id):
    """Start the asynchronous foreground PBR bake; needs a window context."""
    result = bpy.ops.simplebake.bake_operation_pbr(bake_id_override=operation_id)
    if 'RUNNING_MODAL' not in result and 'FINISHED' not in result:
        raise RuntimeError('SimpleBake refused to start the bake; see its message for details.')


def collect_bake_images(operation_id, pairs):
    """Return {(object, material): {channel: Image}} for one bake operation.

    Images without SB_bake_material (e.g. specials baked once per object)
    apply to every requested material of that object.
    """
    by_name = {(obj.name, mat.name): (obj, mat) for obj, mat in pairs}
    per_object = {}
    for obj, mat in pairs:
        per_object.setdefault(obj.name, []).append((obj, mat))
    result = {pair: {} for pair in pairs}
    for image in bpy.data.images:
        if image.get('SB_bake_operation_id') != operation_id:
            continue
        channel = CHANNEL_MAP.get(image.get('SB_this_bake'))
        if channel is None:
            continue
        object_name, material_name = image.get('SB_bake_object'), image.get('SB_bake_material')
        if material_name:
            targets = [by_name[(object_name, material_name)]] if (object_name, material_name) in by_name else []
        else:
            targets = per_object.get(object_name, [])
        for pair in targets:
            result[pair].setdefault(channel, image)
    return result
