"""Viewport-only status wireframe for generated CAD results."""

from __future__ import annotations

import bpy

from .jobs import COLORS


_enabled_spaces = set()
_handler = None
_batches = {}


def is_enabled(space):
    return space is not None and space.as_pointer() in _enabled_spaces


def _mesh_batch(mesh, shader):
    import gpu_extras.batch

    key = mesh.as_pointer()
    batch = _batches.get(key)
    if batch is None:
        positions = [tuple(vertex.co) for vertex in mesh.vertices]
        edges = [tuple(edge.vertices) for edge in mesh.edges]
        batch = gpu_extras.batch.batch_for_shader(
            shader, "LINES", {"pos": positions}, indices=edges
        )
        _batches[key] = batch
    return batch


def _status_objects(state):
    for row in state.results:
        obj = row.output
        if (row.status in COLORS and obj is not None and obj.type == "MESH"
                and obj.get("lcw_cad_run_id") and obj.visible_get()):
            yield obj, COLORS[row.status]


def _draw():
    import gpu

    context = bpy.context
    space = context.space_data
    if not is_enabled(space) or context.scene is None:
        return
    state = getattr(context.scene, "lcw_cad_reconstruction", None)
    if state is None:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        for obj, color in _status_objects(state):
            gpu.matrix.push()
            try:
                gpu.matrix.multiply_matrix(obj.matrix_world)
                shader.bind()
                shader.uniform_float("color", color)
                _mesh_batch(obj.data, shader).draw(shader)
            finally:
                gpu.matrix.pop()
    finally:
        gpu.state.depth_test_set("NONE")


def _mesh_updated(_scene, depsgraph):
    if any(isinstance(update.id, bpy.types.Mesh) for update in depsgraph.updates):
        _batches.clear()


def _stop():
    global _handler

    if _handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    if _mesh_updated in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_mesh_updated)
    if _loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_loaded)
    _batches.clear()


@bpy.app.handlers.persistent
def _loaded(_dummy):
    clear()


def show(space):
    global _handler

    key = space.as_pointer()
    _enabled_spaces.add(key)
    if _handler is None:
        try:
            _handler = bpy.types.SpaceView3D.draw_handler_add(
                _draw, (), "WINDOW", "POST_VIEW"
            )
        except Exception:
            _enabled_spaces.discard(key)
            raise
        bpy.app.handlers.depsgraph_update_post.append(_mesh_updated)
        bpy.app.handlers.load_post.append(_loaded)


def hide(space):
    _enabled_spaces.discard(space.as_pointer())
    if not _enabled_spaces:
        _stop()


def clear():
    _enabled_spaces.clear()
    _stop()
