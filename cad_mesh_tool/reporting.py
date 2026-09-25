"""User-facing CAD failure explanations; technical details remain in JSON/logs."""


EXPLANATIONS = (
    ('No selected operation produced', 'The selected steps made no validated change, so no duplicate output was created.'),
    ('No safe feature could be reconstructed', 'No feature could be changed safely; the source was left untouched.'),
    ('UNRESOLVED_PERIMETER', 'There is not enough safe space to build a support loop around this opening.'),
    ('Candidate topology failed', 'The proposed surfaces would leave an open or inconsistent mesh.'),
    ('Protected feature geometry changed', 'This change would alter a disabled or preserved feature.'),
    ('Protected non-manifold region changed', 'The original non-manifold junction could not be kept unchanged.'),
    ('Protected sharp edge removed', 'An authored sharp edge was removed. The changed mesh needs shading review.'),
    ('Protected dependency conflicts', 'A neighboring reconstruction would change the boundary of a preserved area.'),
    ('Checkpoint validation failed', 'The proposed geometry did not pass the full geometry checks.'),
    ('Editable validation failed', 'The editable result did not pass the full geometry checks.'),
    ('Too few independent rim samples', 'The opening or arc has too few distinct vertices for the proposed reduction.'),
    ('Degenerate face', 'Rebuilding this feature would create an invalid zero-area face.'),
    ('Conflicting shared', 'Adjacent features need incompatible positions for a shared vertex.'),
    ('Planar boundary contraction', 'The surrounding sheet would become self-touching.'),
    ('Collapsed incident patch', 'The surrounding sheet would collapse after reducing this feature.'),
    ('Planar coverage mismatch', 'The rebuilt sheet does not cover the same area as the source.'),
    ('Shading boundary in planar patch',
     'Face directions differ within an area expected to be flat. Review the local geometry and winding; '
     'source custom normals are already ignored.'),
    ('Straight wall cleanup', 'Merging straight walls did not preserve the validated geometry.'),
    ('Protected faces lost', 'Cleanup would remove geometry that must remain unchanged.'),
)


def explain(reason):
    for prefix, message in EXPLANATIONS:
        if reason.startswith(prefix):
            return message
    return 'This operation could not produce a validated result. See the run files for technical details.'


def skipped_summary(skipped):
    """Surface a shared actionable cause without hiding mixed skip reasons."""
    shading = sum(item['reason'].startswith('Shading boundary in planar patch') for item in skipped)
    if not shading:
        return ''
    others = len(skipped) - shading
    message = f'{shading} feature(s) skipped: face directions conflict in a flat region.'
    if others:
        message += f' {others} other feature(s) also need review.'
    return message
