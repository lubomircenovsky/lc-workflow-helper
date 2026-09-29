"""Create CAD-aware UV maps without changing authored seams or existing UVs."""

from __future__ import annotations

import math

import bpy

from .uv_prep_core import plan_uv_cuts


def _source_data(obj):
    mesh = obj.data
    if not mesh.polygons:
        raise ValueError("Mesh has no faces")
    if any(not math.isfinite(face.area) or face.area <= 0.0 for face in mesh.polygons):
        raise ValueError("Mesh contains a zero-area face")
    transform = obj.matrix_world
    normal_matrix = transform.to_3x3().inverted_safe().transposed()
    vertices = tuple(tuple(transform @ vertex.co) for vertex in mesh.vertices)
    if any(not all(math.isfinite(value) for value in vertex) for vertex in vertices):
        raise ValueError("Mesh has non-finite transformed vertex coordinates")
    faces = tuple(tuple(face.vertices) for face in mesh.polygons)
    normals = []
    for face in mesh.polygons:
        direction = normal_matrix @ face.normal
        if direction.length_squared == 0.0:
            raise ValueError("Mesh contains a face without a valid normal")
        direction.normalize()
        normals.append(tuple(direction))
    materials = tuple(face.material_index for face in mesh.polygons)
    return vertices, faces, tuple(normals), materials


def _validate_working_uv(source, working, values):
    if (len(source.vertices), len(source.edges), len(source.polygons), len(source.loops)) != (
        len(working.vertices), len(working.edges), len(working.polygons), len(working.loops)
    ):
        raise ValueError("Unwrap unexpectedly changed mesh topology")
    if any(tuple(a.vertices) != tuple(b.vertices)
           for a, b in zip(source.polygons, working.polygons)):
        raise ValueError("Unwrap changed polygon order")
    if any(a.vertex_index != b.vertex_index
           for a, b in zip(source.loops, working.loops)):
        raise ValueError("Unwrap changed loop order")
    if len(values) != len(source.loops):
        raise ValueError("Unwrap did not produce UVs for every loop")
    if any(not all(math.isfinite(value) and -1e-5 <= value <= 1.00001 for value in uv)
           for uv in values):
        raise ValueError("UVs are non-finite or outside the 0-1 tile")
    for face in source.polygons:
        points = [values[index] for index in face.loop_indices]
        area = abs(sum(a[0] * b[1] - b[0] * a[1]
                       for a, b in zip(points, points[1:] + points[:1]))) * 0.5
        if area <= 1e-14:
            raise ValueError(f"Face {face.index} has a collapsed UV area")


def _working_uv(context, obj, plan, margin):
    source = obj.data
    working = source.copy()
    temporary = None
    selected = tuple(context.selected_objects)
    active = context.view_layer.objects.active
    original_uv_sync = context.scene.tool_settings.use_uv_select_sync
    try:
        temporary = bpy.data.objects.new("LCW UV Prep Temporary", working)
        context.scene.collection.objects.link(temporary)
        for vertex in working.vertices:
            vertex.co = obj.matrix_world @ source.vertices[vertex.index].co
        cuts = plan.cuts
        for edge in working.edges:
            edge.use_seam = tuple(sorted(edge.vertices)) in cuts
        uv_layer = working.uv_layers.new(name="LCW UV Prep Working", do_init=False)
        if uv_layer is None:
            raise ValueError("Blender cannot add another UV map to this mesh")
        working.uv_layers.active = uv_layer
        working_layer_name = uv_layer.name
        working.update()
        for item in selected:
            item.select_set(False)
        temporary.select_set(True)
        context.view_layer.objects.active = temporary
        context.scene.tool_settings.use_uv_select_sync = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        if bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.0) != {"FINISHED"}:
            raise ValueError("Blender could not unwrap the planned islands")
        if bpy.ops.uv.pack_islands(rotate=True, margin_method="ADD", margin=margin) != {"FINISHED"}:
            raise ValueError("Blender could not pack the UV islands")
        bpy.ops.object.mode_set(mode="OBJECT")
        layer_after_edit = working.uv_layers.get(working_layer_name)
        if layer_after_edit is None:
            raise ValueError("Blender removed the working UV layer")
        values = tuple(tuple(item.uv) for item in layer_after_edit.data)
        _validate_working_uv(source, working, values)
        return values
    finally:
        try:
            if temporary is not None and context.view_layer.objects.active == temporary:
                if temporary.mode != "OBJECT":
                    bpy.ops.object.mode_set(mode="OBJECT")
        finally:
            context.scene.tool_settings.use_uv_select_sync = original_uv_sync
            for item in tuple(context.selected_objects):
                item.select_set(False)
            if temporary is not None:
                bpy.data.objects.remove(temporary, do_unlink=True)
            bpy.data.meshes.remove(working)
            for item in selected:
                if item.name in bpy.data.objects:
                    item.select_set(True)
            if active is not None and active.name in bpy.data.objects:
                context.view_layer.objects.active = active


def _add_uv_map(obj, name, values):
    source = obj.data
    independent = source.users > 1
    destination = source.copy() if independent else source
    before_active = destination.uv_layers.active_index if destination.uv_layers else None
    active_render = next((layer.name for layer in destination.uv_layers
                          if layer.active_render), None)
    layer = None
    try:
        layer = destination.uv_layers.new(name=name, do_init=False)
        if layer is None:
            raise ValueError("Blender cannot add another UV map to this mesh")
        for index, uv in enumerate(values):
            layer.data[index].uv = uv
        if active_render is not None:
            destination.uv_layers[active_render].active_render = True
        destination.uv_layers.active = layer
        if independent:
            obj.data = destination
        return layer.name, independent
    except Exception:
        if independent:
            bpy.data.meshes.remove(destination)
        elif layer is not None:
            destination.uv_layers.remove(layer)
            if before_active is not None:
                destination.uv_layers.active_index = before_active
            if active_render is not None:
                destination.uv_layers[active_render].active_render = True
        raise


def prepare_object(context, obj, name, angle, margin):
    if obj.type != "MESH" or obj.library is not None or obj.data.library is not None:
        raise ValueError("Requires an editable local mesh object")
    source_data = _source_data(obj)
    plan = plan_uv_cuts(*source_data, angle_degrees=angle)
    values = _working_uv(context, obj, plan, margin)
    layer_name, single_user_copy = _add_uv_map(obj, name, values)
    return layer_name, plan, single_user_copy


class LCW_OT_cad_prepare_uv(bpy.types.Operator):
    bl_idname = "lcw.cad_prepare_uv"
    bl_label = "Generate CAD-Aware UV"
    bl_description = "Create a new packed UV map on selected meshes without changing existing UVs or mesh seams"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT" and context.scene is not None
                and any(obj.type == "MESH" for obj in context.selected_objects))

    def execute(self, context):
        from . import jobs

        state = context.scene.lcw_cad_reconstruction
        if jobs.ACTIVE_JOB is not None or state.cleanup_running:
            self.report({"ERROR"}, "Wait for the CAD job to finish")
            return {"CANCELLED"}
        selected = tuple(obj for obj in context.selected_objects if obj.type == "MESH")
        succeeded = failed = 0
        failures = []
        for obj in selected:
            try:
                _layer, _plan, copied = prepare_object(
                    context, obj, state.uv_prep_map_name,
                    state.uv_prep_angle_degrees, state.uv_prep_margin,
                )
                succeeded += 1
                if copied:
                    self.report({"INFO"}, f"{obj.name}: shared mesh made single-user")
            except Exception as exc:
                failed += 1
                failures.append(f"{obj.name}: {exc}")
        state.uv_prep_summary = f"{succeeded} UV map(s) created, {failed} skipped"
        if failures:
            state.uv_prep_summary += f"; {failures[0]}"
            self.report({"WARNING"}, "; ".join(failures[:2]))
        else:
            self.report({"INFO"}, state.uv_prep_summary)
        return {"FINISHED"} if succeeded else {"CANCELLED"}


class LCW_OT_cad_analyze_uv(bpy.types.Operator):
    bl_idname = "lcw.cad_analyze_uv"
    bl_label = "Analyze CAD-Aware UV"
    bl_description = "Estimate geometric UV cuts on selected meshes without changing any data"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return LCW_OT_cad_prepare_uv.poll(context)

    def execute(self, context):
        from . import jobs

        state = context.scene.lcw_cad_reconstruction
        if jobs.ACTIVE_JOB is not None or state.cleanup_running:
            self.report({"ERROR"}, "Wait for the CAD job to finish")
            return {"CANCELLED"}
        analyzed = regions = cuts = slits = 0
        failures = []
        for obj in context.selected_objects:
            if obj.type != "MESH":
                continue
            try:
                if obj.library is not None or obj.data.library is not None:
                    raise ValueError("Requires an editable local mesh object")
                plan = plan_uv_cuts(*_source_data(obj),
                                    angle_degrees=state.uv_prep_angle_degrees)
                analyzed += 1
                regions += plan.face_regions
                cuts += plan.angle_cuts + plan.material_cuts
                slits += plan.annulus_slits
            except Exception as exc:
                failures.append(f"{obj.name}: {exc}")
        state.uv_prep_summary = (
            f"{analyzed} mesh(es): {regions} regions, {cuts} fold/material cuts, "
            f"{slits} round-wall slits; {len(failures)} blocked"
        )
        self.report({"WARNING"} if failures else {"INFO"},
                    "; ".join(failures[:2]) if failures else state.uv_prep_summary)
        return {"FINISHED"} if analyzed else {"CANCELLED"}


CLASSES = (LCW_OT_cad_prepare_uv, LCW_OT_cad_analyze_uv)
