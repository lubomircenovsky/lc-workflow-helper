"""Auto batch adapter: light live capture, external planning and incremental import."""
import json
import math
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import bpy
from ..cad_mesh_tool import __version__
from ..cad_mesh_tool.api import code_hash
from ..cad_mesh_tool.auto_policy import completed_bodies
from ..cad_mesh_tool.mesh_io import capture, fingerprint
from . import jobs


def settings(state):
    values = dict(epsilon_m=state.auto_epsilon_mm/1000,
                  hole_detail_factor=state.auto_hole_detail_factor,
                  hole_epsilon_mm=state.auto_hole_epsilon_mm,
                  perimeter_clearance_mm=state.auto_perimeter_clearance_mm)
    if not all(math.isfinite(value) for value in values.values()):raise ValueError('Auto values must be finite')
    if values['epsilon_m'] <= 0 or not .1 <= values['hole_detail_factor'] <= 2:
        raise ValueError('Invalid Auto deviation or hole detail')
    if min(values['hole_epsilon_mm'], values['perimeter_clearance_mm']) < 0:
        raise ValueError('Auto clearances and hole deviation must not be negative')
    return values


def run_root(state):
    if state.run_root.startswith('//') and not bpy.data.filepath:
        root = Path(tempfile.gettempdir())/'lcw_cad_auto_runs'
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()
    return jobs.run_root(state)


class AutoBatch(jobs.CADBatch):
    def __init__(self, context, objects, root, retry_component=None):
        self.scene = context.scene
        state = self.scene.lcw_cad_reconstruction
        self.controls = settings(state)
        self.objects = tuple(objects)
        self.root = root
        self.retry_component = retry_component
        self.max_workers = min(max(int(state.concurrent_workers), 1), 16)
        self.timeout_seconds = jobs.worker_timeout_seconds(state)
        self.next_index = self.completed = 0
        self.running = {}
        self.cancelled = False
        self.row_offset = len(state.results)
        parent = bpy.data.collections.new('CAD_Auto_'+(state.input_collection.name if state.mode == 'COLLECTION' else 'Selected'))
        self.scene.collection.children.link(parent)
        # SELECTED routes directly to this fresh destination through _destination.
        self.routing = dict(mode='AUTO', input=None, output=parent)
        for source in self.objects:
            row = state.results.add()
            row.source = source
            row.source_label = source.name
            row.execution_mode = 'AUTO'
            row.status = 'PENDING'
            row.stage = 'Queued'

    def _start_worker(self, index):
        source = self.objects[index]
        row = self._row(index)
        directory = self.root/uuid.uuid4().hex
        row.auto_run_dir = row.run_dir = str(directory)
        row.status = 'RUNNING'
        log = None
        try:
            issues = jobs.preflight_object(source, check_topology=False)
            if issues:raise ValueError('; '.join(issues))
            snapshot = capture(source, check_topology=False)
            directory.mkdir()
            profile = dict(self.controls, method='CAD_AUTO', delivery='CAD_AUTO_VARIANTS',
                           source_name=source.name, source_hash=snapshot['source_hash'],
                           code_hash=code_hash(), tool_version=__version__, sample_count=20000,
                           unit_scale=snapshot['unit_scale'], retry_component=self.retry_component,
                           worker_timeout_minutes=self.timeout_seconds / 60)
            (directory/'source.json').write_text(json.dumps(snapshot), encoding='utf8')
            (directory/'profile.json').write_text(json.dumps(profile, indent=2), encoding='utf8')
            log = (directory/'worker.log').open('w', encoding='utf8')
            worker = Path(__file__).resolve().parents[1]/'cad_mesh_tool/auto_worker.py'
            process = subprocess.Popen([bpy.app.binary_path, '--background', '--factory-startup',
                '--python-exit-code', '1', '--python', str(worker), '--', str(directory)],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self.running[index] = dict(index=index, process=process, log=log, run_dir=directory,
                log_position=0, phase='Analyzing solids', source_hash=snapshot['source_hash'],
                started=time.perf_counter(), imported=set())
        except Exception as error:
            if log:log.close()
            row.status = 'FAIL';row.reason = str(error);row.stage = 'Auto preparation'
            self.completed += 1

    def _import_completed(self, index):
        job = self.running[index]
        path = job['run_dir']/'auto_manifest.json'
        if not path.exists():return
        report = json.loads(path.read_text(encoding='utf8'))
        if report['source_hash'] != job['source_hash'] or report['code_hash'] != code_hash():
            raise ValueError('Auto report source or implementation changed')
        state = self.scene.lcw_cad_reconstruction
        source = self.objects[index]
        for item in completed_bodies(report, job.get('timed_out', False)):
            component = item['component_index']
            if component in job['imported']:continue
            row_index = self.row_offset+index if not job['imported'] else len(state.results)
            if row_index == len(state.results):state.results.add()
            row = state.results[row_index]
            output = None;manifest = {};status = item['status'];reason = item['reason']
            directory = job['run_dir']
            try:
                if fingerprint(source) != job['source_hash']:raise ValueError('Source changed during Auto run')
                if item['winner']:
                    directory = (job['run_dir']/item['winner']).resolve()
                    if not directory.is_relative_to(job['run_dir'].resolve()):raise ValueError('Auto result escaped run directory')
                    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf8'))
                    if manifest['result_sha256'] != item['result_sha256']:raise ValueError('Auto winner artifact changed')
                    output = jobs._import_result(state, source, directory, status, self.routing)
                    manifest = dict(manifest, partial=status == 'REVIEW', summary=reason)
            except Exception as error:
                status = 'FAIL';reason = f'Auto import/integrity failure: {error}'
            jobs._result_record(state, source, directory, status, reason, 'Auto complete', output,
                                manifest, item.get('guarded', False), row_index, 0., item.get('seconds', 0.))
            row.execution_mode = 'AUTO';row.auto_run_dir = str(job['run_dir'])
            row.component_index = component;row.source_label = f'{source.name} / Solid {component+1}'
            row.strategy_summary = f"{item.get('selected_variant', 'Blocked source')}: {reason}"
            if item.get('winner'):
                row.metrics_summary = f"{item['before']} -> {item['triangles']} triangles | {item['accepted']}/{item['detected']} reconstructed | {item['reduced']} reduced | {len(item['untreated'])} retained"
            job['imported'].add(component)

    def _read_worker_progress(self, job):
        super()._read_worker_progress(job)
        self._import_completed(job['index'])

    def _finish_worker(self, index):
        job = self.running[index]
        self._import_completed(index)
        job['log'].close()
        report_path = job['run_dir']/'auto_manifest.json'
        complete = report_path.exists() and json.loads(report_path.read_text(encoding='utf8')).get('complete')
        if (not complete and not job.get('timed_out')) or not job['imported']:
            state = self.scene.lcw_cad_reconstruction
            row = self._row(index) if not job['imported'] else state.results.add()
            row.source = self.objects[index];row.source_label = row.source.name
            row.execution_mode = 'AUTO';row.status = 'FAIL';row.stage = 'Auto worker'
            row.auto_run_dir = row.run_dir = str(job['run_dir'])
            failure = job['run_dir']/'failure.json'
            row.reason = json.loads(failure.read_text(encoding='utf8'))['error'] if failure.exists() else 'Auto worker stopped before all solids completed; completed results preserved.'
            if job.get('timed_out'):
                row.reason = f'Worker exceeded the {self.timeout_seconds / 60:g} minute time limit during preparation.'
        del self.running[index]
        self.completed += 1

    def cancel(self):
        for job in self.running.values():
            if job['process'].poll() is None:job['process'].terminate()
        for index in list(self.running):
            process = self.running[index]['process']
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            try:self._import_completed(index)
            except (OSError, ValueError):pass
        super().cancel()
