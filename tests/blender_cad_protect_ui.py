"""Edit Mode protected-face operators: protect, unprotect, select, clear.

blender --background --factory-startup --python tests/blender_cad_protect_ui.py
"""
import sys
from pathlib import Path

import bmesh
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_mesh_tool.mesh_io import capture, fingerprint
from LC_workflow_addon.cad_mesh_tool.protected import ATTRIBUTE, faces_from_mesh
from LC_workflow_addon.cad_reconstruction.protection import protected_count

addon.register()
try:
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    plain = fingerprint(obj)
    coordinates = [tuple(v.co) for v in obj.data.vertices]
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)
    for face in bm.faces:
        face.select_set(face.index in (0, 2))
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.lcw.cad_protect_faces(action='PROTECT') == {'FINISHED'}
    assert protected_count(obj) == 2
    bm = bmesh.from_edit_mesh(obj.data)
    for face in bm.faces:
        face.select_set(face.index == 2)
    assert bpy.ops.lcw.cad_protect_faces(action='UNPROTECT') == {'FINISHED'}
    assert protected_count(obj) == 1
    bm = bmesh.from_edit_mesh(obj.data)
    for face in bm.faces:
        face.select_set(False)
    assert bpy.ops.lcw.cad_protect_faces(action='SELECT') == {'FINISHED'}
    bm = bmesh.from_edit_mesh(obj.data)
    assert [face.index for face in bm.faces if face.select] == [0]
    bpy.ops.object.mode_set(mode='OBJECT')
    assert faces_from_mesh(obj.data) == [0]
    assert capture(obj)['user_protected_faces'] == [0]
    assert fingerprint(obj) != plain
    assert [tuple(v.co) for v in obj.data.vertices] == coordinates, 'geometry must not change'
    assert not bpy.ops.lcw.cad_protect_faces.poll(), 'operators require Edit Mode'
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.lcw.cad_protect_faces(action='CLEAR') == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert obj.data.attributes.get(ATTRIBUTE) is None
    assert fingerprint(obj) == plain, 'clearing restores the unprotected fingerprint'
    print('PASS blender_cad_protect_ui')
finally:
    addon.unregister()
