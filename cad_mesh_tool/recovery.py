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
    "Protected non-manifold region changed",
    "Material boundary in planar patch", "Shading boundary in planar patch",
    "Region boundary branches or is open", "Non-simple boundary",
    "Measured cylinder end contours", "Conflicting nested edge subdivisions",
    "Self-touching nested edge subdivisions", "Cannot propagate subdivisions",
)


def is_geometric_conflict(error):
    return isinstance(error, ValueError) and str(error).startswith(RECOVERABLE_PREFIXES)


def decisions(features, operations, accepted=None, reasons=None,
              preserve_curve_segmentation=False):
    accepted = set(accepted) if accepted is not None else None
    reasons = reasons or {}
    result = []
    for feature in features:
        item = dict(feature)
        choice = decision(item['category'], operations, preserve_curve_segmentation)
        if choice != 'DISABLED' and item.get('forced_skip_reason'):
            choice = 'SKIP'
        if accepted is not None and choice != 'DISABLED' and item['id'] not in accepted:
            choice = 'SKIP'
        item['decision'] = choice
        if choice == 'SKIP':
            item['skip_reason'] = item.get('forced_skip_reason') or reasons.get(
                item['id'], 'Deferred during safe-recovery search')
        result.append(item)
    return result


def recover(features, operations, attempt, dispose, max_attempts=64, screen_attempt=None,
            preserve_curve_segmentation=False):
    """Return a validated candidate and exact skip reasons, or propagate failure.

    The callback must validate and release failed temporary data. A full pass is
    attempted first; only known geometric conflicts permit a bounded search.
    Screening may use fewer deterministic surface samples, but final validation
    always calls the full attempt callback again.
    """
    if max_attempts < 2:
        raise ValueError('Recovery attempt limit must allow a final validation')
    fixed = [f for f in features if f.get('forced_skip_reason')
             and decision(f['category'], operations, preserve_curve_segmentation) != 'DISABLED']
    active = [f['id'] for f in features if decision(f['category'], operations, preserve_curve_segmentation) != 'DISABLED'
              and not f.get('forced_skip_reason')]
    tries = 0
    try:
        tries += 1
        result = attempt(decisions(features, operations,
                                   preserve_curve_segmentation=preserve_curve_segmentation))
        return result, [dict(feature=f['id'],reason=f['forced_skip_reason'],group='CAD_Skipped')
                        for f in fixed], tries
    except Exception as error:
        if not is_geometric_conflict(error) or not active:
            raise
        first_error = error
    supplemental=[f for f in features if f.get('measured_axis') and f['id'] in active]
    supplemental_ids={f['id'] for f in supplemental}
    established=[f for f in features if f['id'] not in supplemental_ids]
    if supplemental and established and max_attempts-tries>=2:
        # New proposals must not turn a previously reconstructable body into
        # an all-protected dependency group. The first attempt above fully
        # validates the extended set. On failure retry the established set,
        # spending the SAME bounded recovery budget and reporting every omitted
        # proposal. User-disabled operations and non-manifold protection remain
        # enforced by the ordinary callback.
        result,skipped,used=recover(established,operations,attempt,dispose,
            max_attempts=max_attempts-tries,screen_attempt=screen_attempt,
            preserve_curve_segmentation=preserve_curve_segmentation)
        skipped.extend(dict(feature=f['id'],group='CAD_Skipped',
            reason=f'Supplemental bend set failed: {first_error}; established features retried',
            detected_not_reconstructed=True)
            for f in supplemental)
        return result,skipped,tries+used
    accepted = set()
    reasons = {}
    screen_attempt = screen_attempt or attempt
    final_reserve = min(4, max(1, max_attempts // 8))
    # Shared bends may only be valid together: screen their connected groups
    # before the old single-feature search. Failed groups still fall back to
    # individual trials; every accepted combination receives full validation.
    by_id={f['id']:f for f in features}
    pending=set(active)
    groups=[]
    while pending:
        seed=min(pending);pending.remove(seed)
        group={seed};stack=[seed]
        while stack:
            current=by_id[stack.pop()]
            family=current['category']=='circular_hole'
            vertices=set(current['vertices'])
            neighbors={fid for fid in pending
                       if (by_id[fid]['category']=='circular_hole')==family
                       and vertices.intersection(by_id[fid]['vertices'])}
            pending-=neighbors;group|=neighbors;stack.extend(sorted(neighbors))
        if len(group)>1:groups.append(group)
    # Spend at most a quarter of the search on joint transactions.
    for group in groups[:max_attempts//4]:
        if tries>=max_attempts-final_reserve:break
        try:
            tries+=1
            result=screen_attempt(decisions(features,operations,accepted|group,reasons,
                                           preserve_curve_segmentation))
        except Exception as error:
            if not is_geometric_conflict(error):raise
        else:
            accepted|=group
            dispose(result)
    for feature_id in active:
        if feature_id in accepted:continue
        if tries >= max_attempts - final_reserve:
            reasons[feature_id] = f'Recovery attempt limit ({max_attempts}) reached'
            continue
        trial = accepted | {feature_id}
        try:
            tries += 1
            result = screen_attempt(decisions(features, operations, trial, reasons,
                                              preserve_curve_segmentation))
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
            result = attempt(decisions(features, operations, accepted, reasons,
                                       preserve_curve_segmentation))
        except Exception as error:
            if not is_geometric_conflict(error) or not accepted or tries >= max_attempts:
                raise
            removed = next(feature_id for feature_id in reversed(active) if feature_id in accepted)
            accepted.remove(removed)
            reasons[removed] = str(error)
        else:
            break
    skipped = [dict(feature=f['id'],reason=f['forced_skip_reason'],group='CAD_Skipped')
               for f in fixed]
    skipped.extend(dict(feature=feature_id, reason=reasons[feature_id], group='CAD_Skipped')
                   for feature_id in active if feature_id not in accepted)
    return result, skipped, tries
