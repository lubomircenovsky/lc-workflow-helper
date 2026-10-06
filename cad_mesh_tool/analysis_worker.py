"""Read-only source analysis and bounded checkpoint screening in a worker."""
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from cad_mesh_tool.detect import discover
from cad_mesh_tool.geometry import topology
from cad_mesh_tool.intersections import intersections
from cad_mesh_tool.nonmanifold import protection
from cad_mesh_tool.recovery import decisions, is_geometric_conflict
from cad_mesh_tool.solids import components, extract_component, solid_partitions
from cad_mesh_tool.worker import validated_candidate
import bpy


def analyze(source, profile):
    started = time.perf_counter()
    counts = topology(source['faces'])
    partitions = solid_partitions(source['faces'], source['vertices'])
    groups = [item['faces'] for item in partitions]
    vertices = np.asarray(source['vertices'])
    vertices -= vertices.mean(0)
    print('CHECK_SOURCE intersections', flush=True)
    hits = intersections(vertices, np.asarray(source['triangles']))
    result = dict(topology=counts, solids=len(groups), source_intersections=hits,
                  guarded=bool(counts['nonmanifold']), trials=[], recommendation=None)
    result['junction_shells_separated'] = len(groups) - len(components(source['faces']))
    result['shared_interface_faces'] = sorted({fi for item in partitions for fi in item['shared_interface_faces']})
    if any(counts[k] for k in ('boundary', 'winding', 'duplicates')):
        result['summary'] = 'Repair open edges, inconsistent winding or duplicate faces before reconstruction.'
        result['blocked'] = True
    elif hits['intersections']:
        face_owner = {}
        for index,group in enumerate(groups):
            for fi in group:face_owner.setdefault(fi,set()).add(index)
        polygon_ids = source.get('triangle_polygons')
        if polygon_ids is None:
            by_vertices = {tuple(sorted(face)):fi for fi,face in enumerate(source['faces']) if len(face)==3}
            polygon_ids = [by_vertices[tuple(sorted(tri))] for tri in source['triangles']]
        owner = [face_owner[fi] for fi in polygon_ids]
        cross = sum(not owner[h['a']].intersection(owner[h['b']]) for h in hits['intersections'])
        internal_solids={index for h in hits['intersections']
                         for index in owner[h['a']].intersection(owner[h['b']])}
        result['internal_solid_indices']=sorted(internal_solids)
        eligible_solids=len(groups)-len(internal_solids)
        result.update(cross_solid_intersections=cross,
                      internal_intersections=len(hits['intersections'])-cross,
                      solids_without_internal_intersections=eligible_solids)
        result['summary'] = (f"{len(hits['intersections'])} source intersection pairs: {cross} between solids, "
                             f"{len(hits['intersections'])-cross} internal. "
                             + ('Use Separate Solids; inspect internal pairs on each solid.' if cross else
                                'Repair intersecting surfaces or re-export independent CAD solids.'))
        result['blocked'] = not (cross and eligible_solids and profile.get('separate_solids'))
        if cross and eligible_solids:
            result['recommendation'] = {'separate_solids': True}
    else:
        result['blocked'] = False
    # Screen what Reconstruct will actually process: each intersection-free
    # solid when Separate Solids is on (or recommended), otherwise the source.
    if not result.get('blocked') or result.get('recommendation') == {'separate_solids': True}:
        split = len(partitions) > 1 and (profile.get('separate_solids') or result.get('recommendation'))
        targets = []
        if split:
            clean = set(range(len(partitions))) - set(result.get('internal_solid_indices', ()))
            for index in sorted(clean):
                part = partitions[index]
                body = extract_component(source, part['faces'], part['reversed_faces'])
                targets.append((index, body, bool(topology(body['faces'])['nonmanifold'])))
        elif not hits['intersections']:
            targets.append((None, source, bool(counts['nonmanifold'])))
        result['solid_screens'] = []
        for index, body, guarded in targets:
            outcome = screen(body, profile, guarded)
            outcome['solid'] = index
            result['solid_screens'].append(outcome)
        if targets:
            result['trials'] = [dict(trial, solid=item['solid']) for item in result['solid_screens'] for trial in item['trials']]
            result['user_protected_faces'] = sum(item.get('user_protected_faces', 0) for item in result['solid_screens'])
            passed = [item for item in result['solid_screens'] if item.get('recommendation')]
            failed = [item for item in result['solid_screens'] if not item.get('recommendation')]
            if passed:
                # One shared control set: the profile passing for most solids.
                votes = Counter(json.dumps(item['recommendation'], sort_keys=True) for item in passed)
                best = json.loads(votes.most_common(1)[0][0])
                if split:best['separate_solids'] = True
                result['recommendation'] = best
            elif not split:
                result['recommendation'] = None
            if split:
                result['summary'] = (result.get('summary', '') + ' ' if result.get('summary') else '') + (
                    f"Screened {len(targets)} solid(s): {len(passed)} passed, {len(failed)} without a passing profile. "
                    'Reconstruct still performs full validation and cleanup.')
            elif passed:
                result['summary'] = (f"{passed[0]['passed']} passed checkpoint screening (750 area samples plus vertices, edges and centroids). "
                                     'Reconstruct still performs full validation and cleanup.')
            else:
                item = result['solid_screens'][0]
                result['summary'] = item.get('summary') or 'No screened profile passed. Inspect trial errors; repair dependent boundaries or run a smaller operation set.'
                result['blocked'] = bool(item.get('blocked'))
            if not split:
                for key in ('categories', 'holes', 'source_repair'):
                    if key in result['solid_screens'][0]:result[key] = result['solid_screens'][0][key]
    result['seconds'] = time.perf_counter()-started
    return result


def screen(source, profile, guarded):
    """Checkpoint-screen up to four operation profiles on one intersection-free body.

    Returns a dict with repair report, categories, holes, user-protection
    counts, trials and the first passing profile (or an error summary).
    """
    from cad_mesh_tool.protected import face_cycles, locked_faces, mark_features
    from cad_mesh_tool.source_repair import repair_collinear_faces
    original_source = source
    try:
        source, source_repair = repair_collinear_faces(source)
    except ValueError as error:
        return dict(blocked=True, summary=str(error), trials=[], recommendation=None)
    out = dict(source_repair=source_repair, trials=[], recommendation=None, blocked=False)
    print('DISCOVER', flush=True)
    plan = discover(source['vertices'], source['faces'], profile['epsilon_m'],
                    profile.get('hole_detail_factor', 1.),
                    (profile.get('hole_epsilon_mm', 0.)/1000) or None)
    out['categories'] = dict(Counter(f['category'] for f in plan['features']))
    out['holes'] = [{'id': f['id'], 'before': f['segments_before'], 'target': f['segments']}
                    for f in plan['features'] if f['category'] == 'circular_hole']
    locked = protection(source, plan['features']) if guarded else None
    if locked:
        for feature in plan['features']:
            if feature['id'] in locked['features']:
                feature['forced_skip_reason'] = 'Touches an unchanged source non-manifold junction'
    user_faces = locked_faces(source)
    user_cycles = face_cycles(source)
    out['user_protected_faces'] = len(user_faces)
    out['user_protected_features'] = mark_features(source, plan['features'])
    current = dict(profile['operations'])
    choices = [('Current options', current, profile.get('preserve_curve_segmentation', False))]
    if out['holes'] and (current['arcs'] or current['outer_cylinders']):
        holes = dict(current, circular_holes=True, arcs=False, outer_cylinders=False)
        choices.extend([('Holes only; keep bends', holes, False),
                        ('Holes without support loops', dict(holes, perimeter_loops=False), False)])
    if out['holes']:
        choices.append(('Keep curve segments', dict(current, perimeter_loops=True), True))
    for label, options, preserve in choices[:4]:
        screening = dict(profile, sample_count=750, preserve_curve_segmentation=preserve)
        selected = decisions(plan['features'], options, preserve_curve_segmentation=preserve)
        try:
            print('SCREEN', label, flush=True)
            candidate, mesh, origin, checked = validated_candidate(
                source, selected, options, screening, locked, validation_source=original_source,
                locked_faces=user_faces, locked_cycles=user_cycles)
        except ValueError as error:
            if not is_geometric_conflict(error):
                raise
            out['trials'].append({'label': label, 'error': str(error)})
        else:
            bpy.data.meshes.remove(mesh)
            out['trials'].append({'label': label, 'checks': checked['checks'],
                                  'triangles': checked['after']['t']})
            out['recommendation'] = dict(options, preserve_curve_segmentation=preserve)
            out['passed'] = label
            break
    return out


if __name__ == '__main__':
    root = Path(sys.argv[sys.argv.index('--')+1])
    try:
        source = json.loads((root/'source.json').read_text(encoding='utf-8'))
        profile = json.loads((root/'profile.json').read_text(encoding='utf-8'))
        result = analyze(source, profile)
        result['source_hash'] = source['source_hash']
        (root/'analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        (root/'REPORT.md').write_text('# CAD input analysis\n\n'+source['name']+'\n\n'+result['summary']+
                                    '\n\nCheckpoint screening is advisory, not a certified final result.\n', encoding='utf-8')
    except Exception as error:
        (root/'failure.json').write_text(json.dumps({'error':str(error)}), encoding='utf-8')
        raise
