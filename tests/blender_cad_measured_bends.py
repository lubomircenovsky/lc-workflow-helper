"""Validate selected production bends from an external immutable selection JSON.

Blender --background --factory-startup --python this.py -- selection.json
The fixture stores baseline source paths and source polygon IDs, never edits them.
"""
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.detect import discover, _discover
from cad_mesh_tool.recovery import decisions
from cad_mesh_tool.worker import validated_candidate

if '--' not in sys.argv:
    print('SKIP blender_cad_measured_bends: requires external production data after --')
    sys.exit(0)
fixture=Path(sys.argv[sys.argv.index('--')+1])
for row in json.loads(fixture.read_text()):
    root=Path(row['baseline'])
    source=json.loads((root/'source.json').read_text())
    profile=json.loads((root/'profile.json').read_text())
    assert source['source_hash']==row['source_hash']
    args=(source['vertices'],source['faces'],profile['epsilon_m'],
          profile.get('hole_detail_factor',1.),(profile.get('hole_epsilon_mm',0.)/1000) or None)
    legacy=_discover(*args)['features']
    plan=discover(*args)
    assert plan['features'][:len(legacy)]==legacy
    selected=set(row['selected_source_faces'])
    assert not selected & {fi for f in legacy for fi in f['faces']}
    assert selected <= {fi for f in plan['features'] for fi in f['faces']}
    candidate,mesh,origin,validation=validated_candidate(
        source,decisions(plan['features'],profile['operations']),profile['operations'],profile)
    try:
        assert all(validation['checks'].values()),validation['checks']
        rebuilt={f['id'] for f in candidate['actual_feature_segments']}
        assert selected <= {fi for f in plan['features'] if f['id'] in rebuilt for fi in f['faces']}
        assert len(rebuilt)>len(legacy)
        assert not candidate.get('segment_backoffs')
        print('CAD_MEASURED_BENDS_OK',row['name'],len(selected),len(legacy),'->',len(rebuilt))
    finally:
        bpy.data.meshes.remove(mesh)
print('PASS blender_cad_measured_bends')
