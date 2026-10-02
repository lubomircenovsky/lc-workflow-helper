"""Deterministic Auto profiles and final-result ordering; no Blender dependency."""
from .operations import DEFAULTS


def variants(features):
    curved = bool(features)
    holes = any(f['category'] == 'circular_hole' for f in features)
    result = [('full', dict(DEFAULTS, perimeter_loops=False), False)]
    if holes:
        result.append(('full_loops', dict(DEFAULTS), False))
    if curved:
        result.append(('keep_segments', dict(DEFAULTS, perimeter_loops=False), True))
    return result


def fallback_variant(features, trials):
    holes = any(f['category'] == 'circular_hole' for f in features)
    bends = any(f['category'] != 'circular_hole' for f in features)
    failed_full = any(t['variant'] in {'full', 'full_loops'} and
                      (t['status'] == 'FAIL' or t.get('skipped', 0)) for t in trials)
    if holes and bends and failed_full:
        return ('holes_only', dict(DEFAULTS, perimeter_loops=False, arcs=False,
                                  outer_cylinders=False), False)
    return None


def rank(trial):
    return (trial['triangles'], -trial['reduced'], -trial['accepted'], trial['order'])


def winner(trials):
    passed = [t for t in trials if t['status'] != 'FAIL']
    return min(passed, key=rank) if passed else None


def completed_bodies(report, timed_out=False):
    """Read only completed geometry; timeout may retain an unfinished search's best."""
    bodies = list(report['bodies'])
    if not timed_out:return bodies
    known = {body['component_index'] for body in bodies}
    active = report.get('active_body')
    if active and active.get('winner') and active['component_index'] not in known:
        active = dict(active, status='REVIEW', search_complete=False,
                      reason='Time limit reached; best fully validated completed variant retained. '+active['reason'])
        bodies.append(active)
        known.add(active['component_index'])
    indices = report.get('selected_components', range(len(report['partitions'])))
    for index in indices:
        if index not in known:
            bodies.append(dict(component_index=index, status='FAIL', winner=None,
                               reason='Worker time limit reached before this solid completed.'))
    return bodies
