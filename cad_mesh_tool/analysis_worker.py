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
from cad_mesh_tool.solids import components, solid_partitions
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
        from cad_mesh_tool.source_repair import repair_collinear_faces
        original_source = source
        try:
            source, source_repair = repair_collinear_faces(source)
        except ValueError as error:
            result.update(blocked=True, summary=str(error), seconds=time.perf_counter()-started)
            return result
        result['source_repair'] = source_repair
        print('DISCOVER', flush=True)
        plan = discover(source['vertices'], source['faces'], profile['epsilon_m'],
                        profile.get('hole_detail_factor', 1.),
                        (profile.get('hole_epsilon_mm', 0.)/1000) or None)
        result['categories'] = dict(Counter(f['category'] for f in plan['features']))
        result['holes'] = [{'id': f['id'], 'before': f['segments_before'], 'target': f['segments']}
                           for f in plan['features'] if f['category'] == 'circular_hole']
        locked = protection(source, plan['features']) if counts['nonmanifold'] else None
        if locked:
            for feature in plan['features']:
                if feature['id'] in locked['features']:
                    feature['forced_skip_reason'] = 'Touches an unchanged source non-manifold junction'
        current = dict(profile['operations'])
        choices = [('Current options', current, profile.get('preserve_curve_segmentation', False))]
        if result['holes'] and (current['arcs'] or current['outer_cylinders']):
            holes = dict(current, circular_holes=True, arcs=False, outer_cylinders=False)
            choices.extend([('Holes only; keep bends', holes, False),
                            ('Holes without support loops', dict(holes, perimeter_loops=False), False)])
        if result['holes']:
            choices.append(('Keep curve segments', dict(current, perimeter_loops=True), True))
        for label, options, preserve in choices[:4]:
            screening = dict(profile, sample_count=750, preserve_curve_segmentation=preserve)
            selected = decisions(plan['features'], options, preserve_curve_segmentation=preserve)
            try:
                print('SCREEN', label, flush=True)
                candidate, mesh, origin, checked = validated_candidate(source, selected, options, screening, locked,
                                                                       validation_source=original_source)
            except ValueError as error:
                if not is_geometric_conflict(error):
                    raise
                result['trials'].append({'label': label, 'error': str(error)})
            else:
                bpy.data.meshes.remove(mesh)
                result['trials'].append({'label': label, 'checks': checked['checks'],
                                        'triangles': checked['after']['t']})
                result['recommendation'] = dict(options, preserve_curve_segmentation=preserve)
                result['summary'] = (f"{label} passed checkpoint screening (750 area samples plus vertices, edges and centroids). "
                                     'Reconstruct still performs full validation and cleanup.')
                break
        if result['recommendation'] is None:
            result['summary'] = 'No screened profile passed. Inspect trial errors; repair dependent boundaries or run a smaller operation set.'
        result['blocked'] = False
    result['seconds'] = time.perf_counter()-started
    return result


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
