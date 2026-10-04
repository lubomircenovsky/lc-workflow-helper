"""Transient Windows report locks defer polling; persistent locks isolate one item."""
import io
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import auto_jobs
from LC_workflow_addon.cad_mesh_tool.api import code_hash
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint


addon.register()
try:
    state = bpy.context.scene.lcw_cad_reconstruction
    state.mode = 'SELECTED'
    source = bpy.context.active_object
    before = fingerprint(source)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        report = root / 'auto_manifest.json'
        report.write_text(json.dumps(dict(complete=True, source_hash=before,
            code_hash=code_hash(), bodies=[dict(component_index=0, status='FAIL',
            winner=None, reason='Deliberately blocked fixture')], partitions=[{}])))
        (root / 'worker.log').write_text('')

        def prepared():
            batch = auto_jobs.AutoBatch(bpy.context, [source, source], root)
            batch.next_index = 1
            job = dict(index=0, process=SimpleNamespace(poll=lambda: 0),
                       log=io.StringIO(), run_dir=root, imported=set(),
                       source_hash=before, log_position=0, phase='Done',
                       started=time.perf_counter())
            batch.running[0] = job
            return batch, job

        original = Path.read_text

        def locked(path, *args, **kwargs):
            if path == report:
                raise PermissionError('Injected Windows sharing violation')
            return original(path, *args, **kwargs)

        batch, job = prepared()
        with patch.object(Path, 'read_text', locked):
            batch._read_worker_progress(job)
            assert batch.step() and 0 in batch.running
            assert batch.completed == 0 and not batch.cancelled
        batch._finish_worker(0)
        assert batch.completed == 1 and not batch.running
        assert batch._row(0).reason == 'Deliberately blocked fixture'

        batch, job = prepared()
        batch._row(0).status = 'PASS'
        batch._row(0).output = source
        job['imported'].add(0)
        rows_before = len(state.results)
        with patch.object(Path, 'read_text', locked):
            batch._finish_worker(0)
            job['report_blocked_since'] -= 6.
            batch._finish_worker(0)
        assert batch.completed == 1 and not batch.running and not batch.cancelled
        assert len(state.results) == rows_before + 1
        assert batch._row(0).status == 'PASS' and batch._row(0).output == source
        assert state.results[-1].status == 'FAIL'
        assert 'remained inaccessible' in state.results[-1].reason
        assert batch._row(1).status == 'PENDING'  # Next source remains available.
        batch, job = prepared()
        winner = root / 'winner'
        winner.mkdir()
        warning = 'Original non-manifold junction preserved. 3 sharp edge(s) changed; review shading.'
        (winner / 'manifest.json').write_text(json.dumps(dict(
            geometry_status='PASS', partial=True, summary=warning, result_sha256='fixture')))
        report.write_text(json.dumps(dict(complete=True, source_hash=before,
            code_hash=code_hash(), partitions=[{}], bodies=[dict(
                component_index=0, status='REVIEW', winner='winner',
                result_sha256='fixture', reason='Lowest final triangle count.',
                selected_variant='full', before=12, triangles=12,
                accepted=1, detected=1, reduced=0, untreated=[], guarded=True)])))
        # Geometry import has independent integration coverage. This fixture
        # isolates what the real RNA result row presents to the user.
        with patch.object(auto_jobs.jobs, '_import_result', return_value=source):
            batch._finish_worker(0)
        assert warning in batch._row(0).reason
        assert 'Lowest final triangle count.' in batch._row(0).reason
        assert warning in batch._row(0).summary
        assert fingerprint(source) == before
    print('CAD_AUTO_REPORT_LOCK_OK', bpy.app.version_string)
finally:
    addon.unregister()
