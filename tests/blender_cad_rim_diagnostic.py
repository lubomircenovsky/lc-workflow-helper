"""Read-only diagnostic for a saved CAD source/plan pair."""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cad_mesh_tool.rebuild import cylinder_rims, select_rim_samples
from cad_mesh_tool.geometry import face_normals


root = Path(sys.argv[sys.argv.index('--') + 1])
feature_id = int(sys.argv[sys.argv.index('--') + 2])
source = json.loads((root / 'source.json').read_text(encoding='utf-8'))
plan = json.loads((root / 'plan.json').read_text(encoding='utf-8'))
feature = next(item for item in plan['features'] if item['id'] == feature_id)
vertices = np.asarray(source['vertices'])
frame = np.asarray(feature['frame'])
origin = np.asarray(feature['origin'])
p = (vertices - origin) @ frame.T
center = np.asarray(feature['center'])
angle_rows = []
alias_violations = []
all_displacements = []
for ids, end_normal, end_d in cylinder_rims(feature, p):
    angles = {i: float((math.atan2(p[i, 1] - center[1], p[i, 0] - center[0]) - feature['start']) % (2 * math.pi)) for i in ids}
    angles = {i: 0. if abs(a - 2 * math.pi) < 1e-4 else a for i, a in angles.items()}
    count = feature['segments'] if feature['full'] else feature['segments'] + 1
    row = select_rim_samples(ids, angles, count, feature['span'], feature['full'])
    angle_rows.append([(i, round(angles[i], 8)) for i in row])
    for i in ids:
        replacement = row[min(range(len(row)), key=lambda k: abs(angles[i] - feature['span'] * k / feature['segments']))]
        if i in row and replacement != i:
            alias_violations.append((i, replacement))
    for k, vi in enumerate(row):
        if k in (0, feature['segments']) and not feature['full']:
            continue
        a = feature['start'] + feature['span'] * k / feature['segments']
        xy = center + feature['radius'] * np.array([math.cos(a), math.sin(a)])
        z = (end_d - end_normal[:2] @ xy) / end_normal[2]
        target = np.array([*xy, z]) @ frame + origin
        all_displacements.append((vi, float(np.linalg.norm(target - vertices[vi]))))
print('RIMS', angle_rows)
print('ALIAS_VIOLATIONS', alias_violations)
print('DISPLACEMENTS_M', all_displacements)
print('MAX_DISPLACEMENT_M', max((d for _, d in all_displacements), default=0))
faces = source['faces']
face_n = face_normals(vertices, faces)
radial_errors = []
normal_support = []
for fi in feature['faces']:
    for vi in faces[fi]:
        local = p[vi]
        radial = local[:2] - center
        radial_errors.append(abs(np.linalg.norm(radial) - feature['radius']))
        outward = np.array([*radial / np.linalg.norm(radial), 0.]) @ frame
        normal_support.append(float(face_n[fi] @ outward) * feature['sign'])
print('MAX_SOURCE_RADIAL_ERROR_M', max(radial_errors))
print('NORMAL_SUPPORT_MIN_MEDIAN', min(normal_support), float(np.median(normal_support)))
