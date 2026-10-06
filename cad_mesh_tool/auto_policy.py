"""Deterministic Auto profiles and final-result ordering; no Blender dependency."""
from .operations import DEFAULTS


def solid_order(partitions, retry=None):
    """Finish smaller independent bodies first without changing their identity."""
    if retry is not None:
        return [retry]
    return sorted(range(len(partitions)),
                  key=lambda index: (len(partitions[index]['faces']), index))


def variants(features):
    curved = bool(features)
    holes = any(f['category'] == 'circular_hole' for f in features)
    # Establish a fully validated planar baseline before expensive curve
    # recovery, so a worker deadline can retain useful completed geometry.
    result = ([('keep_segments', dict(DEFAULTS, perimeter_loops=False), True)]
              if curved else [])
    result.append(('full', dict(DEFAULTS, perimeter_loops=False), False))
    if holes:
        result.append(('full_loops', dict(DEFAULTS), False))
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


OBJECTIVES = ('LIGHTWEIGHT', 'EDITABLE')


def objective_name(value=None):
    value = value or 'LIGHTWEIGHT'
    if value not in OBJECTIVES:
        raise ValueError(f'Unknown Auto objective: {value}')
    return value


def rank(trial, objective='LIGHTWEIGHT'):
    """Lower is better. Every ranked trial already passed full validation.

    LIGHTWEIGHT: fewest final triangles, then more reduced/reconstructed regions.
    EDITABLE: fewest retained regions, then more support loops around holes,
    then the LIGHTWEIGHT order. Triangle count no longer outranks loops.
    """
    lightweight = (trial['triangles'], -trial['reduced'], -trial['accepted'], trial['order'])
    if objective_name(objective) == 'EDITABLE':
        return (len(trial.get('untreated', ())), -trial.get('loops', 0)) + lightweight
    return lightweight


def winner(trials, objective='LIGHTWEIGHT'):
    passed = [t for t in trials if t['status'] != 'FAIL']
    return min(passed, key=lambda trial: rank(trial, objective)) if passed else None


def completed_bodies(report, timed_out=False, interrupted_reason=None,
                     include_unfinished=True):
    """Keep validated checkpoints after deadlines, cancellation or worker failure."""
    bodies = list(report['bodies'])
    reason = 'Time limit reached' if timed_out else interrupted_reason
    if not reason:return bodies
    known = {body['component_index'] for body in bodies}
    active = report.get('active_body')
    if active and active.get('winner') and active['component_index'] not in known:
        active = dict(active, status='REVIEW', search_complete=False,
                      reason=reason+'; best fully validated completed variant retained. '+active['reason'])
        bodies.append(active)
        known.add(active['component_index'])
    if not include_unfinished:return bodies
    indices = report.get('selected_components', range(len(report['partitions'])))
    for index in indices:
        if index not in known:
            bodies.append(dict(component_index=index, status='FAIL', winner=None,
                               reason=reason+' before this solid completed.'))
    return bodies
