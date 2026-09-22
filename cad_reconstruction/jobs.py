from __future__ import annotations

import json
import math
import os
import subprocess
import uuid
from collections import Counter
from pathlib import Path

import bpy

from ..cad_mesh_tool.api import apply_result, prepare_selected
from ..cad_mesh_tool.mesh_io import fingerprint


ACTIVE_JOB = None
COLORS = {"PASS": (0.16, 0.72, 0.24, 1.0), "REVIEW": (0.95, 0.72, 0.08, 1.0)}


def sources(context, state, retry_source=None):
    if retry_source is not None:
        objects = [retry_source]
    elif state.mode == "COLLECTION":
        if state.input_collection is None or state.output_collection is None:
            raise ValueError("Choose input and output collections")
        if state.input_collection == state.output_collection or state.output_collection in state.input_collection.children_recursive:
            raise ValueError("Output Collection must not be inside Input Collection")
        objects = list(state.input_collection.all_objects)
    else:
        objects = list(context.selected_objects)
    found = {obj.as_pointer(): obj for obj in objects if obj.type == "MESH" and not obj.get("lcw_cad_run_id")}
    if not found:
        raise ValueError("No eligible source mesh objects")
    return sorted(found.values(), key=lambda obj: (obj.name_full.casefold(), obj.as_pointer()))


def preflight(context, state, objects):
    problems = []
    scale = context.scene.unit_settings.scale_length
    if not math.isfinite(scale) or scale <= 0:
        problems.append("Scene unit scale must be positive and finite")
    for obj in objects:
        if obj.modifiers:
            problems.append(f"{obj.name}: unapplied modifiers")
        if not obj.data.vertices or not obj.data.polygons:
            problems.append(f"{obj.name}: empty mesh")
        if obj.library or obj.data.library:
            problems.append(f"{obj.name}: linked source is read-only")
        if abs(obj.matrix_world.determinant()) < 1e-12:
            problems.append(f"{obj.name}: singular transform")
    if context.mode != "OBJECT":
        problems.append("Switch to Object Mode")
    if not math.isfinite(state.epsilon_mm) or state.epsilon_mm <= 0:
        problems.append("Deviation limit must be positive and finite")
    if state.normal_override:
        if not state.normal_risk_ack:
            problems.append("Acknowledge shading risk for the manual normal limit")
        if not math.isfinite(state.normal_limit_deg) or state.normal_limit_deg <= 0:
            problems.append("Normal limit must be positive and finite")
    return problems


def analyze_risks(objects):
    notes = []
    for obj in objects:
        if not obj.data.polygons:
            continue
        edge_faces = Counter(key for face in obj.data.polygons for key in face.edge_keys)
        boundary = sum(count == 1 for count in edge_faces.values())
        nonmanifold = sum(count > 2 for count in edge_faces.values())
        degenerate = sum(face.area <= 1e-12 for face in obj.data.polygons)
        if boundary or nonmanifold or degenerate:
            notes.append(f"{obj.name}: {boundary} boundary, {nonmanifold} non-manifold, {degenerate} degenerate faces")
        if any(obj.scale[axis] < 0 for axis in range(3)):
            notes.append(f"{obj.name}: negative scale; review output orientation")
    return notes


def run_root(state):
    raw = state.run_root.strip()
    if not raw:
        raise ValueError("Choose a run folder")
    if raw.startswith("//") and not bpy.data.filepath:
        raise ValueError("Save the .blend or choose an absolute Run Folder; the addon will not auto-save")
    root = Path(bpy.path.abspath(raw)).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    if root == addon_root or addon_root in root.parents:
        raise ValueError("Run Folder must be outside the installed addon")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _child(parent, name):
    child = parent.children.get(name)
    if child is None:
        child = bpy.data.collections.new(name)
        parent.children.link(child)
    return child


def _destination(state, source, status):
    if state.mode == "SELECTED":
        return tuple(source.users_collection)
    for binding in state.bindings:
        if (binding.source == state.input_collection and binding.output_parent == state.output_collection
                and binding.branch is not None and binding.branch.name in state.output_collection.children):
            branch = binding.branch
            break
    else:
        branch = bpy.data.collections.new(f"{state.input_collection.name}_CAD")
        state.output_collection.children.link(branch)
        binding = state.bindings.add()
        binding.source = state.input_collection
        binding.output_parent = state.output_collection
        binding.branch = branch
        branch["lcw_cad_source_collection"] = state.input_collection.name
    return (_child(branch, status),)


def _result_record(state, source, run_dir, status, reason="", stage="", output=None, manifest=None):
    row = state.results.add()
    row.source = source
    row.output = output
    row.status = status
    row.geometry_status = (manifest or {}).get("geometry_status", "FAIL" if status != "PASS" else "PASS")
    row.coverage_status = (manifest or {}).get("coverage_status", "REQUIRES_REVIEW")
    row.reason = reason[:1024]
    row.stage = stage[:256]
    row.run_dir = str(run_dir)
    row.normal_limit_deg = state.normal_limit_deg if state.normal_override else 0.0
    state.active_result = len(state.results) - 1
    return row


def _import_result(state, source, run_dir, status):
    before = {o.as_pointer() for o in bpy.data.objects}
    names = apply_result(str(run_dir), include_checkpoint=False)
    imported = [bpy.data.objects.get(name) for name in names]
    if len(imported) != 1 or imported[0] is None or imported[0].as_pointer() in before:
        raise RuntimeError("CAD import did not create one new output object")
    obj = imported[0]
    temporary = tuple(obj.users_collection)
    try:
        destinations = _destination(state, source, status)
        if not destinations:
            raise ValueError("Source object has no direct collection")
        for collection in destinations:
            if obj.name not in collection.objects:
                collection.objects.link(obj)
        world = obj.matrix_world.copy()
        obj.parent = source.parent
        obj.matrix_world = world
        obj.name = f"{source.name}_CAD_{status}"
        obj.color = COLORS[status]
        obj["lcw_cad_run_id"] = run_dir.name
        obj["lcw_cad_source_name"] = source.name
        for collection in temporary:
            if collection not in destinations:
                collection.objects.unlink(obj)
                if not collection.objects and collection.get("cad_tool_run"):
                    bpy.data.collections.remove(collection)
        return obj
    except Exception:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for collection in temporary:
            if collection.name in bpy.data.collections and not collection.objects and collection.get("cad_tool_run"):
                bpy.data.collections.remove(collection)
        raise


class CADBatch:
    def __init__(self, context, objects, root):
        self.scene = context.scene
        self.objects = objects
        self.root = root
        self.index = 0
        self.process = None
        self.log = None
        self.current_dir = None
        self.source_hash = ""
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.log is not None:
            self.log.close()
            self.log = None
        self.scene.lcw_cad_reconstruction.progress = "Cancelled; completed results preserved"

    def step(self):
        state = self.scene.lcw_cad_reconstruction
        if self.cancelled:
            return False
        if self.process is None:
            if self.index >= len(self.objects):
                state.progress = f"Complete: {len(self.objects)} source object(s)"
                return False
            source = self.objects[self.index]
            self.current_dir = self.root / uuid.uuid4().hex
            state.progress = f"Preparing {self.index + 1}/{len(self.objects)}: {source.name}"
            try:
                self.source_hash = fingerprint(source)
                options = {"enabled": state.straight_walls, "normal_limit_deg": state.normal_limit_deg if state.normal_override else None}
                prepare_selected(str(self.current_dir), epsilon_mm=state.epsilon_mm, obj=source, straight_walls=options)
                worker = Path(__file__).resolve().parents[1] / "cad_mesh_tool" / "worker.py"
                command = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(worker), "--", str(self.current_dir)]
                self.log = (self.current_dir / "worker.log").open("w", encoding="utf-8")
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
            except Exception as exc:
                _result_record(state, source, self.current_dir, "FAIL", str(exc), "prepare")
                if state.mode == "COLLECTION":
                    _destination(state, source, "FAIL")
                if self.log is not None:
                    self.log.close()
                    self.log = None
                self.index += 1
            return True
        if self.process.poll() is None:
            state.progress = f"Processing {self.index + 1}/{len(self.objects)}: {self.objects[self.index].name}"
            return True
        exit_code = self.process.returncode
        self.process = None
        self.log.close()
        self.log = None
        source = self.objects[self.index]
        run_dir = self.current_dir
        manifest_path = run_dir / "manifest.json"
        failure_path = run_dir / "failure.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            failure = json.loads(failure_path.read_text(encoding="utf-8")) if failure_path.exists() else {}
        except (OSError, ValueError) as exc:
            manifest = {}
            failure = {"error": f"Unreadable worker report: {exc}"}
        status = "PASS" if exit_code == 0 and manifest.get("geometry_status") == "PASS" else "REVIEW" if manifest.get("review_available") is True else "FAIL"
        reason = manifest.get("review_reason") or failure.get("error", f"Worker exit code {exit_code}" if exit_code else "")
        stage = manifest.get("review_stage") or failure.get("stage", "worker")
        output = None
        try:
            if fingerprint(source) != self.source_hash:
                raise RuntimeError("Source fingerprint changed during worker execution")
            if status != "FAIL":
                output = _import_result(state, source, run_dir, status)
            elif state.mode == "COLLECTION":
                _destination(state, source, "FAIL")
        except Exception as exc:
            status = "FAIL"
            reason = f"Import/integrity failure: {exc}"
            stage = "import"
            if state.mode == "COLLECTION":
                _destination(state, source, "FAIL")
        _result_record(state, source, run_dir, status, reason, stage, output, manifest)
        self.index += 1
        return True
