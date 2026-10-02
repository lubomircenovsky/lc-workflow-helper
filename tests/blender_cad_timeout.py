"""Real process timeout and continued queue for Power user and advisory analysis."""
import json
import sys
import tempfile
import time
from pathlib import Path

import bpy
import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs, analysis_jobs

addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.workflow_mode = 'POWER_USER'
    state.mode = 'SELECTED'
    state.concurrent_workers = 1
    obj = bpy.data.objects['Cube']
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    bmesh.ops.triangulate(mesh, faces=list(mesh.faces))
    mesh.to_mesh(obj.data)
    mesh.free()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sleeper = root/'sleep.py'
        sleeper.write_text('import time; time.sleep(60)')
        original = jobs.subprocess.Popen

        def paused(args, **kwargs):
            args = list(args)
            args[args.index('--python')+1] = str(sleeper)
            return original(args, **kwargs)

        for batch_type in (jobs.CADBatch, analysis_jobs.CADAnalysis):
            batch = batch_type(bpy.context, [obj, obj], root)
            jobs.subprocess.Popen = paused
            try:
                batch.step()
            finally:
                jobs.subprocess.Popen = original
            job = batch.running[0]
            job['started'] -= 601
            while batch.step():
                time.sleep(.02)
            assert job['process'].poll() is not None
            assert json.loads((job['run_dir']/'timeout.json').read_text())['status'] == 'TIMED_OUT'
            assert batch.completed == 2
            if batch_type is jobs.CADBatch:
                assert state.results[0].status == 'FAIL'
                assert 'time limit' in state.results[0].reason
                assert state.results[1].output, state.results[1].reason
            else:
                assert 'time limit' in batch.rows[0].message
                assert 'error' not in json.loads(batch.rows[1].technical)
    print('CAD_TIMEOUT_POWER_ANALYSIS_OK')
finally:
    addon.unregister()
