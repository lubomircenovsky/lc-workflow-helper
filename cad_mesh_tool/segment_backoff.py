"""Propose bounded local segment relaxation; every proposal needs full validation."""
import numpy as np


def relax_near_distance_failure(source, features, validation):
    """Keep detection, disabled features and geometric tolerances unchanged.

    Nearest source vertices identify candidate owners, not proof of causality.
    The caller must reconstruct and validate the complete candidate again.
    """
    failed = {key for key, passed in validation['checks'].items() if not passed}
    if failed != {'sampled_distance'}:
        return []
    vertices = np.asarray(source['vertices'])
    near = set()
    for distance in validation['distance'].values():
        if distance['within_limits']:
            continue
        point = np.asarray(distance.get('worst_budget_sample_centered_m',
                                        distance['worst_sample_centered_m']))
        point = point + validation['distance_reference_center_m']
        near.update(np.argsort(np.sum((vertices-point)**2, axis=1), kind='stable')[:3].tolist())
    changes = []
    for feature in features:
        if (feature.get('decision') != 'REBUILD' or
                feature['segments'] >= feature['segments_before'] or
                not near.intersection(feature['vertices'])):
            continue
        previous = feature['segments']
        feature['segments'] = (previous + feature['segments_before'] + 1) // 2
        changes.append(dict(id=feature['id'], previous=previous, actual=feature['segments']))
    return changes
