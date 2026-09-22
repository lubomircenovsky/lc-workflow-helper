from __future__ import annotations

import time
from pathlib import Path

import bpy
from bpy.props import IntProperty

from . import jobs, status_overlay


class LCW_OT_cad_analyze(bpy.types.Operator):
    bl_idname = "lcw.cad_analyze"
    bl_label = "Analyze CAD Inputs"
    bl_description = "Check source eligibility without reconstructing geometry"
    bl_options = {"REGISTER"}

    def execute(self, context):
        state = context.scene.lcw_cad_reconstruction
        try:
            objects = jobs.sources(context, state)
            issues = jobs.preflight(context, state, objects)
            notes = jobs.analyze_risks(objects)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        state.analysis_summary = f"{len(objects)} mesh(es); {len(issues)} blocker(s), {len(notes)} risk note(s). " + "; ".join((issues + notes)[:3])
        self.report({"WARNING"} if issues or notes else {"INFO"}, state.analysis_summary[:240])
        return {"FINISHED"}


class LCW_OT_cad_reconstruct(bpy.types.Operator):
    bl_idname = "lcw.cad_reconstruct"
    bl_label = "Reconstruct CAD Meshes"
    bl_description = "Run the bundled CAD worker on independent sources; never auto-save the .blend"
    bl_options = {"REGISTER"}

    retry_index: IntProperty(default=-1)
    _timer = None
    _job = None

    @classmethod
    def poll(cls, context):
        return context.scene is not None and context.mode == "OBJECT" and jobs.ACTIVE_JOB is None

    def _start(self, context):
        state = context.scene.lcw_cad_reconstruction
        source = None
        if self.retry_index >= 0:
            if self.retry_index >= len(state.results):
                raise ValueError("Retry result no longer exists")
            row = state.results[self.retry_index]
            if row.status == "PASS" or row.source is None:
                raise ValueError("Retry requires a failed source object")
            source = row.source
        objects = jobs.sources(context, state, source)
        issues = jobs.preflight(context, state, objects)
        if issues:
            raise ValueError("Preflight: " + "; ".join(issues[:3]))
        root = jobs.run_root(state)
        self._job = jobs.CADBatch(context, objects, root)
        jobs.ACTIVE_JOB = self._job
        state.running = True
        state.progress = f"Queued {len(objects)} mesh(es)"

    def invoke(self, context, event):
        state = context.scene.lcw_cad_reconstruction
        if state.normal_override:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context):
        try:
            self._start(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if bpy.app.background:
            try:
                while self._job.step():
                    time.sleep(0.05)
            finally:
                self._finish(context)
            return {"FINISHED"}
        self._timer = context.window_manager.event_timer_add(0.3, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._job.cancel()
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            active = self._job.step()
        except Exception as exc:
            self._job.cancel()
            self.report({"ERROR"}, f"CAD batch stopped: {exc}")
            active = False
        if active:
            return {"RUNNING_MODAL"}
        self._finish(context)
        return {"CANCELLED"} if self._job.cancelled else {"FINISHED"}

    def _finish(self, context):
        state = self._job.scene.lcw_cad_reconstruction
        state.running = False
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        jobs.ACTIVE_JOB = None


class LCW_OT_cad_cancel(bpy.types.Operator):
    bl_idname = "lcw.cad_cancel"
    bl_label = "Cancel CAD Batch"
    bl_description = "Stop the worker; completed results remain and the unfinished object is not imported"

    @classmethod
    def poll(cls, context):
        return jobs.ACTIVE_JOB is not None

    def execute(self, context):
        jobs.ACTIVE_JOB.cancel()
        return {"FINISHED"}


class LCW_OT_cad_select_source(bpy.types.Operator):
    bl_idname = "lcw.cad_select_source"
    bl_label = "Select CAD Source"
    bl_description = "Select the source object of this result"

    result_index: IntProperty(default=0)

    def execute(self, context):
        results = context.scene.lcw_cad_reconstruction.results
        if self.result_index >= len(results) or results[self.result_index].source is None:
            return {"CANCELLED"}
        source = results[self.result_index].source
        for obj in context.selected_objects:
            obj.select_set(False)
        try:
            source.select_set(True)
            context.view_layer.objects.active = source
        except RuntimeError:
            self.report({"WARNING"}, "Source is outside the active view layer")
            return {"CANCELLED"}
        return {"FINISHED"}


class LCW_OT_cad_object_colors(bpy.types.Operator):
    bl_idname = "lcw.cad_object_colors"
    bl_label = "Show CAD Status Colors"
    bl_description = "Show colored wireframes only on generated CAD results in this viewport"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        status_overlay.show(context.space_data)
        context.area.tag_redraw()
        return {"FINISHED"}


class LCW_OT_cad_hide_object_colors(bpy.types.Operator):
    bl_idname = "lcw.cad_hide_object_colors"
    bl_label = "Hide CAD Status Colors"
    bl_description = "Hide the CAD result wireframes without changing viewport shading"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        status_overlay.hide(context.space_data)
        context.area.tag_redraw()
        return {"FINISHED"}


class LCW_OT_cad_open_run(bpy.types.Operator):
    bl_idname = "lcw.cad_open_run"
    bl_label = "Open CAD Run Folder"
    bl_description = "Open worker logs, validation files and reports for this run"

    result_index: IntProperty(default=0)

    def execute(self, context):
        rows = context.scene.lcw_cad_reconstruction.results
        if self.result_index >= len(rows):
            return {"CANCELLED"}
        path = Path(rows[self.result_index].run_dir)
        if not path.is_dir():
            self.report({"WARNING"}, "Run folder no longer exists")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=str(path))
        return {"FINISHED"}


CLASSES = (
    LCW_OT_cad_analyze,
    LCW_OT_cad_reconstruct,
    LCW_OT_cad_cancel,
    LCW_OT_cad_select_source,
    LCW_OT_cad_object_colors,
    LCW_OT_cad_hide_object_colors,
    LCW_OT_cad_open_run,
)
