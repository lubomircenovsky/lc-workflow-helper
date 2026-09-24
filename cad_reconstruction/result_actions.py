"""Result-history actions and scoped worker-file cleanup."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import bpy

from . import jobs, run_files, status_overlay, ui_text


ACTIVE_CLEANUP = None


@bpy.app.handlers.persistent
def _before_load(_dummy):
    cancel_active_cleanup()


def cancel_active_cleanup():
    if ACTIVE_CLEANUP is not None:
        ACTIVE_CLEANUP._pending = []
        ACTIVE_CLEANUP._finish(report=False)


def _can_manage(context):
    return (context.scene is not None and jobs.ACTIVE_JOB is None
            and not context.scene.lcw_cad_reconstruction.cleanup_running)


def _clear_history(state):
    # Keep status colors available after the per-scene history is removed.
    for row in state.results:
        obj = row.output
        if obj is not None and obj.type == "MESH" and obj.get("lcw_cad_run_id"):
            obj["lcw_cad_status"] = row.status
    status_overlay.clear()
    state.results.clear()
    state.active_result = 0
    state.results_visible = 5


class LCW_OT_cad_clear_results(bpy.types.Operator):
    bl_idname = "lcw.cad_clear_results"
    bl_label = "Clear Results"
    bl_description = "Remove result history from this .blend; keep output meshes and run files"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_manage(context) and bool(context.scene.lcw_cad_reconstruction.results)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        count = len(context.scene.lcw_cad_reconstruction.results)
        self.layout.label(text=f"Remove {count} result record(s) from this .blend?", icon="QUESTION")
        self.layout.label(text="Output meshes and run files stay. No archive is made.")

    def execute(self, context):
        state = context.scene.lcw_cad_reconstruction
        count = len(state.results)
        _clear_history(state)
        self.report({"INFO"}, f"Cleared {count} result record(s); outputs and run files kept")
        return {"FINISHED"}


class LCW_OT_cad_archive_results(bpy.types.Operator):
    bl_idname = "lcw.cad_archive_results"
    bl_label = "Archive & Clear Results"
    bl_description = "Save a readable result summary as a Blender Text block, then clear the panel; keep meshes and run files"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_manage(context) and bool(context.scene.lcw_cad_reconstruction.results)

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        count = len(context.scene.lcw_cad_reconstruction.results)
        self.layout.label(text=f"Archive {count} result(s) to a Blender Text block?", icon="TEXT")
        self.layout.label(text="Then clear panel history. Outputs and run files stay.")
        self.layout.label(text="Save this .blend to keep the archive.")

    def execute(self, context):
        state = context.scene.lcw_cad_reconstruction
        count = len(state.results)
        text = bpy.data.texts.new("CAD Results " + datetime.now().strftime("%Y-%m-%d %H-%M-%S"))
        try:
            text.write(f"CAD results archive | {count} record(s)\n\n")
            for row in state.results:
                source = row.source.name if row.source else "Missing source"
                output = row.output.name if row.output else "No output"
                text.write(f"{source} | {row.status} | {output}\n")
                text.write(f"  {ui_text.result_brief(row)}\n")
                if row.reason:
                    text.write(f"  Reason: {row.reason}\n")
                if row.technical_reason and row.technical_reason != row.reason:
                    text.write(f"  Technical: {row.technical_reason}\n")
                if row.perimeter_summary:
                    text.write(f"  {row.perimeter_summary}\n")
                if row.planar_summary:
                    text.write(f"  {row.planar_summary}\n")
                text.write(f"  Run folder: {row.run_dir or 'none'}\n\n")
        except Exception:
            bpy.data.texts.remove(text)
            raise
        _clear_history(state)
        self.report({"INFO"}, f"Archived {count} result(s) in Text: {text.name}")
        return {"FINISHED"}


class LCW_OT_cad_more_results(bpy.types.Operator):
    bl_idname = "lcw.cad_more_results"
    bl_label = "Show More CAD Results"
    bl_description = "Show five more recent CAD result records"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def execute(self, context):
        state = context.scene.lcw_cad_reconstruction
        state.results_visible = min(len(state.results), state.results_visible + 5)
        return {"FINISHED"}


class LCW_OT_cad_delete_run_files(bpy.types.Operator):
    bl_idname = "lcw.cad_delete_run_files"
    bl_label = "Delete CAD Run Files"
    bl_description = ("Permanently delete verified CAD worker folders in the current Run Folder; "
                      "keep source and output meshes. This cannot be undone")
    bl_options = {"REGISTER"}

    _timer = None
    _pending = None
    _root = None
    _deleted = 0
    _errors = None
    _window_manager = None
    _state = None

    @classmethod
    def poll(cls, context):
        return _can_manage(context)

    def invoke(self, context, _event):
        try:
            root = jobs.run_root(context.scene.lcw_cad_reconstruction, create=False)
            self._preview_count = len(run_files.find_owned_runs(root))
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not self._preview_count:
            self.report({"INFO"}, "No verified CAD run folders in the current Run Folder")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, _context):
        self.layout.label(text=f"Permanently delete {self._preview_count} CAD run folder(s)?", icon="ERROR")
        self.layout.label(text="Only verified direct children of the current Run Folder.")
        self.layout.label(text="Includes other .blend projects sharing this folder.")
        self.layout.label(text="Worker reports and logs will be lost. No undo.")
        self.layout.label(text="Source and output meshes stay in the scene.")

    def _step(self, state):
        path = self._pending.pop(0)
        try:
            run_files.delete_owned_run(self._root, path)
        except (OSError, ValueError) as exc:
            self._errors.append(f"{path.name}: {exc}")
        else:
            self._deleted += 1
            for row in state.results:
                try:
                    if row.run_dir and Path(row.run_dir).resolve() == path.resolve():
                        row.files_deleted = True
                except (OSError, RuntimeError):
                    pass
        state.cleanup_progress = f"Run files: {self._deleted} deleted | {len(self._pending)} left"

    def _finish(self, report=True):
        global ACTIVE_CLEANUP

        if self._timer is not None:
            try:
                self._window_manager.event_timer_remove(self._timer)
            except (ReferenceError, RuntimeError, ValueError):
                pass
            self._timer = None
        if self._state is not None:
            try:
                self._state.cleanup_running = False
            except ReferenceError:
                pass
        ACTIVE_CLEANUP = None
        if _before_load in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.remove(_before_load)
        if report and self._errors:
            self.report({"WARNING"}, f"Deleted {self._deleted}; {len(self._errors)} folder(s) failed. See console")
            for error in self._errors:
                print("CAD run cleanup:", error)
        elif report:
            self.report({"INFO"}, f"Deleted {self._deleted} CAD run folder(s); meshes kept")

    def execute(self, context):
        global ACTIVE_CLEANUP

        state = context.scene.lcw_cad_reconstruction
        try:
            self._root = jobs.run_root(state, create=False)
            self._pending = run_files.find_owned_runs(self._root)
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if not self._pending:
            self.report({"INFO"}, "No verified CAD run folders to delete")
            return {"CANCELLED"}
        self._deleted = 0
        self._errors = []
        self._state = state
        self._window_manager = context.window_manager
        ACTIVE_CLEANUP = self
        if _before_load not in bpy.app.handlers.load_pre:
            bpy.app.handlers.load_pre.append(_before_load)
        state.cleanup_running = True
        state.cleanup_progress = f"Run files: 0 deleted | {len(self._pending)} left"
        if bpy.app.background:
            try:
                while self._pending:
                    self._step(state)
            finally:
                self._finish()
            return {"FINISHED"}
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._state.cleanup_progress = (
                f"Run file cleanup stopped: {self._deleted} deleted | {len(self._pending)} kept"
            )
            self._finish(report=False)
            self.report({"INFO"}, "CAD run file cleanup stopped; remaining folders kept")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        state = self._state
        if self._pending:
            try:
                self._step(state)
            except Exception:
                self._finish(report=False)
                raise
        if self._pending:
            return {"RUNNING_MODAL"}
        self._finish()
        return {"FINISHED"}


CLASSES = (
    LCW_OT_cad_clear_results,
    LCW_OT_cad_archive_results,
    LCW_OT_cad_more_results,
    LCW_OT_cad_delete_run_files,
)
