"""Run against the user-supplied .blend without saving it."""

import json
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.api import apply_result, prepare_selected
from cad_mesh_tool.mesh_io import fingerprint
from cad_mesh_tool.operations import DEFAULTS
from cad_mesh_tool.worker import main


source = bpy.data.objects.get('T\u011bleso1.023')
assert source is not None, 'Production source object is missing'
original = fingerprint(source)
operations = dict(DEFAULTS)
if '--no-perimeters' in sys.argv:
    operations['perimeter_loops'] = False
with tempfile.TemporaryDirectory() as directory:
    run = Path(directory) / 'production'
    prepare_selected(run, obj=source, operations=operations)
    main(run)
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['geometry_status'] == 'PASS'
    assert all(json.loads((run / name).read_text(encoding='utf-8'))['checks'].values()
               for name in ('validation_checkpoint.json', 'validation_final.json'))
    names = apply_result(run, include_checkpoint=False)
    assert len(names) == 1
    output = bpy.data.objects[names[0]]
    assert output.data is not source.data
    assert fingerprint(source) == original
    assert not any(obj.get('cad_checkpoint') for obj in bpy.context.scene.objects if obj != source)
    print('CAD_PRODUCTION_RESULT', operations['perimeter_loops'], manifest['partial'], manifest['recovery_attempts'],
          len(manifest['skipped_features']), manifest['final']['t'], manifest['summary'])
