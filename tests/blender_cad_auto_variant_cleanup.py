"""Auto stops every variant process and frees every slot when something fails.

Covers a failed variant start and a failure while handling a finished
variant. Variant processes are fakes, so no Blender child is started.

blender --background --factory-startup --python tests/blender_cad_auto_variant_cleanup.py
"""
import json
import math
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool import auto_worker
from cad_mesh_tool.mesh_io import capture
from cad_mesh_tool.rebuild import tessellation
from cad_mesh_tool.solids import solid_partitions

outer = np.array([[-.04, -.04], [.04, -.04], [.04, .04], [-.04, .04]])
theta = np.arange(32) * math.tau / 32
holes = [.0065 * np.column_stack((np.cos(theta), np.sin(theta))) + c for c in ((-.02, 0), (.02, 0))]
points, triangles = tessellation([outer, *holes])
n = len(points)
vertices = [(x, y, z) for z in (0, .01) for x, y in points]
faces = [f[::-1] for f in triangles] + [[n + i for i in f] for f in triangles]
for ring, reverse in ((list(range(4)), False), (list(range(4, 36)), True), (list(range(36, 68)), True)):
    for a, b in zip(ring, ring[1:] + ring[:1]):
        faces.append([b, a, a + n, b + n] if reverse else [a, b, b + n, a + n])
mesh = bpy.data.meshes.new('Cleanup plate')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj = bpy.data.objects.new('Cleanup plate', mesh)
bpy.context.scene.collection.objects.link(obj)
source = capture(obj)
partition = solid_partitions(source['faces'], source['vertices'])[0]


class FakeProcess:
    """Stands in for a variant worker; ``finished`` processes exit at once."""

    def __init__(self, finished, stdout):
        self.pid = 900000 + len(started)
        self.returncode = 1 if finished else None
        self.killed = False
        self.stdout = stdout
        started.append(self)

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def setup():
    root = Path(tempfile.mkdtemp(prefix='cad_variant_cleanup_'))
    slots = root / 'slots'
    slots.mkdir()
    (slots / 'capacity.txt').write_text('3')
    profile = dict(epsilon_m=.0015, hole_detail_factor=.5, hole_epsilon_mm=1.5, perimeter_clearance_mm=1.5,
                   sample_count=20000, unit_scale=1.0, variant_slot_dir=str(slots), parallel_variant_triangles=0)
    return root, slots, profile


def check_clean(root, slots, label):
    alive = [p for p in started if p.returncode is None]
    assert not alive, f'{label}: {len(alive)} variant process(es) left running'
    assert not list(slots.glob('slot_*')), f'{label}: slots left claimed {list(slots.glob("slot_*"))}'
    for log in root.rglob('worker.log'):
        log.rename(log.with_suffix('.closed'))  # fails on Windows while a handle is open
    for fake in started:
        assert fake.stdout is None or fake.stdout.closed, f'{label}: worker log handle left open'


# 1) The second variant fails to start while the first is still running.
started = []
root, slots, profile = setup()


def popen_fails_second(*args, **kwargs):
    if started:
        raise OSError('Injected start failure')
    return FakeProcess(False, kwargs.get('stdout'))


with patch.object(auto_worker.subprocess, 'Popen', popen_fails_second):
    try:
        auto_worker.process_body(root, source, profile, 0, partition)
    except OSError as error:
        assert 'Injected start failure' in str(error)
    else:
        raise AssertionError('Start failure was swallowed')
assert len(started) == 1 and started[0].killed
check_clean(root, slots, 'start failure')

# 2) Handling a finished variant fails while other variants still run.
started = []
root, slots, profile = setup()


def popen_first_finishes(*args, **kwargs):
    return FakeProcess(not started, kwargs.get('stdout'))


def checkpoint(item):
    raise RuntimeError('Injected result handling failure')


with patch.object(auto_worker.subprocess, 'Popen', popen_first_finishes):
    try:
        auto_worker.process_body(root, source, profile, 0, partition, checkpoint)
    except RuntimeError as error:
        assert 'Injected result handling failure' in str(error)
    else:
        raise AssertionError('Result handling failure was swallowed')
assert len(started) >= 2 and all(p.killed for p in started[1:]), [(p.returncode, p.killed) for p in started]
check_clean(root, slots, 'result failure')

# 3) The Auto worker records the failure as a FAIL body instead of hanging.
started = []
root, slots, profile = setup()
run = root / 'run'
run.mkdir()
(run / 'source.json').write_text(json.dumps(source))
from cad_mesh_tool.api import code_hash

profile.update(method='CAD_AUTO', delivery='CAD_AUTO_VARIANTS', source_name=obj.name,
               source_hash=source['source_hash'], code_hash=code_hash(), retry_component=None)
(run / 'profile.json').write_text(json.dumps(profile))
with patch.object(auto_worker.subprocess, 'Popen', popen_fails_second):
    auto_worker.main(run)
body = json.loads((run / 'auto_manifest.json').read_text())['bodies'][0]
assert body['status'] == 'FAIL' and 'Injected start failure' in body['reason'], body
check_clean(root, slots, 'main')

# 4) / 5) Preparing the second variant fails after its slot was claimed:
#    the profile cannot be written, or its directory cannot be created.
original_write, original_mkdir = Path.write_text, Path.mkdir


def failing(kind):
    calls = {'n': 0}

    def write_text(path, *args, **kwargs):
        if kind == 'profile' and path.name == 'profile.json':
            calls['n'] += 1
            if calls['n'] == 2:
                raise OSError('Injected profile write failure')
        return original_write(path, *args, **kwargs)

    def mkdir(path, *args, **kwargs):
        if kind == 'mkdir' and path.parent.name.startswith('solid_'):
            calls['n'] += 1
            if calls['n'] == 2:
                raise OSError('Injected mkdir failure')
        return original_mkdir(path, *args, **kwargs)

    return write_text, mkdir


for kind in ('profile', 'mkdir'):
    started = []
    root, slots, profile = setup()
    write_text, mkdir = failing(kind)
    with patch.object(auto_worker.subprocess, 'Popen', popen_first_finishes), \
            patch.object(Path, 'write_text', write_text), patch.object(Path, 'mkdir', mkdir):
        try:
            auto_worker.process_body(root, source, profile, 0, partition)
        except OSError as error:
            assert 'Injected' in str(error), error
        else:
            raise AssertionError(f'{kind} failure was swallowed')
    assert len(started) == 1, f'{kind}: only the first variant started'
    check_clean(root, slots, kind)
print('PASS blender_cad_auto_variant_cleanup')
