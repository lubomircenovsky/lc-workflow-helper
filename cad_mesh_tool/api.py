"""Small live-Blender interface: prepare_selected(), then apply_result()."""
import hashlib,json,math
from pathlib import Path
import bpy
from mathutils import Matrix
from . import __version__
from .mesh_io import capture,fingerprint


def code_hash():
    root=Path(__file__).parent
    return hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted(root.glob('*.py')))).hexdigest()


def prepare_selected(run_dir,epsilon_mm=.4,obj=None,straight_walls=None,operations=None,
                     preserve_nonmanifold=False,preserve_curve_segmentation=False):
    obj=obj or bpy.context.active_object
    if obj is None:raise ValueError('Select a source mesh')
    root=Path(run_dir)
    if (root/'source.json').exists():raise FileExistsError('Use a new run directory; existing input is immutable')
    if epsilon_mm<=0:raise ValueError('epsilon_mm must be positive')
    from .straight_walls import settings
    from .operations import normalize
    wall_settings=settings(straight_walls)
    selected_operations=normalize(operations)
    snapshot=capture(obj,preserve_nonmanifold=preserve_nonmanifold);root.mkdir(parents=True,exist_ok=True)
    profile=dict(tool_version=__version__,code_hash=code_hash(),epsilon_m=epsilon_mm/1000,
                 method='A',delivery='EDITABLE_NGONS',source_name=obj.name,source_hash=snapshot['source_hash'],
                 unit_scale=snapshot['unit_scale'],sample_count=20000,coverage_status='REQUIRES_REVIEW',straight_walls=wall_settings,
                 compound_perimeter_policy='straight_strips_v1',operations=selected_operations,
                 preserve_nonmanifold=bool(preserve_nonmanifold),
                 preserve_curve_segmentation=bool(preserve_curve_segmentation))
    (root/'source.json').write_text(json.dumps(snapshot),encoding='utf-8')
    (root/'profile.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
    print('Prepared immutable source:',root)
    return profile


def apply_result(run_dir, *, include_checkpoint=True):
    root=Path(run_dir);profile=json.loads((root/'profile.json').read_text(encoding='utf-8'))
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    status=manifest.get('geometry_status')
    review=status=='FAIL' and manifest.get('review_available') is True
    if status!='PASS' and not review:raise ValueError('Worker produced neither a validated result nor an inspectable review mesh')
    if profile['code_hash']!=code_hash():raise ValueError('Tool changed since preparation; rerun with current version')
    matrix_rows=manifest.get('result_matrix_world')
    if (not isinstance(matrix_rows,list) or len(matrix_rows)!=4
            or any(not isinstance(row,list) or len(row)!=4 or any(not isinstance(value,(int,float)) or not math.isfinite(value) for value in row) for row in matrix_rows)):
        raise ValueError('Missing or invalid result transform; rerun reconstruction')
    result_matrix_world=Matrix(matrix_rows)
    src=bpy.data.objects.get(profile['source_name'])
    if src is None or fingerprint(src)!=profile['source_hash']:raise ValueError('Source changed after preparation')
    if bpy.context.scene.unit_settings.scale_length!=profile['unit_scale']:raise ValueError('Scene units changed')
    blend=root/('review_failed.blend' if review else 'result.blend')
    if hashlib.sha256(blend.read_bytes()).hexdigest()!=manifest['result_sha256']:raise ValueError('Result artifact hash mismatch')
    existing=[c for c in bpy.data.collections if c.get('cad_tool_run')==str(root.resolve())]
    if existing:return [o.name for c in existing for o in c.objects]
    object_names = [n for n in manifest['objects']
                    if include_checkpoint or review or not n.startswith('CAD_Checkpoint')]
    with bpy.data.libraries.load(str(blend),link=False) as (data_from,data_to):
        data_to.objects=[n for n in data_from.objects if n in object_names]
    if len(data_to.objects)!=(1 if review or not include_checkpoint else 2) or any(o is None for o in data_to.objects):raise ValueError('Result library incomplete')
    collection=bpy.data.collections.new(('CAD_REVIEW_' if review else 'CAD_TOOL_')+root.name);bpy.context.scene.collection.children.link(collection)
    collection['cad_tool_run']=str(root.resolve())
    collection['cad_geometry_status']=status
    if review:collection['cad_review_error']=manifest['review_reason']
    names=[]
    for obj in data_to.objects:
        collection.objects.link(obj)
        obj.matrix_world=result_matrix_world
        obj.data.materials.clear()
        for mat in src.data.materials:obj.data.materials.append(mat)
        checkpoint=bool(obj.get('cad_checkpoint'))
        obj.name=src.name+('_CAD_NEEDS_REVIEW' if review else ('_CAD_Checkpoint' if checkpoint else '_CAD_Optimized'))
        obj.hide_set(checkpoint);obj.hide_render=checkpoint
        obj['cad_source_hash']=profile['source_hash'];obj['cad_run_dir']=str(root.resolve())
        obj['cad_coverage_status']=manifest['coverage_status']
        obj['cad_geometry_status']=status
        if review:obj['cad_review_error']=manifest['review_reason']
        names.append(obj.name)
    if fingerprint(src)!=profile['source_hash']:raise RuntimeError('Source integrity changed unexpectedly')
    if review:print('NEEDS_REVIEW:',names[0],'-',manifest['review_reason'])
    return names
