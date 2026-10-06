"""Auto integration: mode isolation, solid failures, final ranking and import integrity."""
import json
import math
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import auto_jobs, settings, jobs, operators
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint
from LC_workflow_addon.cad_mesh_tool.rebuild import tessellation


def fixture():
    outer = np.array([[-.04,-.04],[.04,-.04],[.04,.04],[-.04,.04]])
    theta = np.arange(32)*math.tau/32
    hole = .0065*np.column_stack((np.cos(theta),np.sin(theta)))
    points, triangles = tessellation([outer,hole]);n=len(points)
    vertices=[(x,y,z) for z in (0,.01) for x,y in points]
    faces=[f[::-1] for f in triangles]+[[i+n for i in f] for f in triangles]
    for ring, reverse in ((list(range(4)),False),(list(range(4,n)),True)):
        for a,b in zip(ring,ring[1:]+ring[:1]):
            faces.append([b,a,a+n,b+n] if reverse else [a,b,b+n,a+n])
    offset=len(vertices);vertices.extend([(1,0,0),(1.1,0,0),(1, .1,0)])
    faces.append([offset,offset+1,offset+2])
    mesh=bpy.data.meshes.new('Auto fixture');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('Auto fixture',mesh);bpy.context.scene.collection.objects.link(obj)
    return obj


addon.register()
try:
    state=bpy.context.scene.lcw_cad_reconstruction
    assert state.workflow_mode=='AUTO'
    assert state.worker_timeout_minutes == 10
    legacy=bpy.data.scenes.new('Legacy')
    legacy.lcw_cad_reconstruction.epsilon_mm=1.2
    legacy.lcw_cad_reconstruction.arcs=False
    assert math.isclose(legacy.lcw_cad_reconstruction.epsilon_mm,1.2,rel_tol=1e-6)
    settings.migrate_workflows(None)
    assert legacy.lcw_cad_reconstruction.workflow_mode=='POWER_USER'
    assert math.isclose(legacy.lcw_cad_reconstruction.epsilon_mm,1.2,rel_tol=1e-6)
    state.epsilon_mm=9.;state.hole_detail_factor=2.;state.arcs=False
    state.normal_override=True;state.normal_risk_ack=False
    state.auto_epsilon_mm=1.5;state.auto_hole_detail_factor=.5
    state.auto_hole_epsilon_mm=1.5;state.auto_perimeter_clearance_mm=1.5
    state.mode='SELECTED';state.concurrent_workers=1
    obj=fixture();before=fingerprint(obj)
    with tempfile.TemporaryDirectory() as temp:
        state.run_root=temp
        batch=auto_jobs.AutoBatch(bpy.context,[obj],Path(temp))
        while batch.step():time.sleep(.02)
        assert len(state.results)==2
        rows=list(state.results)
        good=next(r for r in rows if r.output)
        bad=next(r for r in rows if not r.output)
        assert good.status=='PASS' and bad.status=='FAIL',[(r.status,r.reason) for r in rows]
        report=json.loads((Path(good.auto_run_dir)/'auto_manifest.json').read_text())
        body=next(b for b in report['bodies'] if b['winner'])
        assert body['triangles']==min(t['triangles'] for t in body['trials'] if t['status']!='FAIL')
        assert 2<=len(body['trials'])<=4
        for trial in body['trials']:
            profile=json.loads((Path(good.auto_run_dir)/trial['path']/'profile.json').read_text())
            assert profile['epsilon_m']==.0015 and profile['hole_detail_factor']==.5
            assert profile['straight_walls']['normal_limit_deg'] is None
        assert fingerprint(obj)==before and state.epsilon_mm==9. and not state.arcs
        state.workflow_mode='POWER_USER';state.workflow_mode='AUTO'
        assert state.hole_detail_factor==2. and state.auto_hole_detail_factor==.5
        count=len(state.results)
        pending=auto_jobs.AutoBatch(bpy.context,[obj],Path(temp));pending.cancel()
        assert len(state.results)==count
        # Cancel a real running child, retaining previous completed rows.
        pending=auto_jobs.AutoBatch(bpy.context,[obj],Path(temp))
        pending.step();process=pending.running[0]['process'];pending.cancel()
        assert process.poll() is not None and len(state.results)==count
        # Pause the second variant in a real child. The watchdog must keep the
        # validated first variant and continue the next source in the queue.
        wrapper = Path(temp)/'slow_worker.py'
        wrapper.write_text('''import sys, time
from pathlib import Path
sys.path.insert(0, ROOT)
from cad_mesh_tool import auto_worker
original = auto_worker.run_variant
calls = 0
def slow(*args):
    global calls
    calls += 1
    if calls == 2:time.sleep(60)
    return original(*args)
auto_worker.run_variant = slow
auto_worker.main(Path(sys.argv[sys.argv.index('--')+1]))
'''.replace('ROOT', repr(str(Path(__file__).resolve().parents[1]))))
        original_popen = auto_jobs.subprocess.Popen
        def slow_popen(args, **kwargs):
            args = list(args)
            args[args.index('--python')+1] = str(wrapper)
            return original_popen(args, **kwargs)
        timed = auto_jobs.AutoBatch(bpy.context,[obj,obj],Path(temp))
        auto_jobs.subprocess.Popen = slow_popen
        try:timed.step()
        finally:auto_jobs.subprocess.Popen = original_popen
        job = timed.running[0]
        deadline = time.monotonic()+50
        while time.monotonic() < deadline:
            path = job['run_dir']/'auto_manifest.json'
            if path.exists() and json.loads(path.read_text()).get('active_body',{}).get('winner'):break
            time.sleep(.02)
        else:raise AssertionError('Validated checkpoint was not published')
        job['started'] -= 601
        timed.timeout_seconds = 0
        timed._stop_expired_workers()
        assert job['process'].poll() is None  # zero disables the limit
        timed.timeout_seconds = 600
        while timed.step():time.sleep(.02)
        assert job['process'].poll() is not None
        assert (job['run_dir']/'timeout.json').exists()
        timed_rows=list(state.results)[count:]
        assert len(timed_rows)==4,[(r.status,r.reason) for r in timed_rows]
        assert any(r.status=='REVIEW' and r.output and 'Time limit' in r.reason for r in timed_rows)
        assert any(r.status=='PASS' and r.output for r in timed_rows)
        assert sum(r.status=='FAIL' for r in timed_rows)==2
        for interruption in ('cancel', 'crash'):
            offset=len(state.results)
            pending=auto_jobs.AutoBatch(bpy.context,[obj],Path(temp))
            auto_jobs.subprocess.Popen = slow_popen
            try:pending.step()
            finally:auto_jobs.subprocess.Popen = original_popen
            child=pending.running[0]
            deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                checkpoint=child['run_dir']/'auto_manifest.json'
                if checkpoint.exists() and json.loads(checkpoint.read_text()).get('active_body',{}).get('winner'):break
                time.sleep(.02)
            else:raise AssertionError('No checkpoint before interruption')
            if interruption=='cancel':pending.cancel()
            else:
                child['process'].kill();child['process'].wait()
                while pending.step():time.sleep(.02)
            saved=list(state.results)[offset:]
            assert any(r.output and r.status=='REVIEW' for r in saved), interruption
            assert child['process'].poll() is not None
        count=len(state.results)
        retry_index=next(i for i,r in enumerate(state.results) if r.status=='REVIEW' and r.output)
        retry=SimpleNamespace(retry_index=retry_index, preserve_nonmanifold=False)
        state.workflow_mode='POWER_USER'
        operators.LCW_OT_cad_reconstruct._start(retry,bpy.context)
        assert isinstance(retry._job,auto_jobs.AutoBatch)
        assert retry._job.retry_component==state.results[retry_index].component_index
        retry._job.cancel();jobs.ACTIVE_JOB=None;state.running=False
        state.workflow_mode='AUTO'
        # Finish worker but change the live source before its first import.
        changed=auto_jobs.AutoBatch(bpy.context,[obj],Path(temp));changed.step()
        process=changed.running[0]['process']
        while process.poll() is None:time.sleep(.05)
        output_count=len(bpy.data.objects)
        obj.data.vertices[0].co.x+=.001
        try:operators.LCW_OT_cad_reconstruct._start(retry,bpy.context)
        except ValueError as error:assert 'Source changed' in str(error)
        else:raise AssertionError('Retry accepted a changed source')
        changed._finish_worker(0)
        assert len(bpy.data.objects)==output_count
        new_rows=list(state.results)[count:]
        # The source's second solid is a separate queued work item that never started.
        assert not any(r.output for r in new_rows)
        started=[r for r in new_rows if r.status!='PENDING']
        assert started and all(r.status=='FAIL' for r in started),[(r.status,r.reason) for r in new_rows]
    print('CAD_AUTO_INTEGRATION_OK')
finally:addon.unregister()
