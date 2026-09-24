"""Trace CAD diagnostic vertices through reconstruction and mesh cleanup."""
from collections import Counter


def vertex_maps(candidate, candidate_to_final):
    source_to_candidate = candidate['source_to_candidate']
    candidate_to_source = candidate['candidate_to_source']
    if len(candidate_to_source) != len(candidate_to_final):
        raise ValueError('Candidate/final vertex map length mismatch')
    source_to_final = [candidate_to_final[i] if i >= 0 else -1
                       for i in source_to_candidate]
    final_count = max(candidate_to_final, default=-1) + 1
    final_to_candidate = [[] for _ in range(final_count)]
    for candidate_id, final_id in enumerate(candidate_to_final):
        if final_id >= 0:
            final_to_candidate[final_id].append(candidate_id)
    return dict(source_to_candidate=source_to_candidate,
                candidate_to_source=candidate_to_source,
                candidate_to_final=list(candidate_to_final),
                source_to_final=source_to_final,
                final_to_candidate=final_to_candidate,
                removed_source_vertices=[i for i, j in enumerate(source_to_candidate) if j < 0],
                generated_candidate_vertices=[i for i, j in enumerate(candidate_to_source) if j < 0])


def invalid_boundary_vertices(mesh, ignored_edges=()):
    ignored={tuple(sorted(edge)) for edge in ignored_edges}
    incidence = Counter(tuple(sorted((a, b))) for face in mesh.polygons
                        for a, b in zip(face.vertices, (*face.vertices[1:], face.vertices[0])))
    return sorted({vertex for edge in mesh.edge_keys if tuple(sorted(edge)) not in ignored
                   and incidence.get(tuple(sorted(edge)),0) != 2
                   for vertex in edge})


def add_review_groups(obj, candidate=None, candidate_to_final=None):
    """Attach only nonempty groups to a generated object, never to the source."""
    report = []
    if candidate is not None:
        source_to_candidate = candidate['source_to_candidate']
        if candidate_to_final is None:
            candidate_to_final = list(range(len(candidate['vertices'])))
        grouped = {}
        for item in candidate.get('review_features', []):
            name = item['group']
            indices = grouped.setdefault(name, set())
            missing = 0
            for candidate_id in item.get('candidate_vertices', []):
                final_id = candidate_to_final[candidate_id]
                if final_id >= 0:
                    indices.add(final_id)
                else:
                    missing += 1
            for source_id in item['source_vertices']:
                candidate_id = source_to_candidate[source_id]
                final_id = candidate_to_final[candidate_id] if candidate_id >= 0 else -1
                if final_id >= 0:
                    indices.add(final_id)
                else:
                    missing += 1
            report.append(dict(feature=item['id'],reason=item['reason'],group=name,
                               avoided_displacement_m=item.get('avoided_displacement_m',0.),
                               unmapped_source_vertices=missing))
        for name, indices in sorted(grouped.items()):
            if indices:
                obj.vertex_groups.new(name=name).add(sorted(indices), 1.0, 'REPLACE')
    expected=[]
    if candidate is not None:
        expected=[[candidate_to_final[vi] for vi in edge]
                  for edge in candidate.get('preserved_nonmanifold_edges',[])]
    invalid = invalid_boundary_vertices(obj.data,expected)
    if invalid:
        obj.vertex_groups.new(name='CAD_Review_InvalidBoundary').add(invalid, 1.0, 'REPLACE')
        report.append(dict(feature=None,reason='Output has boundary or non-manifold edges',
                           group='CAD_Review_InvalidBoundary',vertices=len(invalid)))
    return report
