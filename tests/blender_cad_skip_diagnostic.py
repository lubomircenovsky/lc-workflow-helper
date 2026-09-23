"""Read-only reproduction of an unsafe feature skip using saved CAD inputs."""
import ast
import inspect
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cad_mesh_tool.rebuild as rebuild


root = Path(sys.argv[sys.argv.index('--') + 1])
feature_id = int(sys.argv[sys.argv.index('--') + 2])
source = json.loads((root / 'source.json').read_text(encoding='utf-8'))
plan = json.loads((root / 'plan.json').read_text(encoding='utf-8'))
feature = next(item for item in plan['features'] if item['id'] == feature_id)
feature['decision'] = 'SKIP'

# Reproduce the pre-fix uniform-target alias and unconditional vertex snap
# without changing the production module or source fixture.
code = inspect.getsource(rebuild.reconstruct)
old_snap = '''                    if preserve_samples:
                        avoided_move=max(avoided_move,float(np.linalg.norm(target-V[vi])))
                    else:
                        if vi in changed and np.linalg.norm(np.array(vertices[vi])-target)>1e-6:raise ValueError('Conflicting shared analytic endpoint')
                        vertices[vi]=target.tolist();changed.add(vi)'''
new_snap = '''                    if vi in changed and np.linalg.norm(np.array(vertices[vi])-target)>1e-6:raise ValueError('Conflicting shared analytic endpoint')
                    vertices[vi]=target.tolist();changed.add(vi)'''
assert old_snap in code
code = code.replace(old_snap, new_snap)
old_alias = '''            for vi,replacement in rim_aliases(ids,row,theta,cy['full']).items():'''
new_alias = '''            for vi in ids:
                def sample_distance(k):
                    d=abs(theta[vi]-cy['span']*k/n)
                    return min(d,2*math.pi-d) if cy['full'] else d
                replacement=row[min(range(len(row)),key=sample_distance)]'''
assert old_alias in code
code = code.replace(old_alias, new_alias)
start = code.index('            if radius is not None and all(inside(x,outer) for x in hole)')
end = code.index('            sq,attempts=sparse if sparse is not None else choose_perimeter', start)
code = code[:start] + code[end:]
namespace = dict(rebuild.__dict__)
exec(code, namespace)
legacy_reconstruct = namespace['reconstruct']
incidence = defaultdict(list)
for face_id, face in enumerate(source['faces']):
    for a, b in zip(face, face[1:] + face[:1]):
        incidence[tuple(sorted((a, b)))].append(face_id)
try:
    legacy_reconstruct(source, plan['features'])
except ValueError as error:
    message = str(error)
    if 'boundary_source_index_edges=' not in message:
        raise
    edges = ast.literal_eval(message.split('boundary_source_index_edges=', 1)[1])
    print('BOUNDARY_EDGE_COUNT', len(edges))
    for edge in edges:
        print('OPEN_EDGE', edge, 'SOURCE_FACES', incidence[tuple(edge)],
              'SKIPPED_FACES', sorted(set(incidence[tuple(edge)]) & set(feature['faces'])))
else:
    raise AssertionError('The skipped feature unexpectedly produced a valid candidate')
