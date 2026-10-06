"""One external process per object; solids and immutable variants run sequentially."""
import hashlib
import json
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
from cad_mesh_tool.solids import solid_partitions, extract_component
from cad_mesh_tool.worker import main as run_variant, prepare_source, source_digest


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
    choices = variants(features)
    for order in range(4):
        if order >= len(choices):
            fallback = fallback_variant(features, item['trials'])
            if fallback is None or any(c[0] == fallback[0] for c in choices):break
            choices.append(fallback)
        label, operations, preserve = choices[order]
        directory = root/f'solid_{index:04d}'/label
        directory.mkdir(parents=True, exist_ok=False)
        options = dict(profile, method='A', delivery='EDITABLE_NGONS', operations=operations,
                       preserve_curve_segmentation=preserve, preserve_nonmanifold=item['guarded'],
                       component_index=index, shared_interface_reversed_faces=partition['reversed_faces'],
                       straight_walls=dict(enabled=True, normal_limit_deg=None))
        (directory/'source.json').write_text(body_text, encoding='utf8')
        (directory/'profile.json').write_text(json.dumps(options, indent=2), encoding='utf8')
        trial = dict(variant=label, order=order, path=str(directory.relative_to(root)), status='FAIL')
        print('AUTO_VARIANT', index, label, flush=True)
        objects_before = set(bpy.data.objects)
        meshes_before = set(bpy.data.meshes)
        state = {}
        try:
            run_variant(directory, state, prepared)
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
        except Exception as error:
            trial['error'] = str(error)
            (directory/'auto_failure.json').write_text(json.dumps(dict(error=str(error),
                stage=state.get('stage', 'startup'), traceback=traceback.format_exc()), indent=2), encoding='utf8')
        finally:
            for obj in set(bpy.data.objects)-objects_before:bpy.data.objects.remove(obj, do_unlink=True)
            for mesh in set(bpy.data.meshes)-meshes_before:
                if mesh.users == 0:bpy.data.meshes.remove(mesh)
        item['trials'].append(trial)
        select_winner(item, objective)
        item['seconds'] = time.perf_counter()-started
        if checkpoint is not None:
            checkpoint(item)
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
