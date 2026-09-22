"""Run with Blender --background --factory-startup --python-exit-code 1 --python worker.py -- RUN_DIR."""
import sys,json,time,hashlib,traceback
from collections import Counter
from pathlib import Path
root_package=Path(__file__).resolve().parent
sys.path.insert(0,str(root_package.parent))
import bpy,numpy as np
from mathutils import Matrix,Vector
from cad_mesh_tool.api import code_hash
from cad_mesh_tool.detect import discover
from cad_mesh_tool.rebuild import reconstruct
from cad_mesh_tool.mesh_io import make_mesh,cleanup
from cad_mesh_tool.validate import validate
from cad_mesh_tool.straight_walls import cleanup_straight_walls


def write(root,name,data):
    (root/name).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')


def save_failed_review(root,error,state):
    """Preserve a failed candidate for inspection without certifying it as PASS."""
    from cad_mesh_tool import __version__
    profile_path=root/'profile.json'
    if not profile_path.is_file():return False
    profile=json.loads(profile_path.read_text(encoding='utf-8'))
    if profile.get('code_hash')!=code_hash():return False
    me=getattr(error,'review_mesh',None) or state.get('mesh')
    origin=state.get('origin')
    if me is None or origin is None:return False
    stage=getattr(error,'review_stage',None) or state.get('stage','unknown')
    obj=bpy.data.objects.new('CAD_NEEDS_REVIEW',me)
    scale=profile['unit_scale']
    obj.matrix_world=Matrix.Translation(Vector(origin)/scale)@Matrix.Scale(1/scale,4)
    result_matrix_world=[list(row) for row in obj.matrix_world]
    obj['cad_checkpoint']=False
    obj['cad_geometry_status']='FAIL'
    obj['cad_review_stage']=stage
    obj['cad_review_error']=str(error)
    blend=root/'review_failed.blend'
    bpy.data.libraries.write(str(blend),{obj},fake_user=True)
    manifest=dict(geometry_status='FAIL',coverage_status='REQUIRES_REVIEW',review_available=True,
                  review_reason=str(error),review_stage=stage,objects=[obj.name],
                  result_sha256=hashlib.sha256(blend.read_bytes()).hexdigest(),
                  result_matrix_world=result_matrix_world,
                  result_file=blend.name,tool_version=profile['tool_version'],
                  source_hash=profile['source_hash'],code_hash=profile['code_hash'])
    write(root,'manifest.json',manifest)
    print('WORKER_FAILED_REVIEW_AVAILABLE',profile['source_name'],str(error),flush=True)
    return True


def main(root,state=None):
    root=Path(root);start=time.time()
    if state is None:state={}
    source=json.loads((root/'source.json').read_text(encoding='utf-8'))
    profile=json.loads((root/'profile.json').read_text(encoding='utf-8'))
    if profile['code_hash']!=code_hash():raise ValueError('Implementation changed since prepare_selected')
    if (root/'manifest.json').exists():raise FileExistsError('Completed run already exists')
    state['stage']='discover'
    print('DISCOVER',flush=True)
    discovery=discover(source['vertices'],source['faces'],profile['epsilon_m'])
    write(root,'plan.json',discovery)
    state['stage']='reconstruct'
    print('RECONSTRUCT',len(discovery['features']),flush=True)
    candidate=reconstruct(source,discovery['features']);write(root,'candidate.json',candidate)
    mesh,origin=make_mesh(candidate,'CAD_CheckpointMesh')
    state.update(mesh=mesh,origin=origin,stage='checkpoint_unvalidated')
    validation=validate(source,mesh,origin,candidate['roles'],candidate['perimeters'],profile['epsilon_m'],profile['sample_count'])
    write(root,'validation_checkpoint.json',validation)
    if not all(validation['checks'].values()):raise ValueError('Checkpoint validation failed: '+str(validation['checks']))
    state['stage']='checkpoint_validated'
    final,roles,cleanup_report=cleanup(mesh)
    state.update(mesh=final,stage='background_cleanup_unvalidated')
    wall_mesh,wall_report=cleanup_straight_walls(final,profile['straight_walls'])
    bpy.data.meshes.remove(final);final=wall_mesh
    state.update(mesh=final,stage='straight_walls_unvalidated')
    from cad_mesh_tool.mesh_io import ROLES
    roles=[ROLES[x.value] for x in final.attributes['cad_role'].data]
    remap=wall_report['vertex_map']
    final_perimeters=[dict(p,ids=[remap[i] for i in p['ids']],hole=[remap[i] for i in p['hole']],
                           strips=[[remap[i] for i in f] for f in p.get('strips',[])]) for p in candidate['perimeters']]
    if any(i<0 for p in final_perimeters for i in p['ids']+p['hole']):raise ValueError('Straight wall cleanup removed perimeter vertex')
    write(root,'straight_walls.json',wall_report)
    write(root,'perimeters_final.json',final_perimeters)
    validation_final=validate(source,final,origin,roles,final_perimeters,profile['epsilon_m'],profile['sample_count'])
    write(root,'validation_final.json',validation_final);write(root,'cleanup.json',cleanup_report)
    if not all(validation_final['checks'].values()):raise ValueError('Editable validation failed: '+str(validation_final['checks']))
    state['stage']='final_validated'
    scale=profile['unit_scale'];objects=[]
    result_matrix_world=Matrix.Translation(origin/scale)@Matrix.Scale(1/scale,4)
    for me,name,checkpoint in [(mesh,'CAD_Checkpoint',True),(final,'CAD_Optimized',False)]:
        obj=bpy.data.objects.new(name,me);obj.matrix_world=result_matrix_world
        obj['cad_checkpoint']=checkpoint;objects.append(obj)
    bpy.data.libraries.write(str(root/'result.blend'),set(objects),fake_user=True)
    manifest=dict(geometry_status='PASS',coverage_status='REQUIRES_REVIEW',objects=[o.name for o in objects],
                  result_sha256=hashlib.sha256((root/'result.blend').read_bytes()).hexdigest(),
                  before=validation['before'],checkpoint=validation['after'],final=validation_final['after'],
                  tool_version=profile['tool_version'],cylinders_rebuilt=len(discovery['features']),perimeters=len(candidate['perimeters']),
                  feature_categories=dict(Counter(c['category'] for c in discovery['features'])),
                  source_faces_not_claimed_by_cylinders=len(discovery['unclaimed_faces']),
                  transition_patches=len(candidate.get('transitions',[])),
                  locally_triangulated_ngons=cleanup_report.get('locally_triangulated_ngons',0),
                  protected_faces_lost=cleanup_report['protected_faces_lost'],elapsed_seconds=time.time()-start,
                  straight_wall_patches=len(wall_report['merged_patches']),straight_wall_faces_removed=wall_report['removed_faces'],
                  sparse_perimeters=sum(p.get('layout')=='straight_strips' for p in candidate['perimeters']),
                  compound_perimeters_dense=[i for i,p in enumerate(candidate['perimeters']) if p.get('kind')=='compound' and p.get('layout')!='straight_strips'],
                  source_hash=profile['source_hash'],code_hash=profile['code_hash'])
    manifest['result_matrix_world']=[list(row) for row in result_matrix_world]
    manifest['normal_limit_override_deg']=profile['straight_walls'].get('normal_limit_deg')
    if manifest['normal_limit_override_deg'] is not None:
        manifest['normal_limit_warning']='Manual normal limit may accept visible shading changes' if manifest['normal_limit_override_deg']>0.05 else ''
    write(root,'manifest.json',manifest)
    (root/'REPORT.md').write_text(
        '# CAD mesh tool result\n\nGeometry: PASS. Coverage: REQUIRES_REVIEW.\n\n'
        f"Triangles: {manifest['before']['t']} → {manifest['checkpoint']['t']} → {manifest['final']['t']}.\n\n"
        f"Rebuilt cylinders: {manifest['cylinders_rebuilt']}; perimeters: {manifest['perimeters']}; protected faces lost: {manifest['protected_faces_lost']}.\n\n"
        f"Local background n-gon repairs: {manifest['locally_triangulated_ngons']}. Transition patches: {manifest['transition_patches']}.\n\n"
        f"Straight wall patches merged: {manifest['straight_wall_patches']}; wall faces removed: {manifest['straight_wall_faces_removed']}. See straight_walls.json for parameters and skipped cases.\n\n"
        f"Sparse compound perimeters: {manifest['sparse_perimeters']}; compound perimeters retaining dense layout: {manifest['compound_perimeters_dense']}. See candidate.json.\n\n"
        f"Manual normal limit (degrees): {manifest['normal_limit_override_deg']}; {manifest.get('normal_limit_warning','')}\n\n"
        f"Source faces not owned by detected cylinders: {manifest['source_faces_not_claimed_by_cylinders']}. This includes flat background, caps and other surfaces; it is not a count of missed holes or failed faces.\n\n"
        'The tool checks supported analytic reconstructions. Independent visual/coverage review remains required. plan.json inventories source face ownership; candidate.json records rebuilt planes, transitions and protected faces. This is not a certified arbitrary-CAD optimizer.\n',encoding='utf-8')
    print('WORKER_COMPLETE',json.dumps(manifest),flush=True)


if __name__=='__main__':
    run=Path(sys.argv[sys.argv.index('--')+1])
    review_state={}
    try:main(run,review_state)
    except Exception as error:
        detail=dict(status='FAIL',error=str(error),stage=review_state.get('stage','startup'),
                    traceback=traceback.format_exc())
        try:detail['review_available']=save_failed_review(run,error,review_state)
        except Exception as review_error:detail['review_available']=False;detail['review_artifact_error']=str(review_error)
        write(run,'failure.json',detail)
        raise
