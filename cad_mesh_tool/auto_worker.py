"""One external process per object; solids and immutable variants run sequentially."""
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import bpy
import numpy as np
from cad_mesh_tool.api import code_hash
from cad_mesh_tool.artifacts import publish_json
from cad_mesh_tool.auto_policy import variants, fallback_variant, winner, solid_order, objective_name
from cad_mesh_tool.geometry import topology
from cad_mesh_tool.operations import decision
from cad_mesh_tool.processes import kill as kill_process, spawn_options
from cad_mesh_tool.solids import solid_partitions, extract_component
from cad_mesh_tool.worker import main as run_variant, prepare_source, source_digest


PARALLEL_VARIANT_TRIANGLES = 4000


def acquire_slot(profile):
    """Claim one spare CPU slot published by the batch (atomic slot files)."""
    directory = profile.get('variant_slot_dir')
    if not directory:return None
    directory = Path(directory)
    try:capacity = int((directory/'capacity.txt').read_text(encoding='utf8').strip() or 0)
    except (OSError, ValueError):return None
    for number in range(max(0, capacity)):
        slot = directory/f'slot_{number}'
        try:descriptor = os.open(slot, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:continue
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        return slot
    return None


def release_slot(slot):
    if slot is None:return
    try:slot.unlink()
    except OSError:pass


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def publish(root, report):
    publish_json(root/'auto_manifest.json', report)


def select_winner(item, objective='LIGHTWEIGHT'):
    best = winner(item['trials'], objective)
    item['objective'] = objective
    if best:
        item.update(status=best['status'], winner=best['path'], selected_variant=best['variant'],
                    detected=best['detected'], accepted=best['accepted'], reduced=best['reduced'],
                    untreated=best['untreated'], before=best['before'], triangles=best['triangles'],
                    loops=best['loops'], result_sha256=best['result_sha256'])
        criterion = ('Editable objective: fewest retained regions, then most support loops, then fewest triangles. '
                     if objective == 'EDITABLE' else
                     'Lowest final triangle count among validated variants; ties prefer more reduced and reconstructed regions. ')
        item['reason'] = (criterion
                          + ('Support loops omitted to minimize polygons. ' if best['variant'] != 'full_loops' else 'Support loops retained. ')
                          + f"{best['accepted']}/{best['detected']} regions reconstructed; {best['reduced']} reduced; "
                          + f"{len(best['untreated'])} retained; {best['loops']} loops.")
    else:
        item['reason'] = 'No fully validated Auto variant; inspect recorded failures.'

def process_body(root, source, profile, index, partition, checkpoint=None):
    started = time.perf_counter()
    item = dict(component_index=index, status='FAIL', trials=[], winner=None)
    objective = objective_name(profile.get('auto_objective'))
    body = extract_component(source, partition['faces'], partition['reversed_faces'])
    counts = topology(body['faces'])
    item['topology'] = counts
    item['guarded'] = bool(counts['nonmanifold'])
    if any(counts[k] for k in ('boundary', 'winding', 'duplicates')):
        item['reason'] = 'Source solid has open boundaries, winding errors or duplicate faces.'
        return item
    # One detection pass per solid. Every variant receives the same immutable
    # source text and verifies the prepared plan against its digest.
    body_text = json.dumps(body)
    prepared = prepare_source(json.loads(body_text), profile)
    hits = prepared['source_intersections']
    item['source_intersections'] = hits
    if hits['intersections']:
        item['reason'] = f"Source solid has {len(hits['intersections'])} intersecting triangle pairs."
        return item
    prepared.update(source_sha256=source_digest(body_text),
                    profile={k: profile.get(k) for k in ('epsilon_m', 'hole_detail_factor', 'hole_epsilon_mm')})
    features = prepared['discovery']['features']
    item['detected'] = len(features)
    choices = [(order,)+choice for order, choice in enumerate(variants(features))]
    pending = list(choices)
    children = {}
    fallback_checked = False
    prepared_path = None
    body_root = root/f'solid_{index:04d}'

    def prepare_directory(order, label, operations, preserve, extra=None):
        directory = body_root/label
        directory.mkdir(parents=True, exist_ok=False)
        options = dict(profile, method='A', delivery='EDITABLE_NGONS', operations=operations,
                       preserve_curve_segmentation=preserve, preserve_nonmanifold=item['guarded'],
                       component_index=index, shared_interface_reversed_faces=partition['reversed_faces'],
                       straight_walls=dict(enabled=True, normal_limit_deg=None),
                       # Auto may reduce a requested support clearance that does not fit.
                       perimeter_clearance_policy='shrink', **(extra or {}))
        (directory/'source.json').write_text(body_text, encoding='utf8')
        (directory/'profile.json').write_text(json.dumps(options, indent=2), encoding='utf8')
        print('AUTO_VARIANT', index, label, flush=True)
        return directory

    def finish(order, label, operations, preserve, directory, error=None, stage=None, trace=None):
        trial = dict(variant=label, order=order, path=str(directory.relative_to(root)), status='FAIL')
        try:
            if error is not None:raise ValueError(error)
            manifest = read(directory/'manifest.json')
            validation = read(directory/'validation_final.json')
            if manifest['geometry_status'] != 'PASS' or not all(validation['checks'].values()):
                raise ValueError('Auto variant did not pass final validation')
            plan = read(directory/'plan.json')['features']
            skipped = {s['feature'] for s in manifest['skipped_features']}
            untreated = [f['id'] for f in plan if f['id'] in skipped or
                         decision(f['category'], operations, preserve) != 'REBUILD']
            accepted = len(plan)-len(untreated)
            # User-protected features are intentionally untreated, not a finding.
            intended = set(manifest.get('user_protected_features', ()))
            partial = manifest['partial'] or any(f not in intended for f in untreated)
            trial.update(status='REVIEW' if partial else 'PASS', triangles=manifest['final']['t'],
                         before=manifest['before']['t'], reduced=manifest['operation_results']['curves_reduced'],
                         accepted=accepted, detected=len(plan), skipped=len(skipped),
                         untreated=untreated, loops=manifest['operation_results']['perimeter_loops_created'],
                         preserve_segments=preserve, partial=partial,
                         result_sha256=manifest['result_sha256'])
        except Exception as failure:
            trial['error'] = str(failure)
            if not (directory/'auto_failure.json').exists():
                (directory/'auto_failure.json').write_text(json.dumps(dict(error=str(failure),
                    stage=stage or 'startup', traceback=trace or traceback.format_exc()), indent=2), encoding='utf8')
        item['trials'].append(trial)
        # Completion order varies with parallel variants; ranking and reports
        # use the deterministic variant order.
        item['trials'].sort(key=lambda value: value['order'])
        select_winner(item, objective)
        item['seconds'] = time.perf_counter()-started
        if checkpoint is not None:
            checkpoint(item)

    def collect(block=False):
        while children:
            for order in sorted(children):
                process, slot, args, directory = children[order]
                if process.poll() is None:continue
                release_slot(slot)
                del children[order]
                error = stage = trace = None
                if not (directory/'manifest.json').exists():
                    failure = directory/'failure.json'
                    detail = read(failure) if failure.exists() else {}
                    error = detail.get('error') or f'Variant worker exited with code {process.returncode}'
                    stage, trace = detail.get('stage'), detail.get('traceback')
                finish(*args, directory, error, stage, trace)
            if not block or not children:return
            time.sleep(.2)

    def launch(order, label, operations, preserve, slot):
        nonlocal prepared_path
        if prepared_path is None:
            prepared_path = body_root/'prepared.pkl'
            body_root.mkdir(parents=True, exist_ok=True)
            with prepared_path.open('wb') as stream:pickle.dump(prepared, stream)
        directory = prepare_directory(order, label, operations, preserve,
                                      dict(prepared_path=str(prepared_path)))
        try:
            with (directory/'worker.log').open('w', encoding='utf8') as log:
                # Variants stay in this worker's process group, so stopping
                # the Auto worker's tree also stops them.
                process = subprocess.Popen([bpy.app.binary_path, '--background', '--factory-startup',
                    '--python-exit-code', '1', '--python', str(Path(__file__).with_name('worker.py')),
                    '--', str(directory)],
                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **spawn_options())
        except BaseException:
            release_slot(slot)
            raise
        children[order] = (process, slot, (order, label, operations, preserve), directory)

    def stop_children():
        # Any exception (failed start, failed result handling, interrupt)
        # must not leave variant processes running or slots claimed.
        running = list(children.values()) + ([speculative] if speculative is not None else [])
        children.clear()
        for process, slot, _, _ in running:
            try:
                kill_process(process)
            finally:
                release_slot(slot)

    # Large solids run every variant in a child process: this process keeps
    # one of them on its own slot and starts the others whenever the batch
    # publishes a spare slot, also while earlier variants are still running.
    # Small solids stay in-process; a child's start-up would cost more.
    use_children = bool(profile.get('variant_slot_dir')) and len(body['triangles']) >= profile.get(
        'parallel_variant_triangles', PARALLEL_VARIANT_TRIANGLES)
    # The holes-only fallback depends on the other variants' outcome. With a
    # spare slot it is computed speculatively and only used if the ordinary
    # rule (auto_policy.fallback_variant) asks for it; otherwise discarded.
    possible = fallback_variant(features, [dict(variant='full', status='FAIL')]) if use_children else None
    speculative = None
    try:
        while True:
            if use_children:
                while pending:
                    own = not any(slot is None for _, slot, _, _ in children.values())
                    slot = None if own else acquire_slot(profile)
                    if not own and slot is None:break
                    launch(*pending.pop(0), slot)
                if (not pending and possible is not None and speculative is None and not fallback_checked
                        and len(choices) < 4 and not any(c[1] == possible[0] for c in choices)):
                    slot = acquire_slot(profile)
                    if slot is not None:
                        launch(len(choices), *possible, slot)
                        speculative = children.pop(len(choices))
                if pending or children:
                    collect()
                    time.sleep(.2)
                    continue
            elif pending:
                order, label, operations, preserve = pending.pop(0)
                directory = prepare_directory(order, label, operations, preserve)
                objects_before = set(bpy.data.objects)
                meshes_before = set(bpy.data.meshes)
                state = {}
                error = trace = None
                try:
                    run_variant(directory, state, prepared)
                except Exception as failure:
                    error, trace = str(failure), traceback.format_exc()
                finally:
                    for obj in set(bpy.data.objects)-objects_before:bpy.data.objects.remove(obj, do_unlink=True)
                    for mesh in set(bpy.data.meshes)-meshes_before:
                        if mesh.users == 0:bpy.data.meshes.remove(mesh)
                finish(order, label, operations, preserve, directory, error, state.get('stage', 'startup'), trace)
                continue
            if fallback_checked or len(choices) >= 4:break
            fallback_checked = True
            fallback = fallback_variant(features, item['trials'])
            if fallback is None or any(c[1] == fallback[0] for c in choices):
                if speculative is not None:
                    process, slot, _, directory = speculative
                    speculative = None
                    try:
                        kill_process(process)
                    finally:
                        release_slot(slot)
                    shutil.rmtree(directory, ignore_errors=True)
                break
            choice = (len(choices),)+fallback
            choices.append(choice)
            if speculative is not None:
                # Same order, label and options as the speculative run.
                children[choice[0]] = speculative
                speculative = None
                continue
            pending.append(choice)
    finally:
        stop_children()
    select_winner(item, objective)
    item['seconds'] = time.perf_counter()-started
    return item


def main(root):
    root = Path(root).resolve()
    source, profile = read(root/'source.json'), read(root/'profile.json')
    if profile['code_hash'] != code_hash():raise ValueError('Auto implementation changed since preparation')
    if (root/'auto_manifest.json').exists():raise FileExistsError('Auto run already started; use a new immutable directory')
    partitions = solid_partitions(source['faces'], source['vertices'])
    partition_hash = hashlib.sha256(json.dumps(partitions, sort_keys=True).encode()).hexdigest()
    retry = profile.get('retry_component')
    if retry is not None and not 0 <= retry < len(partitions):raise ValueError('Source solid partition changed')
    report = dict(method='CAD_AUTO', complete=False, source_hash=profile['source_hash'],
                  code_hash=profile['code_hash'], partition_hash=partition_hash,
                  partitions=partitions, bodies=[],
                  selected_components=[retry] if retry is not None else list(range(len(partitions))))
    publish(root, report)
    def checkpoint(item):
        report['active_body'] = item
        publish(root, report)

    for index in solid_order(partitions, retry):
        partition = partitions[index]
        print('AUTO_SOLID', index+1, len(partitions), flush=True)
        try:item = process_body(root, source, profile, index, partition, checkpoint)
        except Exception as error:
            item = dict(component_index=index, status='FAIL', winner=None, reason=str(error),
                        traceback=traceback.format_exc(), trials=[])
        report['bodies'].append(item)
        report.pop('active_body', None)
        publish(root, report)
    report['complete'] = True
    publish(root, report)
    print('AUTO_COMPLETE', len(report['bodies']), flush=True)


if __name__ == '__main__':
    directory = Path(sys.argv[sys.argv.index('--')+1]).resolve()
    try:main(directory)
    except Exception as error:
        (directory/'failure.json').write_text(json.dumps(dict(error=str(error), traceback=traceback.format_exc())), encoding='utf8')
        raise
