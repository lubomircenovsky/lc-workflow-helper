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
from cad_mesh_tool.diagnostics import add_review_groups, vertex_maps
from cad_mesh_tool.operations import normalize
from cad_mesh_tool.recovery import decisions, is_geometric_conflict, recover
from cad_mesh_tool.reporting import explain
from cad_mesh_tool.nonmanifold import protection as nonmanifold_protection


def write(root,name,data):
    (root/name).write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')


def changed_from_source(source, mesh, origin):
    if len(source['vertices']) != len(mesh.vertices) or len(source['faces']) != len(mesh.polygons):
        return True
    if any(list(poly.vertices) != source['faces'][poly.index] for poly in mesh.polygons):
        return True
    return any(np.linalg.norm(np.array(vertex.co) + origin - source['vertices'][vertex.index]) > 1e-6
               for vertex in mesh.vertices)


def map_perimeters(perimeters, remap):
    mapped=[]
    for perimeter in perimeters:
        item=dict(perimeter)
        for name in ('ids','hole'):
            item[name]=[remap[i] for i in perimeter[name]]
            if any(i<0 for i in item[name]):
                raise ValueError('Straight wall cleanup removed perimeter vertex')
        item['strips']=[[remap[i] for i in face] for face in perimeter.get('strips',[])]
        if any(i<0 for face in item['strips'] for i in face):
            raise ValueError('Straight wall cleanup removed perimeter strip vertex')
        mapped.append(item)
    return mapped


def validated_candidate(source, features, operations, profile, protection=None, timings=None):
    if timings is None:timings={}
    phase=time.perf_counter()
    candidate=reconstruct(source, features, operations, protection=protection,
                          preserve_curve_segmentation=profile.get('preserve_curve_segmentation',False))
    timings['reconstruct_seconds']=time.perf_counter()-phase
    phase=time.perf_counter()
    mesh,origin=make_mesh(candidate,'CAD_CheckpointMesh')
    timings['make_mesh_seconds']=time.perf_counter()-phase
    try:
        validation=validate(source,mesh,origin,candidate['roles'],candidate['perimeters'],
                            profile['epsilon_m'],profile['sample_count'],require_reduction=False,
                            protection=protection,source_to_output=candidate['source_to_candidate'],
                            timings=timings)
        if not all(validation['checks'].values()):
            raise ValueError('Checkpoint validation failed: '+str(validation['checks']))
        return candidate,mesh,origin,validation
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise


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
    candidate=state.get('candidate') if me is state.get('checkpoint_mesh') or state.get('candidate_to_final') is not None else None
    review_groups=add_review_groups(obj,candidate,state.get('candidate_to_final'))
    blend=root/'review_failed.blend'
    bpy.data.libraries.write(str(blend),{obj},fake_user=True)
    manifest=dict(geometry_status='FAIL',coverage_status='REQUIRES_REVIEW',review_available=True,
                  review_reason=str(error),review_stage=stage,objects=[obj.name],
                  result_sha256=hashlib.sha256(blend.read_bytes()).hexdigest(),
                  result_matrix_world=result_matrix_world,
                  result_file=blend.name,tool_version=profile['tool_version'],
                  review_groups=review_groups,
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
    discover_seconds=time.time()-start
    protection=nonmanifold_protection(source,discovery['features']) if profile.get('preserve_nonmanifold') else None
    if protection is not None:
        for feature in discovery['features']:
            if feature['id'] in protection['features']:
                feature['forced_skip_reason']='Touches an unchanged source non-manifold junction'
    write(root,'plan.json',discovery)
    operations=normalize(profile.get('operations'))
    preserve_curve_segmentation=bool(profile.get('preserve_curve_segmentation',False))
    state['stage']='reconstruct'
    print('RECONSTRUCT',len(discovery['features']),operations,flush=True)
    attempts=0
    attempt_timings=[]
    def attempt(features):
        nonlocal attempts
        attempts+=1
        print('RECONSTRUCTION_ATTEMPT',attempts,flush=True)
        timing=dict(attempt=attempts,kind='full')
        started=time.perf_counter()
        try:
            return validated_candidate(source,features,operations,profile,protection,timing)
        finally:
            timing['total_seconds']=time.perf_counter()-started
            attempt_timings.append(timing)
    def dispose(result):
        bpy.data.meshes.remove(result[1])
    screening_profile=dict(profile,sample_count=min(profile['sample_count'],750))
    def screen_attempt(features):
        nonlocal attempts
        attempts+=1
        print('RECOVERY_SCREEN',attempts,flush=True)
        timing=dict(attempt=attempts,kind='screen')
        started=time.perf_counter()
        try:
            return validated_candidate(source,features,operations,screening_profile,protection,timing)
        finally:
            timing['total_seconds']=time.perf_counter()-started
            attempt_timings.append(timing)
    (candidate,mesh,origin,validation),skipped,recovery_attempts=recover(
        discovery['features'],operations,attempt,dispose,screen_attempt=screen_attempt,
        preserve_curve_segmentation=preserve_curve_segmentation)
    review_by_id={item['id']:item for item in candidate.get('review_features',[])
                  if item.get('group')=='CAD_Skipped' and item.get('id') is not None}
    for item in skipped:
        region=review_by_id.get(item['feature'],{})
        item['preserved_faces']=len(region.get('source_faces',[]))
        item['preserved_vertices']=len(region.get('source_vertices',[]))
    write(root,'candidate.json',candidate)
    write(root,'validation_checkpoint.json',validation)
    state.update(candidate=candidate,mesh=mesh,checkpoint_mesh=mesh,origin=origin,stage='checkpoint_validated')
    from cad_mesh_tool.mesh_io import ROLES
    final=mesh.copy()
    remap=list(range(len(mesh.vertices)))
    final_perimeters=map_perimeters(candidate['perimeters'],remap)
    validation_final=validation
    cleanup_report=dict(dissolved_edges=0,protected_faces=0,protected_faces_lost=0,locally_triangulated_ngons=0)
    wall_report=dict(merged_patches=[],removed_faces=0,vertex_map=remap)
    stage_fallbacks=[]
    if operations['perimeter_loops']:
        for perimeter in candidate['perimeters']:
            if perimeter.get('layout')=='direct_join':
                stage_fallbacks.append(dict(stage='Perimeter Loops',
                    reason='A support perimeter would not fit; the hole was joined directly',
                    message='This opening was connected safely without the requested support loop.'))

    def validate_stage(proposed, proposed_remap, name):
        from cad_mesh_tool.mesh_io import ROLES
        proposed_roles=[ROLES[x.value] for x in proposed.attributes['cad_role'].data]
        proposed_perimeters=map_perimeters(candidate['perimeters'],proposed_remap)
        checked=validate(source,proposed,origin,proposed_roles,proposed_perimeters,
                         profile['epsilon_m'],profile['sample_count'],require_reduction=False,
                         protection=protection,
                         source_to_output=[proposed_remap[i] if i>=0 else -1
                             for i in candidate['source_to_candidate']])
        if not all(checked['checks'].values()):
            raise ValueError(f'{name} validation failed: {checked["checks"]}')
        return checked,proposed_perimeters

    if operations['background_cleanup']:
        state['stage']='background_cleanup_unvalidated'
        proposed=None
        cleanup_started=time.perf_counter()
        try:
            proposed,_,report=cleanup(final)
            checked,perimeters=validate_stage(proposed,remap,'Background cleanup')
        except ValueError as error:
            if not is_geometric_conflict(error) and not str(error).startswith((
                    'Background cleanup validation failed','Protected faces lost','Cleanup changed vertices',
                    'Invalid triangulation in protected detail','Local n-gon repair changed topology')):
                raise
            if proposed is not None:bpy.data.meshes.remove(proposed)
            stage_fallbacks.append(dict(stage='Background Cleanup',reason=str(error),message=explain(str(error))))
        else:
            bpy.data.meshes.remove(final);final=proposed
            validation_final=checked;final_perimeters=perimeters;cleanup_report=report
            write(root,'validation_background.json',checked)
        cleanup_report['elapsed_seconds']=time.perf_counter()-cleanup_started
    if operations['straight_walls']:
        state['stage']='straight_walls_unvalidated'
        proposed=None
        walls_started=time.perf_counter()
        try:
            proposed,report=cleanup_straight_walls(final,profile['straight_walls'])
            next_remap=[report['vertex_map'][i] if i>=0 else -1 for i in remap]
            checked,perimeters=validate_stage(proposed,next_remap,'Straight wall cleanup')
        except ValueError as error:
            if not is_geometric_conflict(error) and not str(error).startswith((
                    'Straight wall cleanup','Straight wall','Straight wall cleanup validation failed')):
                raise
            if proposed is not None:bpy.data.meshes.remove(proposed)
            stage_fallbacks.append(dict(stage='Merge Straight Walls',reason=str(error),message=explain(str(error))))
        else:
            bpy.data.meshes.remove(final);final=proposed;remap=next_remap
            validation_final=checked;final_perimeters=perimeters;wall_report=report
            write(root,'validation_straight_walls.json',checked)
        wall_report['elapsed_seconds']=time.perf_counter()-walls_started
    if not changed_from_source(source,final,origin):
        raise ValueError('No selected operation produced a validated geometry change')
    state.update(mesh=final,candidate_to_final=remap,stage='final_validated')
    write(root,'straight_walls.json',wall_report)
    write(root,'perimeters_final.json',final_perimeters)
    write(root,'validation_final.json',validation_final)
    write(root,'cleanup.json',cleanup_report)
    write(root,'vertex_map.json',vertex_maps(candidate,remap))
    scale=profile['unit_scale'];objects=[]
    result_matrix_world=Matrix.Translation(origin/scale)@Matrix.Scale(1/scale,4)
    review_groups=[]
    for me,name,checkpoint in [(mesh,'CAD_Checkpoint',True),(final,'CAD_Optimized',False)]:
        obj=bpy.data.objects.new(name,me);obj.matrix_world=result_matrix_world
        if not checkpoint:
            review_groups=add_review_groups(obj,candidate,remap)
        obj['cad_checkpoint']=checkpoint;objects.append(obj)
    bpy.data.libraries.write(str(root/'result.blend'),set(objects),fake_user=True)
    partial=bool(protection or skipped or stage_fallbacks)
    skipped_ids={item['feature'] for item in skipped}
    rebuilt_count=sum(decisions([feature],operations,
                                preserve_curve_segmentation=preserve_curve_segmentation)[0]['decision']=='REBUILD'
                      and feature['id'] not in skipped_ids for feature in discovery['features'])
    accepted_reductions=[feature for feature in discovery['features']
                         if feature['id'] not in skipped_ids and
                         decisions([feature],operations,
                                   preserve_curve_segmentation=preserve_curve_segmentation)[0]['decision']=='REBUILD'
                         and feature['segments']<feature['segments_before']]
    circular_skips=[item for item in skipped if next(
        (feature['category'] for feature in discovery['features'] if feature['id']==item['feature']),None)=='circular_hole']
    created_loops=sum(p.get('kind')=='circular' and p.get('layout')!='direct_join'
                      for p in candidate['perimeters'])
    direct_joins=sum(p.get('kind')=='circular' and p.get('layout')=='direct_join'
                     for p in candidate['perimeters'])
    operation_results=dict(
        circular_holes_detected=sum(feature['category']=='circular_hole' for feature in discovery['features']),
        perimeter_loops_created=created_loops,
        perimeter_direct_joins=direct_joins,
        perimeter_skipped=len(circular_skips) if operations['perimeter_loops'] else 0,
        perimeter_not_attempted=(sum('Recovery attempt limit' in item['reason'] for item in circular_skips)
                                 if operations['perimeter_loops'] else 0),
        segments_reduced=sum(feature['segments_before']-feature['segments'] for feature in accepted_reductions),
        curves_reduced=len(accepted_reductions),
        planar_edges_removed=cleanup_report['dissolved_edges'],
        ngons_before=sum(len(face)>4 for face in source['faces']),
        ngons_after=sum(len(face.vertices)>4 for face in final.polygons),
        locally_triangulated_ngons=cleanup_report.get('locally_triangulated_ngons',0))
    manifest=dict(geometry_status='PASS',coverage_status='REQUIRES_REVIEW',partial=partial,
                  preserved_source_nonmanifold=protection,
                  operations=operations,skipped_features=skipped,stage_fallbacks=stage_fallbacks,
                  preserve_curve_segmentation=preserve_curve_segmentation,
                  operation_results=operation_results,
                  recovery_attempts=recovery_attempts,objects=[o.name for o in objects],
                  result_sha256=hashlib.sha256((root/'result.blend').read_bytes()).hexdigest(),
                  before=validation['before'],checkpoint=validation['after'],final=validation_final['after'],
                  tool_version=profile['tool_version'],cylinders_rebuilt=rebuilt_count,perimeters=len(candidate['perimeters']),
                  feature_categories=dict(Counter(c['category'] for c in discovery['features'])),
                  source_faces_not_claimed_by_cylinders=len(discovery['unclaimed_faces']),
                  transition_patches=len(candidate.get('transitions',[])),
                  locally_triangulated_ngons=cleanup_report.get('locally_triangulated_ngons',0),
                  protected_faces_lost=cleanup_report['protected_faces_lost'],elapsed_seconds=time.time()-start,
                  straight_wall_patches=len(wall_report['merged_patches']),straight_wall_faces_removed=wall_report['removed_faces'],
                  sparse_perimeters=sum(p.get('layout')=='straight_strips' for p in candidate['perimeters']),
                  direct_join_perimeters=sum(p.get('layout')=='direct_join' for p in candidate['perimeters']),
                  compound_perimeters_dense=[i for i,p in enumerate(candidate['perimeters']) if p.get('kind')=='compound' and p.get('layout')!='straight_strips'],
                  review_groups=review_groups,
                  timings=dict(discover_seconds=discover_seconds,attempts=attempt_timings,
                               background_cleanup_seconds=cleanup_report.get('elapsed_seconds',0),
                               straight_walls_seconds=wall_report.get('elapsed_seconds',0)),
                  source_hash=profile['source_hash'],code_hash=profile['code_hash'])
    manifest['result_matrix_world']=[list(row) for row in result_matrix_world]
    manifest['normal_limit_override_deg']=profile['straight_walls'].get('normal_limit_deg')
    manifest['summary']=(f"Original non-manifold junction preserved across "
                         f"{len(protection['faces'])} source faces; {len(skipped)} feature(s) skipped. "
                         'Inspect CAD_Skipped and REPORT.md.' if protection is not None else
                         f"Validated partial result: {len(skipped)} feature(s) preserved, "
                         f"{len(stage_fallbacks)} step warning(s). "
                         +('Inspect CAD_Skipped and REPORT.md.' if skipped else 'Inspect REPORT.md.')
                         if partial else 'Selected CAD operations completed; inspect the output visually.')
    if manifest['normal_limit_override_deg'] is not None:
        manifest['normal_limit_warning']='Manual normal limit may accept visible shading changes' if manifest['normal_limit_override_deg']>0.05 else ''
    write(root,'manifest.json',manifest)
    lines=['# CAD mesh reconstruction', '',
           'Result: PARTIAL / REVIEW.' if partial else 'Result: PASS.',
           'The output passed geometry validation. Visual review is still required.', '',
           f"Selected operations: {', '.join(name for name,enabled in operations.items() if enabled)}.",
           f"Preserve curve segmentation: {preserve_curve_segmentation}.",
           f"Circular holes detected: {operation_results['circular_holes_detected']}.",
           f"Perimeter loops: {created_loops} created, {direct_joins} direct joins without a loop, "
           f"{operation_results['perimeter_skipped']} skipped ({operation_results['perimeter_not_attempted']} not attempted).",
           f"Curve reduction: {operation_results['curves_reduced']} features, "
           f"{operation_results['segments_reduced']} segments removed.",
           f"Planar cleanup: {operation_results['planar_edges_removed']} internal edges removed; "
           f"ngons {operation_results['ngons_before']} -> {operation_results['ngons_after']}.",
           f"Triangles: {manifest['before']['t']} -> {manifest['final']['t']}.",
           f"Validated reconstruction attempts: {recovery_attempts}.", '']
    if protection is not None:
        lines.append(f"- The original {len(protection['edges'])} non-manifold edge(s) "
                     f"and their {len(protection['faces'])}-face dependent patch were preserved "
                     'exactly. This is not a repaired manifold mesh. Review CAD_Skipped.')
    for item in skipped:
        lines.append(f"- Feature {item['feature']} was preserved ({item['preserved_faces']} source faces, "
                     f"{item['preserved_vertices']} vertices): {explain(item['reason'])} "
                     'Review its CAD_Skipped vertex group.')
    for item in stage_fallbacks:
        lines.append(f"- {item['stage']} was not applied: {item['message']} The last validated mesh was kept.")
    if not partial:
        lines.append('All selected operations completed without a local recovery fallback.')
    lines.extend(['', 'Details: candidate.json, validation_checkpoint.json, validation_final.json, '
                  'vertex_map.json and worker.log contain exact technical evidence.'])
    (root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('WORKER_COMPLETE',manifest['summary'],
          f"triangles={manifest['before']['t']}->{manifest['final']['t']}",flush=True)


if __name__=='__main__':
    run=Path(sys.argv[sys.argv.index('--')+1])
    review_state={}
    try:main(run,review_state)
    except Exception as error:
        detail=dict(status='FAIL',error=str(error),stage=review_state.get('stage','startup'),
                    message=explain(str(error)),traceback=traceback.format_exc(),
                    review_available=False,diagnostic_output_created=False)
        write(run,'failure.json',detail)
        (run/'REPORT.md').write_text('# CAD mesh reconstruction\n\nResult: FAIL. No validated output was created.\n\n'
                                     +detail['message']+'\n\nTechnical details are in failure.json and worker.log.\n',encoding='utf-8')
        raise
