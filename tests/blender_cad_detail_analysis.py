"""Independent hole budget, async analysis, source rejection and solid delivery."""
import json
import math
import sys
import tempfile
import time
from pathlib import Path

import bpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_mesh_tool.api import prepare_selected,apply_result
from LC_workflow_addon.cad_mesh_tool.detect import discover
from LC_workflow_addon.cad_mesh_tool.mesh_io import capture,fingerprint,make_mesh
from LC_workflow_addon.cad_mesh_tool.rebuild import tessellation,reconstruct
from LC_workflow_addon.cad_mesh_tool.recovery import decisions
from LC_workflow_addon.cad_mesh_tool.validate import validate,point_limits
from LC_workflow_addon.cad_mesh_tool.worker import main
from LC_workflow_addon.cad_reconstruction import jobs,analysis_jobs


def plate(name,copies=1):
    outer=np.array([[-.04,-.04],[.04,-.04],[.04,.04],[-.04,.04]])
    angle=np.arange(64)*math.tau/64
    ring=.0065*np.column_stack((np.cos(angle),np.sin(angle)))
    points,triangles=tessellation([outer,ring])
    count=len(points)
    vertices=[(x,y,z) for z in (0.,.01) for x,y in points]
    faces=[list(reversed(f)) for f in triangles]+[[count+i for i in f] for f in triangles]
    for ids,reverse in ((list(range(4)),False),(list(range(4,count)),True)):
        for a,b in zip(ids,ids[1:]+ids[:1]):
            faces.append([b,a,a+count,b+count] if reverse else [a,b,b+count,a+count])
    if copies==2:
        offset=len(vertices)
        vertices += [(x+.025,y,z+.003) for x,y,z in list(vertices)]
        faces += [[offset+i for i in f] for f in list(faces)]
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


addon.register()
try:
    state=bpy.context.scene.lcw_cad_reconstruction
    state.mode='SELECTED'
    state.hole_detail_factor=.5
    state.hole_epsilon_mm=1.
    state.epsilon_mm=.15
    options=dict(circular_holes=True,perimeter_loops=False,arcs=False,outer_cylinders=False,
                 background_cleanup=True,straight_walls=True)
    for k,v in options.items():setattr(state,k,v)
    source=plate('Dense hole')
    before=fingerprint(source)
    snapshot=capture(source)
    normal=discover(snapshot['vertices'],snapshot['faces'],.00015)
    coarse=discover(snapshot['vertices'],snapshot['faces'],.00015,.5,.001)
    assert coarse['features'][0]['segments']<normal['features'][0]['segments']
    candidate=reconstruct(snapshot,decisions(coarse['features'],options),options)
    regions=candidate['hole_deviation_regions']
    assert np.allclose(point_limits(np.array([[.035,.035,.01],[.0065,0.,.005],[0.,0.,.005]]),.00015,regions),[.00015,.001,.00015])
    mesh,origin=make_mesh(candidate,'Detail checkpoint')
    checked=validate(snapshot,mesh,origin,candidate['roles'],candidate['perimeters'],.00015,750,
                     require_reduction=False,source_to_output=candidate['source_to_candidate'],hole_deviation_regions=regions)
    assert all(checked['checks'].values()),checked['checks']
    mesh.vertices[0].co.z+=.003
    moved=validate(snapshot,mesh,origin,candidate['roles'],candidate['perimeters'],.00015,750,
                   require_reduction=False,source_to_output=candidate['source_to_candidate'],hole_deviation_regions=regions)
    assert not moved['checks']['sampled_distance']
    bpy.data.meshes.remove(mesh)
    print('CAD_HOLE_INDEPENDENT_BUDGET_OK',normal['features'][0]['segments'],coarse['features'][0]['segments'])
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        state.run_root=str(root)
        for obj in bpy.context.selected_objects:obj.select_set(False)
        source.select_set(True);bpy.context.view_layer.objects.active=source
        assert bpy.ops.lcw.cad_analyze()=={'FINISHED'}
        assert state.analysis_ready and not state.analysis_running
        row=state.analysis_lines[0]
        assert row.recommendation and row.source_hash==before
        assert bpy.ops.lcw.cad_apply_recommendation(analysis_index=0)=={'FINISHED'}
        data=json.loads(Path(row.run_dir,'analysis.json').read_text())
        assert data['holes'][0]['target']==coarse['features'][0]['segments']
        source.location.x+=.01
        try:bpy.ops.lcw.cad_apply_recommendation(analysis_index=0)
        except RuntimeError:pass
        else:raise AssertionError('Stale recommendation accepted')
        source.location.x=0.
        bpy.context.view_layer.update()
        assert fingerprint(source)==before
        print('CAD_DETAILED_ANALYSIS_RECOMMENDATION_OK')
        joined=plate('Intersecting assembly',copies=2)
        joined_hash=fingerprint(joined)
        state.separate_solids=False
        batch=jobs.CADBatch(bpy.context,[joined],root)
        while batch.step():time.sleep(.03)
        assert state.results[-1].status=='FAIL' and state.results[-1].stage=='source_geometry'
        assert 'Source geometry has' in state.results[-1].technical_reason
        assert Path(state.results[-1].run_dir,'validation_source.json').exists()
        state.separate_solids=True
        batch=jobs.CADBatch(bpy.context,[joined],root)
        assert len(batch.objects)==2
        while batch.step():time.sleep(.03)
        rows=list(state.results)[batch.row_offset:]
        assert [r.status for r in rows]==['PASS','PASS'],[(r.status,r.reason) for r in rows]
        assert all(r.source==joined and r.output is not None and r.output.data!=joined.data for r in rows)
        assert len({r.output.as_pointer() for r in rows})==2
        assert [r.output['cad_component_index'] for r in rows]==[0,1]
        assert all(json.loads(Path(r.run_dir,'profile.json').read_text())['hole_detail_factor']==.5 for r in rows)
        assert fingerprint(joined)==joined_hash
        retry=jobs.CADBatch(bpy.context,[joined],root,retry_component=1)
        assert len(retry.objects)==1 and retry.component_indices==(1,)
        retry.cancel()
        stale=jobs.CADBatch(bpy.context,[joined],root)
        joined.location.x=.02
        bpy.context.view_layer.update()
        while stale.step():time.sleep(.03)
        assert all(r.status=='FAIL' and 'partitioning' in r.reason for r in list(state.results)[stale.row_offset:])
        joined.location.x=0.
        bpy.context.view_layer.update()
        assert fingerprint(joined)==joined_hash
        print('CAD_SOURCE_INTERSECTIONS_AND_SEPARATE_SOLIDS_OK')
        analysis=analysis_jobs.CADAnalysis(bpy.context,[source,joined],root)
        while not analysis.running:assert analysis.step()
        processes=[j['process'] for j in analysis.running.values()]
        analysis.cancel()
        assert all(p.poll() is not None for p in processes)
        assert not analysis.step()
        print('CAD_ANALYSIS_CANCEL_OK')
finally:
    addon.unregister()
