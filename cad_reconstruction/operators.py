from __future__ import annotations

import time
import json
import tempfile
from pathlib import Path

import bpy
from bpy.props import BoolProperty, IntProperty

from . import jobs, status_overlay, ui_text, analysis_jobs


class LCW_OT_cad_analyze(bpy.types.Operator):
    bl_idname = "lcw.cad_analyze"
    bl_label = "Analyze CAD Inputs"
    bl_description = "Check topology, source intersections and hole detail; screen operation profiles in external workers without modifying source meshes"
    bl_options = {"REGISTER"}

    _timer = None
    _job = None

    @classmethod
    def poll(cls, context):
        return (context.scene is not None and context.mode=='OBJECT' and jobs.ACTIVE_JOB is None
                and analysis_jobs.ACTIVE_ANALYSIS is None and not context.scene.lcw_cad_reconstruction.cleanup_running)

    def execute(self, context):
        state = context.scene.lcw_cad_reconstruction
        try:
            objects = jobs.sources(context, state)
            issues = jobs.preflight_globals(context,state)
            if issues:raise ValueError('; '.join(issues))
            root=(Path(tempfile.gettempdir())/'lcw_cad_analysis' if state.run_root.startswith('//') and not bpy.data.filepath
                  else jobs.run_root(state))
            root.mkdir(parents=True,exist_ok=True)
        except Exception as exc:
            self.report({"ERROR"}, ui_text.analysis_issue(str(exc)))
            return {"CANCELLED"}
        state.analysis_lines.clear()
        state.analysis_ready=False
        state.analysis_running=True
        self._job=analysis_jobs.CADAnalysis(context,objects,root)
        analysis_jobs.ACTIVE_ANALYSIS=self._job
        if bpy.app.background:
            try:
                while self._job.step():time.sleep(.05)
            except Exception:
                self._job.cancel()
                raise
            finally:self._finish(context)
            return {'FINISHED'}
        self._timer=context.window_manager.event_timer_add(.3,window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        if event.type=='ESC':self._job.cancel()
        if event.type!='TIMER':return {'PASS_THROUGH'}
        try:active=self._job.step()
        except Exception as error:
            self._job.cancel()
            self.report({'ERROR'},f'CAD analysis stopped: {error}')
            active=False
        if active:return {'RUNNING_MODAL'}
        self._finish(context)
        return {'CANCELLED'} if self._job.cancelled else {'FINISHED'}

    def _finish(self,context):
        self._job.scene.lcw_cad_reconstruction.analysis_running=False
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer=None
        analysis_jobs.ACTIVE_ANALYSIS=None


class LCW_OT_cad_apply_recommendation(bpy.types.Operator):
    bl_idname='lcw.cad_apply_recommendation'
    bl_label='Use Suggested CAD Settings'
    bl_description='Apply this object\'s screened options to the shared controls; input selection stays unchanged'
    bl_options={'REGISTER','UNDO'}
    analysis_index: IntProperty(default=0,min=0)

    @classmethod
    def poll(cls,context):
        return (context.scene is not None and jobs.ACTIVE_JOB is None
                and analysis_jobs.ACTIVE_ANALYSIS is None and not context.scene.lcw_cad_reconstruction.cleanup_running)

    def execute(self,context):
        state=context.scene.lcw_cad_reconstruction
        if self.analysis_index>=len(state.analysis_lines):return {'CANCELLED'}
        row=state.analysis_lines[self.analysis_index]
        from ..cad_mesh_tool.mesh_io import fingerprint
        if row.source is None or fingerprint(row.source)!=row.source_hash:
            self.report({'ERROR'},'Source changed; analyze again before applying recommendations')
            return {'CANCELLED'}
        try:
            options=json.loads(row.recommendation)
            from ..cad_mesh_tool.operations import DEFAULTS
            allowed=set(DEFAULTS)|{'separate_solids','preserve_curve_segmentation'}
            if not isinstance(options,dict) or any(k not in allowed or not isinstance(v,bool) for k,v in options.items()):
                raise ValueError('Invalid recommended settings')
            for key,value in options.items():setattr(state,key,value)
        except (ValueError,TypeError) as error:
            self.report({'ERROR'},str(error))
            return {'CANCELLED'}
        self.report({'INFO'},f'Applied shared options suggested for {row.source.name}; select that source to run them')
        return {'FINISHED'}


class LCW_OT_cad_open_analysis(bpy.types.Operator):
    bl_idname = 'lcw.cad_open_analysis'
    bl_label = 'Open CAD Analysis Files'
    bl_description = 'Open source intersection pairs, screened profile checks and the analysis report'
    analysis_index: IntProperty(default=0, min=0)

    def execute(self, context):
        rows = context.scene.lcw_cad_reconstruction.analysis_lines
        if self.analysis_index >= len(rows):
            return {'CANCELLED'}
        path = Path(rows[self.analysis_index].run_dir)
        if not rows[self.analysis_index].run_dir or not path.is_dir():
            self.report({'WARNING'}, 'Analysis files no longer exist')
            return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=str(path))
        return {'FINISHED'}


class LCW_OT_cad_reconstruct(bpy.types.Operator):
    bl_idname = "lcw.cad_reconstruct"
    bl_label = "Reconstruct CAD Meshes"
    bl_description = "Reconstruct selected CAD operations; source meshes stay unchanged"
    bl_options = {"REGISTER"}

    retry_index: IntProperty(default=-1)
    preserve_nonmanifold: BoolProperty(default=False, options={"HIDDEN"})
    _timer = None
    _job = None

    @classmethod
    def poll(cls, context):
        return (context.scene is not None and context.mode == "OBJECT"
                and jobs.ACTIVE_JOB is None
                and analysis_jobs.ACTIVE_ANALYSIS is None
                and not context.scene.lcw_cad_reconstruction.cleanup_running)

    @classmethod
    def description(cls, _context, properties):
        if getattr(properties, "preserve_nonmanifold", False):
            return ("Try safe regions of a non-manifold mesh. Bad edges stay unchanged; "
                    "may take minutes. Output needs manual review. Source stays unchanged")
        return cls.bl_description

    def _start(self, context):
        state = context.scene.lcw_cad_reconstruction
        source = None
        retry_component = None
        if self.retry_index >= 0:
            if self.retry_index >= len(state.results):
                raise ValueError("Retry result no longer exists")
            row = state.results[self.retry_index]
            if row.status == "PASS" or row.source is None:
                raise ValueError("Retry requires a failed source object")
            source = row.source
            if state.separate_solids and row.component_index>=0:
                retry_component=row.component_index
            if row.preserve_nonmanifold:
                self.preserve_nonmanifold = True
        objects = jobs.sources(context, state, source)
        issues = jobs.preflight_globals(context, state)
        if issues:
            raise ValueError("Preflight: " + "; ".join(issues[:3]))
        object_issues = [jobs.preflight_object(obj, jobs.guarded_strategy(obj,self.preserve_nonmanifold))
                         for obj in objects]
        root = jobs.run_root(state)
        self._job = jobs.CADBatch(context, objects, root,
                                  preserve_nonmanifold=self.preserve_nonmanifold,
                                  object_issues=object_issues,retry_component=retry_component)
        jobs.ACTIVE_JOB = self._job
        state.running = True
        state.progress = f"Queued {len(self._job.objects)} CAD work item(s)"

    def invoke(self, context, event):
        state = context.scene.lcw_cad_reconstruction
        if 0 <= self.retry_index < len(state.results) and state.results[self.retry_index].preserve_nonmanifold:
            self.preserve_nonmanifold = True
        if state.concurrent_workers >= 8:
            return context.window_manager.invoke_props_dialog(self, width=420)
        if state.normal_override:
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def draw(self, context):
        if context.scene.lcw_cad_reconstruction.concurrent_workers >= 8:
            self.layout.label(text="Many Blender workers can exhaust RAM. Continue?", icon="ERROR")
        if self.preserve_nonmanifold:
            col = self.layout.column()
            col.label(text="Existing non-manifold junctions will remain unchanged.", icon="ERROR")
            col.label(text="Only safely isolated geometry can be reconstructed.")
            col.label(text="Results require manual review; sources are never modified.")
            if context.scene.lcw_cad_reconstruction.normal_override:
                col.label(text="Manual normal validation is also enabled.", icon="ERROR")

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
            except Exception:
                self._job.cancel()
                raise
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
        return jobs.ACTIVE_JOB is not None or analysis_jobs.ACTIVE_ANALYSIS is not None

    def execute(self, context):
        if jobs.ACTIVE_JOB is not None:jobs.ACTIVE_JOB.cancel()
        if analysis_jobs.ACTIVE_ANALYSIS is not None:analysis_jobs.ACTIVE_ANALYSIS.cancel()
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
    bl_description = "Temporarily show CAD status colors via Object Color; save this viewport's shading and CAD result colors"

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def execute(self, context):
        status_overlay.show(context.space_data, context.scene.lcw_cad_reconstruction)
        context.area.tag_redraw()
        return {"FINISHED"}


class LCW_OT_cad_hide_object_colors(bpy.types.Operator):
    bl_idname = "lcw.cad_hide_object_colors"
    bl_label = "Hide CAD Status Colors"
    bl_description = "Restore previous shading in all CAD-colored viewports and restore the original CAD result colors"

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
    LCW_OT_cad_apply_recommendation,
    LCW_OT_cad_open_analysis,
    LCW_OT_cad_reconstruct,
    LCW_OT_cad_cancel,
    LCW_OT_cad_select_source,
    LCW_OT_cad_object_colors,
    LCW_OT_cad_hide_object_colors,
    LCW_OT_cad_open_run,
)
