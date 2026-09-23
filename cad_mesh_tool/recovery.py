"""Bounded deterministic retries of independently selectable CAD features."""

from .operations import decision


RECOVERABLE_PREFIXES = (
    "UNRESOLVED_PERIMETER", "Candidate topology failed", "Protected feature geometry changed",
    "Protected dependency conflicts",
    "Checkpoint validation failed", "Blender had to repair candidate mesh",
    "Too few independent rim samples", "No ordered rim sample mapping",
    "Conflicting shared", "Shared retained/deleted", "Unmapped nonplanar",
    "Transition contraction", "Unsupported nonplanar incident patch",
    "Planar boundary contraction", "Collapsed incident patch", "Planar coverage mismatch",
    "Cannot propagate a perimeter subdivision", "CDT created ambiguous",
    "Branching cylinder", "Expected two cylinder", "Cylinder end contour",
    "Degenerate face",
)


def is_geometric_conflict(error):
    return isinstance(error, ValueError) and str(error).startswith(RECOVERABLE_PREFIXES)


def decisions(features, operations, accepted=None, reasons=None):
    accepted = set(accepted) if accepted is not None else None
    reasons = reasons or {}
    result = []
    for feature in features:
        item = dict(feature)
        choice = decision(item['category'], operations)
        if accepted is not None and choice != 'DISABLED' and item['id'] not in accepted:
            choice = 'SKIP'
        item['decision'] = choice
        if choice == 'SKIP':
            item['skip_reason'] = reasons.get(item['id'], 'Deferred during safe-recovery search')
        result.append(item)
    return result


def recover(features, operations, attempt, dispose, max_attempts=64, screen_attempt=None):
    """Return a validated candidate and exact skip reasons, or propagate failure.

    The callback must validate and release failed temporary data. A full pass is
    attempted first; only known geometric conflicts permit a bounded search.
    Screening may use fewer deterministic surface samples, but final validation
    always calls the full attempt callback again.
    """
    if max_attempts < 2:
        raise ValueError('Recovery attempt limit must allow a final validation')
    active = [f['id'] for f in features if decision(f['category'], operations) != 'DISABLED']
    tries = 0
    try:
        tries += 1
        result = attempt(decisions(features, operations))
        return result, [], tries
    except Exception as error:
        if not is_geometric_conflict(error) or not active:
            raise
        first_error = error
    accepted = set()
    reasons = {}
    screen_attempt = screen_attempt or attempt
    final_reserve = min(4, max(1, max_attempts // 8))
    for feature_id in active:
        if tries >= max_attempts - final_reserve:
            reasons[feature_id] = f'Recovery attempt limit ({max_attempts}) reached'
            continue
        trial = accepted | {feature_id}
        try:
            tries += 1
            result = screen_attempt(decisions(features, operations, trial, reasons))
        except Exception as error:
            if not is_geometric_conflict(error):
                raise
            reasons[feature_id] = str(error)
        else:
            accepted = trial
            dispose(result)
    for feature_id in active:
        if feature_id not in accepted and feature_id not in reasons:
            reasons[feature_id] = f'Recovery attempt limit ({max_attempts}) reached'
    if not accepted and tries >= max_attempts:
        raise ValueError(f'No safe feature could be reconstructed: {first_error}')
    while True:
        tries += 1
        try:
            result = attempt(decisions(features, operations, accepted, reasons))
        except Exception as error:
            if not is_geometric_conflict(error) or not accepted or tries >= max_attempts:
                raise
            removed = next(feature_id for feature_id in reversed(active) if feature_id in accepted)
            accepted.remove(removed)
            reasons[removed] = str(error)
        else:
            break
    skipped = [dict(feature=feature_id, reason=reasons[feature_id], group='CAD_Skipped')
               for feature_id in active if feature_id not in accepted]
    return result, skipped, tries
