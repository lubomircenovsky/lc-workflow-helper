"""Auto batch adapter: light live capture, external planning and incremental import.

Each independent solid of a multi-solid source runs in its own worker process
(the worker's retry_component path), so large assemblies use every worker slot
instead of processing their solids one after another in a single process.
"""
import collections
import json
import shutil
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
from ..cad_mesh_tool.auto_policy import completed_bodies, objective_name
from ..cad_mesh_tool.mesh_io import capture, fingerprint
from ..cad_mesh_tool.processes import spawn_options
from ..cad_mesh_tool.solids import solid_partitions
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
    values['auto_objective'] = objective_name(getattr(state, 'auto_objective', 'LIGHTWEIGHT'))
    return values


def run_root(state):
    if state.run_root.startswith('//') and not bpy.data.filepath:
        root = Path(tempfile.gettempdir())/'lcw_cad_auto_runs'
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()
    return jobs.run_root(state)


class AutoBatch(jobs.CADBatch):
    """Modal Auto batch over work items.

    A work item is one source object, or one solid of a multi-solid source.
    Items start as one per object; when an object is captured and has several
    independent solids, it expands into one item per solid. All solid items of
    an object share one immutable source.json (hard link where possible) and
    the worker processes only its ``retry_component``; partitions are computed
    from the same captured snapshot the worker reads, so indices agree.
    """

    def __init__(self, context, objects, root, retry_component=None):
        self.scene = context.scene
        state = self.scene.lcw_cad_reconstruction
        self.controls = settings(state)
        self.objects = tuple(objects)
        self.root = root
        self.retry_component = retry_component
        self.max_workers = min(max(int(state.concurrent_workers), 1), 16)
        self.timeout_seconds = jobs.worker_timeout_seconds(state)
        self.completed = 0
        self.running = {}
        self.cancelled = False
        self.row_offset = len(state.results)
        parent = bpy.data.collections.new('CAD_Auto_'+(state.input_collection.name if state.mode == 'COLLECTION' else 'Selected'))
        self.scene.collection.children.link(parent)
        # SELECTED routes directly to this fresh destination through _destination.
        self.routing = dict(mode='AUTO', input=None, output=parent)
        self.items = []
        for index, source in enumerate(self.objects):
            row = state.results.add()
            row.source = source
            row.source_label = source.name
            row.execution_mode = 'AUTO'
            row.status = 'PENDING'
            row.stage = 'Queued'
            self.items.append(dict(object=index, component=retry_component, row=self.row_offset+index,
                                   snapshot=None, imported=set()))
        self.queue = collections.deque(range(len(self.items)))
        # Spare worker slots let a running solid evaluate its Auto variants in
        # parallel processes once the queue no longer needs them.
        self.slot_dir = self.root/f'_variant_slots_{uuid.uuid4().hex}'
        self.slot_dir.mkdir(parents=True, exist_ok=True)
        self._publish_capacity()

    def _publish_capacity(self):
        spare = max(0, self.max_workers - len(self.running) - len(self.queue))
        try:
            (self.slot_dir/'capacity.tmp').write_text(str(spare), encoding='utf8')
            (self.slot_dir/'capacity.tmp').replace(self.slot_dir/'capacity.txt')
        except OSError:
            pass

    def _release_slots_of(self, pid):
        for slot in self.slot_dir.glob('slot_*'):
            try:
                if slot.read_text(encoding='utf8').strip() == str(pid):slot.unlink()
            except OSError:
                pass

    def _stop_expired_workers(self):
        jobs.stop_expired_workers(self.running, self.timeout_seconds, tree=True)

    @property
    def next_index(self):
        # Base-class compatibility: number of items already started.
        return len(self.items)-len(self.queue)

    def _row(self, item_id):
        return self.scene.lcw_cad_reconstruction.results[self.items[item_id]['row']]

    def _expand(self, item_id, snapshot, source_hash):
        """Split a captured multi-solid source into per-solid work items."""
        item = self.items[item_id]
        partitions = solid_partitions(snapshot['faces'], snapshot['vertices'])
        if len(partitions) < 2:
            return
        shared = self.root/uuid.uuid4().hex
        shared.mkdir()
        (shared/'source.json').write_text(json.dumps(snapshot), encoding='utf8')
        (shared/'SHARED_SOURCE').write_text('Immutable source shared by per-solid Auto runs\n', encoding='utf8')
        state = self.scene.lcw_cad_reconstruction
        source = self.objects[item['object']]
        item.update(component=0, snapshot=shared, source_hash=source_hash)
        self._row(item_id).source_label = f'{source.name} / Solid 1'
        children = []
        for component in range(1, len(partitions)):
            row = state.results.add()
            row.source = source
            row.source_label = f'{source.name} / Solid {component+1}'
            row.execution_mode = 'AUTO'
            row.status = 'PENDING'
            row.stage = 'Queued'
            self.items.append(dict(object=item['object'], component=component, row=len(state.results)-1,
                                   snapshot=shared, source_hash=source_hash, imported=set()))
            children.append(len(self.items)-1)
        # Run the remaining solids of this object next, keeping objects compact.
        self.queue.extendleft(reversed(children))

    def _start_worker(self, item_id):
        item = self.items[item_id]
        source = self.objects[item['object']]
        row = self._row(item_id)
        directory = self.root/uuid.uuid4().hex
        row.auto_run_dir = row.run_dir = str(directory)
        row.status = 'RUNNING'
        log = None
        try:
            if item['snapshot'] is None:
                issues = jobs.preflight_object(source, check_topology=False)
                if issues:raise ValueError('; '.join(issues))
                snapshot = capture(source, check_topology=False)
                source_hash = snapshot['source_hash']
                if self.retry_component is None:
                    self._expand(item_id, snapshot, source_hash)
            else:
                snapshot = None
                source_hash = item['source_hash']
                if fingerprint(source) != source_hash:
                    raise ValueError('Source changed during Auto run')
            directory.mkdir()
            if item['snapshot'] is None:
                (directory/'source.json').write_text(json.dumps(snapshot), encoding='utf8')
            else:
                try:os.link(item['snapshot']/'source.json', directory/'source.json')
                except OSError:shutil.copy2(item['snapshot']/'source.json', directory/'source.json')
            profile = dict(self.controls, method='CAD_AUTO', delivery='CAD_AUTO_VARIANTS',
                           source_name=source.name, source_hash=source_hash,
                           code_hash=code_hash(), tool_version=__version__, sample_count=20000,
                           unit_scale=bpy.context.scene.unit_settings.scale_length,
                           retry_component=item['component'],
                           variant_slot_dir=str(self.slot_dir),
                           worker_timeout_minutes=self.timeout_seconds / 60)
            (directory/'profile.json').write_text(json.dumps(profile, indent=2), encoding='utf8')
            log = (directory/'worker.log').open('w', encoding='utf8')
            worker = Path(__file__).resolve().parents[1]/'cad_mesh_tool/auto_worker.py'
            process = subprocess.Popen([bpy.app.binary_path, '--background', '--factory-startup',
                '--python-exit-code', '1', '--python', str(worker), '--', str(directory)],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                **spawn_options(group=True))
            self.running[item_id] = dict(index=item_id, process=process, log=log, run_dir=directory,
                log_position=0, phase='Analyzing solids', source_hash=source_hash,
                started=time.perf_counter(), imported=item['imported'])
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
        source = self.objects[self.items[index]['object']]
        for item in completed_bodies(report, job.get('timed_out', False),
                                     job.get('interrupted_reason'),
                                     include_unfinished=not job.get('cancelled', False)):
            component = item['component_index']
            if component in job['imported']:continue
            row_index = self.items[index]['row'] if not job['imported'] else len(state.results)
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
                    if manifest.get('partial') and manifest.get('summary'):
                        # Selection metrics must not hide preserved junctions,
                        # stage fallbacks or sharp-edge/shading warnings.
                        reason = manifest['summary']+' '+reason
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
        try:self._import_completed(job['index'])
        except PermissionError:
            # A Windows rename/reader sharing collision is transient. Poll on
            # the next UI tick rather than cancelling every active worker.
            pass

    def _finish_worker(self, index):
        try:self._finish_worker_report(index)
        except PermissionError as error:
            job = self.running[index]
            since = job.setdefault('report_blocked_since', time.perf_counter())
            if time.perf_counter()-since < 5.:
                return
            # Bound retries even after the process has exited. Keep imported
            # bodies and isolate a persistent file-access failure to this item.
            state = self.scene.lcw_cad_reconstruction
            row = state.results.add() if job['imported'] else self._row(index)
            row.source = self.objects[self.items[index]['object']];row.source_label = self._row(index).source_label or row.source.name
            row.execution_mode = 'AUTO';row.status = 'FAIL';row.stage = 'Auto report'
            row.auto_run_dir = row.run_dir = str(job['run_dir'])
            row.reason = f'Auto report remained inaccessible; completed results preserved: {error}'
            job['log'].close()
            del self.running[index]
            self.completed += 1

    def _finish_worker_report(self, index):
        job = self.running[index]
        report_path = job['run_dir']/'auto_manifest.json'
        complete = report_path.exists() and json.loads(report_path.read_text(encoding='utf8')).get('complete')
        if not complete and not job.get('timed_out'):
            job['interrupted_reason'] = 'Worker stopped unexpectedly'
        self._import_completed(index)
        job['log'].close()
        if not job['imported']:
            state = self.scene.lcw_cad_reconstruction
            row = self._row(index) if not job['imported'] else state.results.add()
            row.source = self.objects[self.items[index]['object']];row.source_label = self._row(index).source_label or row.source.name
            row.execution_mode = 'AUTO';row.status = 'FAIL';row.stage = 'Auto worker'
            row.auto_run_dir = row.run_dir = str(job['run_dir'])
            failure = job['run_dir']/'failure.json'
            row.reason = json.loads(failure.read_text(encoding='utf8'))['error'] if failure.exists() else 'Auto worker stopped before all solids completed; completed results preserved.'
            if job.get('timed_out'):
                row.reason = f'Worker exceeded the {self.timeout_seconds / 60:g} minute time limit during preparation.'
        del self.running[index]
        self.completed += 1

    def cancel(self):
        for index in list(self.running):
            job = self.running[index]
            jobs.kill_process_tree(job['process'])
            job['cancelled'] = True
            job['interrupted_reason'] = 'Cancelled by user'
            try:self._import_completed(index)
            except (OSError, ValueError):pass
        self.cancelled = True
        for job in self.running.values():
            job['log'].close()
        self.running.clear()
        self.queue.clear()
        state = self.scene.lcw_cad_reconstruction
        rows = state.results
        for row_index in sorted({item['row'] for item in self.items}, reverse=True):
            if row_index < len(rows) and rows[row_index].status in {'PENDING', 'RUNNING'}:
                rows.remove(row_index)
        state.active_result = min(max(state.active_result, 0), max(len(rows) - 1, 0))
        shutil.rmtree(self.slot_dir, ignore_errors=True)
        state.progress = 'Cancelled; completed results preserved'

    def _progress(self):
        phases = ', '.join(f"{self._row(i).source_label}: {job['phase']}"
                           for i, job in sorted(self.running.items()))
        self.scene.lcw_cad_reconstruction.progress = (
            f'Queued {len(self.queue)} | Running {len(self.running)} | Done {self.completed}'
            + (f' | {phases}' if phases else ''))

    def step(self):
        state = self.scene.lcw_cad_reconstruction
        if self.cancelled:
            return False
        self._stop_expired_workers()
        for index, job in sorted(self.running.items()):
            if job['process'].poll() is not None:
                # The worker has exited, so any variant slots it held are stale
                # even if its report is still locked and finishing is retried.
                pid = getattr(job['process'], 'pid', None)
                self._finish_worker(index)
                if pid is not None:
                    self._release_slots_of(pid)
                self._publish_capacity()
                self._progress()
                return True
            self._read_worker_progress(job)
        if self.queue and len(self.running) < self.max_workers:
            self._start_worker(self.queue.popleft())
            self._publish_capacity()
            self._progress()
            return True
        if not self.running and not self.queue:
            shutil.rmtree(self.slot_dir, ignore_errors=True)
            state.progress = f'Complete: {len(self.items)} CAD work item(s)'
            return False
        self._progress()
        return True
