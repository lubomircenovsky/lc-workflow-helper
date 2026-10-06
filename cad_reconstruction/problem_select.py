"""Select the source geometry that blocked a CAD result, for manual repair.

Only selection changes; the mesh itself is never modified.
"""
from __future__ import annotations

import bmesh
import bpy
from bpy.props import IntProperty

from ..cad_mesh_tool.mesh_io import fingerprint
from . import problem_faces

# Result stages whose cause can be shown on the source mesh.
INTERSECTION_STAGE = "source_geometry"
TOPOLOGY_STAGE = "preflight"
SELECTABLE_STAGES = {INTERSECTION_STAGE, TOPOLOGY_STAGE}


def can_select(item) -> bool:
    """Cheap check for panel drawing; files are verified by the operator."""
    if item.status != "FAIL" or item.source is None or item.stage not in SELECTABLE_STAGES:
        return False
    return item.stage == TOPOLOGY_STAGE or not item.files_deleted


def _enter_edit_mode(context, obj) -> None:
    if context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for other in context.selected_objects:
        other.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")


def _frame_selection(context) -> None:
    if context.area is not None and context.area.type == "VIEW_3D":
        try:
            bpy.ops.view3d.view_selected()
        except RuntimeError:
            pass


class LCW_OT_cad_select_problems(bpy.types.Operator):
    bl_idname = "lcw.cad_select_problems"
    bl_label = "Select Problem Areas"
    bl_description = (
        "Open the source in Edit Mode and select the geometry that blocked this result "
        "(intersecting faces or open/non-manifold edges) for manual repair"
    )
    bl_options = {"REGISTER", "UNDO"}

    result_index: IntProperty(default=0)

    def execute(self, context):
        rows = context.scene.lcw_cad_reconstruction.results
        if not 0 <= self.result_index < len(rows) or not can_select(rows[self.result_index]):
            self.report({"WARNING"}, "This result has no selectable problem areas")
            return {"CANCELLED"}
        item = rows[self.result_index]
        source = item.source
        if source.type != "MESH" or source.name not in context.view_layer.objects:
            self.report({"WARNING"}, "Source mesh is not in the active view layer")
            return {"CANCELLED"}
        if item.stage == INTERSECTION_STAGE:
            return self._select_intersections(context, item, source)
        return self._select_topology(context, item, source)

    def _select_intersections(self, context, item, source):
        try:
            source_hash, polygons, pairs = problem_faces.load_intersections(item.run_dir)
        except (OSError, ValueError, KeyError) as error:
            self.report({"WARNING"}, f"Cannot read problem areas: {error}")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        if fingerprint(source) != source_hash:
            self.report({"WARNING"}, "Source changed since this run; reconstruct again to refresh the problem areas")
            return {"CANCELLED"}
        if not polygons or polygons[-1] >= len(source.data.polygons):
            self.report({"WARNING"}, "Stored problem faces do not match the source mesh")
            return {"CANCELLED"}
        _enter_edit_mode(context, source)
        context.tool_settings.mesh_select_mode = (False, False, True)
        bm = bmesh.from_edit_mesh(source.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select_set(False)
        for index in polygons:
            bm.faces[index].select_set(True)
        bm.select_flush_mode()
        bmesh.update_edit_mesh(source.data, loop_triangles=False, destructive=False)
        _frame_selection(context)
        self.report({"INFO"}, f"Selected {len(polygons)} face(s) from {pairs} intersecting triangle pair(s)")
        return {"FINISHED"}

    def _select_topology(self, context, item, source):
        _enter_edit_mode(context, source)
        context.tool_settings.mesh_select_mode = (True, True, False)
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.mesh.select_non_manifold(
            extend=False, use_wire=True, use_boundary=True,
            use_multi_face=not item.preserve_nonmanifold, use_non_contiguous=True, use_verts=True,
        )
        bm = bmesh.from_edit_mesh(source.data)
        edges = sum(edge.select for edge in bm.edges)
        verts = sum(vert.select for vert in bm.verts)
        _frame_selection(context)
        if not edges and not verts:
            self.report({"INFO"}, "No open or non-manifold edges selected; check duplicate faces (Merge by Distance)")
        else:
            self.report({"INFO"}, f"Selected {edges} edge(s) and {verts} vertex(es) with open or non-manifold topology")
        return {"FINISHED"}


CLASSES = (LCW_OT_cad_select_problems,)
