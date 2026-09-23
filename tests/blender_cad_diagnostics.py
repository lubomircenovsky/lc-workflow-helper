"""Check sparse vertex provenance and nonempty CAD review groups."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.diagnostics import add_review_groups, vertex_maps


candidate = dict(vertices=[(0, 0, 0)] * 4,
                 source_to_candidate=[0, -1, 2],
                 candidate_to_source=[0, -1, 2, -1],
                 review_features=[
                     dict(id=2, group='CAD_Review_Constrained', reason='kept samples',
                          source_vertices=[0, 1]),
                     dict(id=3, group='CAD_Skipped', reason='unsafe fit',
                          source_vertices=[2]),
                 ])
mapping = vertex_maps(candidate, [0, -1, 1, 2])
assert mapping['source_to_final'] == [0, -1, 1]
assert mapping['removed_source_vertices'] == [1]
assert mapping['generated_candidate_vertices'] == [1, 3]
mesh = bpy.data.meshes.new('CAD Diagnostic Triangle')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
mesh.update()
obj = bpy.data.objects.new('CAD Diagnostic Triangle', mesh)
bpy.context.scene.collection.objects.link(obj)
report = add_review_groups(obj, candidate, mapping['candidate_to_final'])
assert {group.name for group in obj.vertex_groups} == {
    'CAD_Review_Constrained', 'CAD_Skipped', 'CAD_Review_InvalidBoundary'}
assert next(item for item in report if item['feature'] == 2)['unmapped_source_vertices'] == 1
assert next(item for item in report if item['feature'] is None)['vertices'] == 3
print('CAD_DIAGNOSTICS_OK', mapping['source_to_final'], [item['group'] for item in report])
