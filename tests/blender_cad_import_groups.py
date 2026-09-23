"""Verify CAD diagnostic groups and source identity after importing a saved run."""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import apply_result
from cad_mesh_tool.mesh_io import fingerprint


run_dir = Path(sys.argv[sys.argv.index('--') + 1])
source = bpy.data.objects['Těleso1.023']
before = fingerprint(source)
manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
mapping = json.loads((run_dir / 'vertex_map.json').read_text(encoding='utf-8'))
candidate = json.loads((run_dir / 'candidate.json').read_text(encoding='utf-8'))
names = apply_result(run_dir, include_checkpoint=False)
assert len(names) == 1
output = bpy.data.objects[names[0]]
assert output.data != source.data
assert fingerprint(source) == before == manifest['source_hash']
assert len(mapping['source_to_candidate']) == len(source.data.vertices)
assert len(mapping['candidate_to_final']) == len(mapping['candidate_to_source'])
assert len(mapping['final_to_candidate']) == len(output.data.vertices)
assert all(mapping['source_to_final'][i] == (
    mapping['candidate_to_final'][candidate] if candidate >= 0 else -1)
    for i, candidate in enumerate(mapping['source_to_candidate']))
scale = bpy.context.scene.unit_settings.scale_length
for candidate_id, final_id in enumerate(mapping['candidate_to_final']):
    if final_id < 0:
        continue
    position = np.asarray(output.matrix_world @ output.data.vertices[final_id].co) * scale
    expected_position = np.asarray(candidate['vertices'][candidate_id])
    assert np.linalg.norm(position - expected_position) < 1e-6, (candidate_id, final_id)
expected = {item['group'] for item in manifest['review_groups']}
actual = {group.name for group in output.vertex_groups}
assert actual == expected, (actual, expected)
for group in output.vertex_groups:
    members = [vertex.index for vertex in output.data.vertices
               if any(item.group == group.index for item in vertex.groups)]
    assert members, group.name
assert 'CAD_Review_Constrained' in actual
print('CAD_IMPORT_GROUPS_OK', names[0], actual,
      len(mapping['removed_source_vertices']), len(mapping['generated_candidate_vertices']))
