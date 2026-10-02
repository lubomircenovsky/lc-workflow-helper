"""Cancelable external analysis; live bpy access stays on the main thread."""
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import bpy
from . import jobs
from ..cad_mesh_tool.api import code_hash
from ..cad_mesh_tool.mesh_io import capture, fingerprint
from ..cad_mesh_tool.operations import DEFAULTS

ACTIVE_ANALYSIS = None


@bpy.app.handlers.persistent
def cancel_active(_unused=None):
    global ACTIVE_ANALYSIS
    if ACTIVE_ANALYSIS is not None:
        ACTIVE_ANALYSIS.cancel()
        ACTIVE_ANALYSIS = None


class CADAnalysis:
    def __init__(self, context, objects, root):
        self.scene = context.scene
        self.objects = tuple(objects)
        self.root = root
        state = self.scene.lcw_cad_reconstruction
        self.max_workers = min(state.concurrent_workers, 4)
        self.profile = dict(epsilon_m=state.epsilon_mm/1000, sample_count=750,
                            operations={name:bool(getattr(state,name)) for name in DEFAULTS},
                            preserve_curve_segmentation=state.preserve_curve_segmentation,
                            perimeter_clearance_mm=state.perimeter_clearance_mm,
                            hole_epsilon_mm=state.hole_epsilon_mm,hole_detail_factor=state.hole_detail_factor,
                            separate_solids=state.separate_solids,code_hash=code_hash())
        self.next_index = 0
        self.running = {}
        self.completed = 0
        self.cancelled = False
        self.rows = []
        for obj in objects:
            row=state.analysis_lines.add()
            row.source=obj
            row.message=f'{obj.name}: Queued for detailed analysis.'
            row.severity='NOTE'
            self.rows.append(row)

    def _record(self, index, result):
        row=self.rows[index]
        name=self.objects[index].name
        if 'error' in result:
            row.message=f"{name}: {result['error']}"
            row.severity='BLOCKER'
        else:
            row.severity='BLOCKER' if result['blocked'] else 'NOTE'
            topology=result['topology']
            holes=result.get('holes',[])
            targets=sorted({f['target'] for f in holes})
            prefix=f"{result['solids']} solid(s); {topology['nonmanifold']} non-manifold edges. "
            if result.get('shared_interface_faces'):
                prefix+=f"{len(result['shared_interface_faces'])} measured shared interface face(s); opposite caps in separate outputs. "
            repaired=result.get('source_repair',{}).get('removed_zero_area_faces',[])
            if repaired:
                prefix+=f"{len(repaired)} collinear zero-area face(s) can be sewn without moving vertices. "
            if result['guarded']:prefix+='Automatic guarded strategy. '
            if holes:prefix+=f"{len(holes)} holes; target segments {', '.join(map(str,targets))}. "
            categories=result.get('categories',{})
            if categories:
                prefix+=f"{categories.get('concave_arc',0)+categories.get('convex_arc',0)} bends; {categories.get('outer_cylinder',0)} outer cylinders. "
            row.message=f"{name}: {prefix}{result['summary']}"
            row.recommendation=json.dumps(result['recommendation']) if result.get('recommendation') else ''
            row.source_hash=result['source_hash']
        row.technical=json.dumps(result)
        self.completed+=1

    def _start(self, index):
        obj=self.objects[index]
        row=self.rows[index]
        # Topology is analyzed in the worker, including guarded eligibility.
        issues=[issue for issue in jobs.preflight_object(obj, True)
                if 'closed manifold mesh' not in issue]
        if issues:
            self._record(index,{'error':'; '.join(issues)})
            return
        root=self.root/uuid.uuid4().hex
        log=None
        try:
            snapshot=capture(obj,check_topology=False)
            root.mkdir(parents=True)
            (root/'source.json').write_text(json.dumps(snapshot),encoding='utf-8')
            profile=dict(self.profile,method='CAD_ANALYSIS',delivery='CAD_INPUT_ANALYSIS',source_hash=snapshot['source_hash'])
            (root/'profile.json').write_text(json.dumps(profile),encoding='utf-8')
            row.run_dir=str(root)
            row.message=f'{obj.name}: Checking source geometry and operation profiles...'
            worker=Path(__file__).resolve().parents[1]/'cad_mesh_tool/analysis_worker.py'
            log=(root/'worker.log').open('w',encoding='utf-8')
            process=subprocess.Popen([bpy.app.binary_path,'--background','--factory-startup','--python-exit-code','1',
                                      '--python',str(worker),'--',str(root)],stdout=log,stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.running[index]={'process':process,'log':log,'root':root,'hash':snapshot['source_hash']}
        except Exception as error:
            if log is not None:log.close()
            self._record(index,{'error':str(error)})

    def _finish(self, index):
        job=self.running.pop(index)
        job['log'].close()
        try:
            if fingerprint(self.objects[index])!=job['hash']:
                raise ValueError('Source changed during analysis; analyze again before using recommendations')
            if job['process'].returncode:
                path=job['root']/'failure.json'
                raise ValueError(json.loads(path.read_text(encoding='utf-8'))['error'] if path.exists() else 'Analysis worker failed; inspect worker.log')
            result=json.loads((job['root']/'analysis.json').read_text(encoding='utf-8'))
        except Exception as error:
            result={'error':str(error)}
        self._record(index,result)

    def step(self):
        if self.cancelled:return False
        for index,job in sorted(self.running.items()):
            if job['process'].poll() is not None:
                self._finish(index)
                break
        if self.next_index<len(self.objects) and len(self.running)<self.max_workers:
            index=self.next_index
            self.next_index+=1
            self._start(index)
        state=self.scene.lcw_cad_reconstruction
        state.progress=f'Analyze: {self.completed}/{len(self.objects)} complete | {len(self.running)} running'
        if self.completed==len(self.objects):
            state.analysis_ready=True
            state.analysis_meshes=len(self.objects)
            state.analysis_blockers=sum(row.severity=='BLOCKER' for row in self.rows)
            state.analysis_notes=len(self.rows)-state.analysis_blockers
            label='mesh' if len(self.objects)==1 else 'meshes'
            state.analysis_summary=f'{len(self.objects)} {label} | {state.analysis_blockers} blocked | {state.analysis_notes} notes'
            state.progress='Detailed analysis complete'
            return False
        return True

    def cancel(self):
        self.cancelled=True
        deadline=time.monotonic()+2.
        for job in self.running.values():
            if job['process'].poll() is None:job['process'].terminate()
        for job in self.running.values():
            try:job['process'].wait(timeout=max(0.,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                job['process'].kill()
                job['process'].wait()
            job['log'].close()
        self.running.clear()
        for row in self.rows:
            if not row.technical:row.message=f'{row.source.name if row.source else "Mesh"}: Analysis cancelled.'
        state=self.scene.lcw_cad_reconstruction
        state.analysis_running=False
        state.progress='Analysis cancelled; completed notes kept'
