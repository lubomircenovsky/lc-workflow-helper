"""Regression with immutable .004/Solid004 source/profile fixture supplied after --.

Blender --background --factory-startup --python-exit-code 1 --python this.py -- RUN_DIR
The fixture is external production data; never mutate it or the input feature plan.
"""
import copy
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover
from cad_mesh_tool.recovery import decisions
from cad_mesh_tool.worker import validated_candidate

if '--' not in sys.argv:
    print('SKIP blender_cad_production_backoff: requires external production data after --')
    sys.exit(0)
root = Path(sys.argv[sys.argv.index('--')+1])
source = json.loads((root/'source.json').read_text())
profile = json.loads((root/'profile.json').read_text())
plan = discover(source['vertices'], source['faces'], profile['epsilon_m'],
                profile['hole_detail_factor'], profile['hole_epsilon_mm']/1000)
assert len(plan['features']) == 20
features = decisions(plan['features'], profile['operations'])
original = copy.deepcopy(features)
timings = {}
candidate, mesh, origin, validation = validated_candidate(
    source, features, profile['operations'], profile, timings=timings)
try:
    assert features == original
    assert all(validation['checks'].values()), validation['checks']
    actual = candidate['actual_feature_segments']
    assert len(actual) == 20 and all(item['actual']<item['before'] for item in actual)
    assert {item['id'] for item in candidate['segment_backoffs']} == {6,8,18}
    assert len(timings['segment_attempts']) == 2
    assert timings['segment_attempts'][0]['failed_checks'] == ['sampled_distance']
    assert len(candidate['perimeters']) == 4
    print('CAD_PRODUCTION_SHARED_RAIL_BACKOFF_OK')
finally:
    bpy.data.meshes.remove(mesh)
