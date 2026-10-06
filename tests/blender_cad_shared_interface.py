"""Separate a measured shared cap into two fully validated independent solids."""
import json
import sys
import tempfile
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_mesh_tool.geometry import topology
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint
from LC_workflow_addon.cad_reconstruction import jobs

addon.register()
try:
    faces = [[0,2,1],[0,1,3],[1,2,3],[2,0,3],
             [0,4,1],[1,4,2],[2,4,0]]
    vertices = [[0,0,0],[1,0,0],[0,1,0],[0,0,1],[0,0,-1]]
    mesh = bpy.data.meshes.new('Shared interface')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('Shared interface', mesh)
    bpy.context.scene.collection.objects.link(obj)
    before = fingerprint(obj)
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = 'SELECTED'
    state.separate_solids = True
    state.concurrent_workers = 2
    state.arcs = False
    state.outer_cylinders = False
    state.perimeter_loops = False
    with tempfile.TemporaryDirectory(prefix='cad_shared_interface_') as directory:
        batch = jobs.CADBatch(bpy.context, [obj], Path(directory))
        assert len(batch.objects) == 2
        assert batch.component_reversed_faces == ([], [0])
        while batch.step():
            time.sleep(.03)
        rows = list(state.results)
        assert len(rows) == 2
        assert all(row.geometry_status == 'PASS' for row in rows), [(row.status,row.reason) for row in rows]
        assert all(row.output is not None and row.output.data != obj.data for row in rows)
        assert fingerprint(obj) == before
        for row in rows:
            counts = topology([list(p.vertices) for p in row.output.data.polygons])
            assert not any(counts[k] for k in ('boundary','nonmanifold','winding','duplicates'))
            final = json.loads(Path(row.run_dir,'validation_final.json').read_text())
            assert all(final['checks'].values()), final['checks']
        profiles = [json.loads(Path(row.run_dir,'profile.json').read_text()) for row in rows]
        assert profiles[1]['shared_interface_reversed_faces'] == [0]
        assert [profile['source_hash'] for profile in profiles] == [before,before]
    from LC_workflow_addon.tests.test_cad_source_repair import collinear_fixture
    fixture=collinear_fixture()
    repair_mesh=bpy.data.meshes.new('Exact collinear strip')
    repair_mesh.from_pydata(fixture['vertices'],[],fixture['faces']);repair_mesh.update()
    repair_obj=bpy.data.objects.new('Exact collinear strip',repair_mesh)
    bpy.context.scene.collection.objects.link(repair_obj)
    original_hash=fingerprint(repair_obj)
    state.separate_solids=False
    with tempfile.TemporaryDirectory(prefix='cad_collinear_') as directory:
        batch=jobs.CADBatch(bpy.context,[repair_obj],Path(directory))
        while batch.step():time.sleep(.03)
        row=state.results[-1]
        assert row.geometry_status=='PASS',(row.status,row.reason)
        assert fingerprint(repair_obj)==original_hash
        report=json.loads(Path(row.run_dir,'source_repair.json').read_text())
        assert len(report['removed_zero_area_faces'])==2
        final=json.loads(Path(row.run_dir,'validation_final.json').read_text())
        assert all(final['checks'].values()),final['checks']
        assert final['before']['t']==len(fixture['faces'])
        assert 'Source cleanup' in Path(row.run_dir,'REPORT.md').read_text()
    print('CAD_EXACT_COLLINEAR_SOURCE_REPAIR_OK')
    print('CAD_SHARED_INTERFACE_OK')
finally:
    addon.unregister()
print('PASS blender_cad_shared_interface')
