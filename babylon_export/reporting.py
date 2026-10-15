"""Typed historical operation results; no readiness checks or report parsing."""


def issue_outcome(issues):
    levels = {item.level for item in issues}
    return 'ERROR' if 'ERROR' in levels else 'WARNING' if 'WARNING' in levels else 'OK'


def store_outcome(state, collection, operation, outcome):
    """Call only after an operation stops, never from draw or a running bake."""
    state.last_operation = operation
    state.last_outcome = outcome
    state.report_scene_collection = False
    try:
        if getattr(collection, 'is_embedded_data', False):
            state.report_collection = None
            state.report_scene_collection = True
        else:
            state.report_collection = collection
    except ReferenceError:
        state.report_collection = None  # The collection was deleted during the operation.


def _reported_target(state, collection):
    if getattr(state, 'report_scene_collection', False):
        return getattr(collection, 'is_embedded_data', False)
    return state.report_collection is not None and state.report_collection == collection


def last_operation_status(state, collection):
    if state.last_outcome == 'UNKNOWN' or state.last_operation == 'UNKNOWN':
        return 'idle', 'Last report \u2014 outcome unavailable'
    if not _reported_target(state, collection):
        name = ('Scene Collection' if getattr(state, 'report_scene_collection', False) else
                state.report_collection.name if state.report_collection else 'collection unavailable')
        return 'info', f'Last report: {name}'
    operation = {
        'CHECK': 'Check', 'BAKE': 'Bake', 'BAKE_EXPORT': 'Bake & Export',
        'EXPORT': 'Export', 'CLEANUP': 'Clean Up',
    }.get(state.last_operation, 'Operation')
    outcome = state.last_outcome
    if outcome == 'OK':
        detail = {'CHECK': 'no issues reported', 'EXPORT': 'verified'}.get(
            state.last_operation, 'finished')
    else:
        detail = {'WARNING': 'warnings', 'ERROR': 'failed', 'CANCELLED': 'cancelled'}.get(
            outcome, 'outcome unavailable')
    icon = {'OK': 'ok', 'WARNING': 'warning', 'ERROR': 'error',
            'CANCELLED': 'cancelled'}.get(outcome, 'idle')
    return icon, f'Last {operation}: {detail}'
