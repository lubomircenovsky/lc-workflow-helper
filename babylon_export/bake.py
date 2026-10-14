"""Bake job: drive SimpleBake pass by pass, then build *_baked materials.

The job is a small state machine advanced by ``step()`` from a modal operator
timer, because SimpleBake bakes asynchronously. Originals (slot materials, face
assignments, UV maps, selection, mode, SimpleBake settings and preferences)
are always restored - after success, an error, a cancel request or a stalled
SimpleBake - but never while SimpleBake is still working on them.
The adapter is injectable for tests.
"""
from __future__ import annotations

import os
import time
import uuid

import bpy

from . import simplebake_adapter
from .core import bake_batch_name
from .materials import build_baked_material
from .plan import build_bake_plan
from .state import restore_state, snapshot_state
from .validation import validate

RUNNING, FINISHED, FAILED, CANCELLED = 'RUNNING', 'FINISHED', 'FAILED', 'CANCELLED'
# SimpleBake keeps its "baking" flag after an aborted macro (an error inside a
# step, Esc in the Cycles bake). If no bake job runs for this long while the
# flag is set, the bake is treated as stopped.
DEFAULT_STALL_SECONDS = 90.0

_active_job = None


def active_job():
    return _active_job


def set_active_job(job):
    global _active_job
    _active_job = job


def abandon_active_job(*, restore_data):
    """Stop the active job when the add-on unregisters or a file loads.

    ``restore_data`` restores the scene (unregister); on file load the scene
    is being replaced, so only global preferences are restored.
    """
    job = _active_job
    set_active_job(None)
    if job is None or job.result:
        return
    if restore_data and not job.adapter_is_baking():
        job.finish(CANCELLED, 'Bake stopped because LC Workflow was disabled.')
    else:
        job.restore_preferences_only()


class BakeError(RuntimeError):
    pass


class BakeJob:
    def __init__(self, collection, *, adapter=simplebake_adapter, stall_seconds=DEFAULT_STALL_SECONDS,
                 clock=time.monotonic):
        self.collection = collection
        self.settings = collection.lcw_babylon_export
        self.adapter = adapter
        self.stall_seconds = stall_seconds
        self.clock = clock
        self.scene = None
        self.plan = None
        self.state = None
        self.settings_token = None
        self.saved_preferences = None
        self.pass_index = -1
        self.phase = 'idle'
        self.operation_id = ''
        self.expected = set()
        self.idle_since = None
        self.cancel_requested = False
        self.pending = None
        self.built = []
        self.images = []
        self.message = ''
        self.result = None

    # -- public ---------------------------------------------------------
    @property
    def total_passes(self):
        return len(self.plan.passes) if self.plan else 0

    def progress_text(self):
        if self.phase == 'idle' or not self.plan:
            return 'Preparing bake...'
        if self.result or self.phase == 'draining':
            return self.message
        current = self.plan.passes[self.pass_index] if 0 <= self.pass_index < self.total_passes else None
        label = 'default state' if current is None or current.variant_idx is None else f'variant {current.variant_idx}'
        objects = ', '.join(sorted(o.name for o in current.objects)) if current else ''
        prefix = 'Cancelling after this pass. ' if self.cancel_requested else ''
        return f'{prefix}Pass {self.pass_index + 1}/{self.total_passes} ({label}): {objects}'

    def request_cancel(self):
        self.cancel_requested = True

    def adapter_is_baking(self):
        try:
            return bool(self.adapter.is_baking())
        except Exception:  # noqa: BLE001
            return False

    def start(self):
        """Validate, plan, snapshot. Raises BakeError; leaves nothing changed."""
        errors = [i.text for i in validate(self.collection) if i.level == 'ERROR']
        if errors:
            raise BakeError(errors[0] if len(errors) == 1 else f'{errors[0]} (+{len(errors) - 1} more)')
        self.plan = build_bake_plan(self.collection)
        if not self.plan.passes:
            raise BakeError('No material is selected for baking.')
        self.scene = bpy.context.scene
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        self.state = snapshot_state(self.plan)
        try:
            sbp = self.adapter.bake_properties(self.scene)
            self.settings_token = self.adapter.save_settings(sbp)
            if not self.settings_token:
                raise BakeError('Could not save the current SimpleBake settings.')
            self.saved_preferences = self.adapter.suspend_preferences()
        except Exception as exc:
            self.finish(FAILED, f'Bake cannot start: {exc}')
            raise BakeError(str(exc)) from exc
        self.phase = 'next'

    def step(self):
        """Advance the job; return RUNNING until a final status."""
        if self.result:
            return self.result
        try:
            if self.phase == 'draining':
                # Never restore originals while SimpleBake still works on them.
                if self.adapter.is_baking() and not self._stalled():
                    return RUNNING
                return self.finish(*self.pending)
            if self.phase == 'next':
                if self.cancel_requested:
                    return self.finish(CANCELLED, 'Bake cancelled; completed passes were kept.')
                self.pass_index += 1
                if self.pass_index >= self.total_passes:
                    return self.finish(FINISHED, self._summary())
                self._start_pass(self.plan.passes[self.pass_index])
                self.phase = 'baking'
                return RUNNING
            if self.phase == 'baking':
                if self.adapter.is_baking():
                    if self._stalled():
                        self.adapter.clear_stuck_bake()
                        raise BakeError(f'SimpleBake stopped during pass {self.pass_index + 1} without finishing '
                                        '(an error inside SimpleBake or Esc in the bake).')
                    return RUNNING
                self._collect(self.plan.passes[self.pass_index])
                self.phase = 'next'
                return RUNNING
        except Exception as exc:  # noqa: BLE001 - every failure must restore originals
            message = f'Bake failed: {exc}'
            if self.adapter_is_baking() and not self._stalled():
                self.pending, self.phase = (FAILED, message), 'draining'
                self.message = message + ' Waiting for SimpleBake to stop...'
                return RUNNING
            return self.finish(FAILED, message)
        return RUNNING

    def finish(self, status, message):
        """Restore originals exactly once, whatever happened."""
        if self.result:
            return self.result
        self.result, self.message = status, message
        errors = []
        if self.state is not None:
            try:
                restore_state(self.state)
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        if self.settings_token:
            try:
                self.adapter.restore_settings(self.adapter.bake_properties(self.scene), self.settings_token)
                self.settings_token = None
            except Exception as exc:  # noqa: BLE001
                errors.append(f'SimpleBake settings: {exc}')
        self.restore_preferences_only()
        if errors:
            self.result = FAILED
            self.message = f'{message} ' + '; '.join(errors)
        return self.result

    def restore_preferences_only(self):
        if self.saved_preferences is None:
            return
        try:
            self.adapter.restore_preferences(self.saved_preferences)
        finally:
            self.saved_preferences = None

    # -- internals ------------------------------------------------------
    def _stalled(self):
        """True once SimpleBake claims to bake but Blender runs no bake job."""
        if self.adapter.bake_job_running():
            self.idle_since = None
            return False
        now = self.clock()
        if self.idle_since is None:
            self.idle_since = now
        return now - self.idle_since >= self.stall_seconds

    def _start_pass(self, bake_pass):
        objects = sorted(bake_pass.objects, key=lambda o: o.name)
        for (obj, slot_index), material in bake_pass.assignments.items():
            slot = obj.material_slots[slot_index]
            if slot.material != material:
                slot.material = material
        sbp = self.adapter.bake_properties(self.scene)
        self.adapter.configure_simplebake(
            sbp, preset=self.settings.simplebake_preset, texture_dir=self.settings.texture_dir,
            batch_name=bake_batch_name(self.collection.name), objects=objects,
            enabled_pairs=bake_pass.to_bake)
        # Activate the bake UV last: a SimpleBake preset may change active UVs.
        uv_name = self.settings.bake_uv_name
        for obj in objects:
            layers = obj.data.uv_layers
            if layers.active is None or layers.active.name != uv_name:
                layers.active = layers[uv_name]
        self.expected = set(self.adapter.expected_channels(sbp))
        if not self.expected:
            raise BakeError('SimpleBake has no channel selected that glTF can use.')
        self.operation_id = uuid.uuid4().hex
        self.idle_since = None
        self.adapter.start_bake(self.operation_id)

    def _collect(self, bake_pass):
        images = self.adapter.collect_bake_images(self.operation_id, bake_pass.to_bake)
        problems = []
        for (obj, mat), maps in sorted(images.items(), key=lambda item: (item[0][0].name, item[0][1].name)):
            missing = self.expected - set(maps)
            if missing:
                problems.append(f'{obj.name} / {mat.name}: ' + ', '.join(sorted(missing)))
        if problems:
            raise BakeError('SimpleBake did not produce all channels for ' + '; '.join(problems))
        for (obj, mat), maps in sorted(images.items(), key=lambda item: (item[0][0].name, item[0][1].name)):
            for image in maps.values():
                image['bbe_owner'] = self.collection.name  # ours: later runs may replace it
                if image not in self.images:
                    self.images.append(image)
            self.built.append(build_baked_material(mat, obj, maps, self.settings))

    def _summary(self):
        names = ', '.join(sorted(m.name for m in self.built))
        folder = os.path.normpath(bpy.path.abspath(self.settings.texture_dir))
        return (f'Baked {len(self.built)} material(s) in {self.total_passes} pass(es): {names}. '
                f'{len(self.images)} texture(s) in {folder}')
