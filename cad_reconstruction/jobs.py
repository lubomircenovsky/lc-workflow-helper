from __future__ import annotations

import json
import math
import os
import subprocess
import time
import uuid
from collections import Counter
from pathlib import Path

import bpy

from ..cad_mesh_tool.api import apply_result, prepare_selected
from ..cad_mesh_tool.mesh_io import fingerprint, topology_problem
from ..cad_mesh_tool.operations import DEFAULTS, normalize


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
    found = {obj.as_pointer(): obj for obj in objects if obj.type == "MESH"}
    if not found:
        raise ValueError("No eligible source mesh objects")
    return sorted(found.values(), key=lambda obj: (obj.name_full.casefold(), obj.as_pointer()))


def preflight_globals(context, state):
    problems = []
    try:
        normalize({name: bool(getattr(state, name)) for name in DEFAULTS})
    except ValueError as exc:
        problems.append(str(exc))
    scale = context.scene.unit_settings.scale_length
    if not math.isfinite(scale) or scale <= 0:
        problems.append("Scene unit scale must be positive and finite")
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


def preflight_object(obj, preserve_nonmanifold=False):
    problems = []
    if obj.modifiers:
        problems.append(f"{obj.name}: unapplied modifiers")
    if not obj.data.vertices or not obj.data.polygons:
        problems.append(f"{obj.name}: empty mesh")
    else:
        try:
            if topology_issue := topology_problem(obj, preserve_nonmanifold=preserve_nonmanifold):
                problems.append(topology_issue)
        except Exception as exc:
            problems.append(f"{obj.name}: topology check failed ({exc})")
    if obj.library or obj.data.library:
        problems.append(f"{obj.name}: linked source is read-only")
    if abs(obj.matrix_world.determinant()) < 1e-12:
        problems.append(f"{obj.name}: singular transform")
    return problems


def preflight(context, state, objects, preserve_nonmanifold=False):
    problems = preflight_globals(context, state)
    for obj in objects:
        problems.extend(preflight_object(obj, preserve_nonmanifold))
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


def run_root(state, create=True):
    raw = state.run_root.strip()
    if not raw:
        raise ValueError("Choose a run folder")
    if raw.startswith("//") and not bpy.data.filepath:
        raise ValueError("Save the .blend or choose an absolute Run Folder; the addon will not auto-save")
    root = Path(bpy.path.abspath(raw)).resolve()
    addon_root = Path(__file__).resolve().parents[1]
    if root == addon_root or addon_root in root.parents:
        raise ValueError("Run Folder must be outside the installed addon")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _child(parent, name):
    child = parent.children.get(name)
    if child is None:
        child = bpy.data.collections.new(name)
        parent.children.link(child)
    return child


def _destination(state, source, status, routing=None):
    mode = routing["mode"] if routing is not None else state.mode
    input_collection = routing["input"] if routing is not None else state.input_collection
    output_collection = routing["output"] if routing is not None else state.output_collection
    if mode == "SELECTED":
        return tuple(source.users_collection)
    for binding in state.bindings:
        if (binding.source == input_collection and binding.output_parent == output_collection
                and binding.branch is not None and binding.branch.name in output_collection.children):
            branch = binding.branch
            break
    else:
        branch = bpy.data.collections.new(f"{input_collection.name}_CAD")
        output_collection.children.link(branch)
        binding = state.bindings.add()
        binding.source = input_collection
        binding.output_parent = output_collection
        binding.branch = branch
        branch["lcw_cad_source_collection"] = input_collection.name
    return (_child(branch, status),)


def _result_record(state, source, run_dir, status, reason="", stage="", output=None,
                   manifest=None, preserve_nonmanifold=False, row_index=None,
                   normal_limit_deg=None, elapsed_seconds=0.0, technical_reason=""):
    row = state.results[row_index] if row_index is not None else state.results.add()
    row.source = source
    row.output = output
    row.status = status
    row.geometry_status = (manifest or {}).get("geometry_status", "FAIL" if status != "PASS" else "PASS")
    row.coverage_status = (manifest or {}).get("coverage_status", "REQUIRES_REVIEW")
    row.partial = bool((manifest or {}).get("partial", False))
    row.preserve_nonmanifold = bool(preserve_nonmanifold)
    row.summary = (manifest or {}).get("summary", "")[:1024]
    operation_results = (manifest or {}).get("operation_results", {})
    row.perimeter_summary = (
        f"Perimeters: {operation_results['perimeter_loops_created']} loops, "
        f"{operation_results['perimeter_direct_joins']} direct joins, "
        f"{operation_results['perimeter_skipped']} skipped"
        if "perimeter_loops_created" in operation_results else ""
    )
    row.planar_summary = (
        f"Planar cleanup: {operation_results['planar_edges_removed']} edges removed; "
        f"ngons {operation_results['ngons_before']} -> {operation_results['ngons_after']}"
        if "planar_edges_removed" in operation_results else ""
    )
    metrics = []
    for key, label in (("curves_reduced", "curves reduced"),
                       ("perimeter_loops_created", "loops made"),
                       ("planar_edges_removed", "flat edges removed")):
        count = operation_results.get(key, 0)
        if count:
            metrics.append(f"{count:,} {label}")
    row.metrics_summary = " | ".join(metrics)
    row.reason = reason[:1024]
    row.technical_reason = technical_reason[:1024]
    row.stage = stage[:256]
    row.run_dir = str(run_dir)
    row.normal_limit_deg = (state.normal_limit_deg if state.normal_override else 0.0
                            ) if normal_limit_deg is None else normal_limit_deg
    row.elapsed_seconds = elapsed_seconds
    state.active_result = len(state.results) - 1 if row_index is None else row_index
    return row


def _import_result(state, source, run_dir, status, routing=None):
    before = {o.as_pointer() for o in bpy.data.objects}
    names = apply_result(str(run_dir), include_checkpoint=False)
    imported = [bpy.data.objects.get(name) for name in names]
    if len(imported) != 1 or imported[0] is None or imported[0].as_pointer() in before:
        raise RuntimeError("CAD import did not create one new output object")
    obj = imported[0]
    temporary = tuple(obj.users_collection)
    try:
        destinations = _destination(state, source, status, routing)
        if not destinations:
            raise ValueError("Source object has no direct collection")
        for collection in destinations:
            if obj.name not in collection.objects:
                collection.objects.link(obj)
        world = obj.matrix_world.copy()
        obj.parent = source.parent
        obj.matrix_world = world
        obj.name = f"{source.name}_CAD_{status}"
        from . import status_overlay

        obj.color = status_overlay.base_color(source)
        obj["lcw_cad_run_id"] = run_dir.name
        obj["lcw_cad_status"] = status
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
    def __init__(self, context, objects, root, preserve_nonmanifold=False,
                 object_issues=None):
        self.scene = context.scene
        self.objects = tuple(objects)
        self.object_issues = tuple(tuple(issues) for issues in (
            object_issues if object_issues is not None else (() for _ in objects)))
        self.root = root
        self.preserve_nonmanifold = preserve_nonmanifold
        state = self.scene.lcw_cad_reconstruction
        self.max_workers = min(max(int(state.concurrent_workers), 1), 16)
        self.epsilon_mm = state.epsilon_mm
        self.options = {name: bool(getattr(state, name)) for name in DEFAULTS}
        self.preserve_curve_segmentation = bool(state.preserve_curve_segmentation)
        self.straight_walls = {"enabled": state.straight_walls,
                               "normal_limit_deg": state.normal_limit_deg if state.normal_override else None}
        self.normal_limit_deg = state.normal_limit_deg if state.normal_override else 0.0
        self.routing = {"mode": state.mode, "input": state.input_collection,
                        "output": state.output_collection}
        self.next_index = 0
        self.completed = 0
        self.running = {}
        self.cancelled = False
        self.row_offset = len(state.results)
        for source in self.objects:
            row = state.results.add()
            row.source = source
            row.status = "PENDING"
            row.stage = "Queued"

    def _row(self, index):
        return self.scene.lcw_cad_reconstruction.results[self.row_offset + index]

    def _read_worker_progress(self, job):
        path = job["run_dir"] / "worker.log"
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                stream.seek(job["log_position"])
                lines = stream.readlines()
                job["log_position"] = stream.tell()
        except OSError:
            return
        for line in lines:
            if line.startswith("DISCOVER"):
                job["phase"] = "Detecting features"
            elif line.startswith("RECOVERY_SCREEN"):
                job["phase"] = f"Testing safe regions ({line.split()[-1].strip()})"
            elif line.startswith("RECONSTRUCTION_ATTEMPT"):
                job["phase"] = f"Validating attempt ({line.split()[-1].strip()})"
            elif line.startswith("VALIDATE"):
                job["phase"] = "Checking geometry"
        self._row(job["index"]).stage = job["phase"]

    def _progress(self):
        queued = len(self.objects) - self.next_index
        phases = ", ".join(f"{self.objects[i].name}: {job['phase']}"
                           for i, job in sorted(self.running.items()))
        self.scene.lcw_cad_reconstruction.progress = (
            f"Queued {queued} | Running {len(self.running)} | Done {self.completed}"
            + (f" | {phases}" if phases else ""))

    def _start_worker(self, index):
        state = self.scene.lcw_cad_reconstruction
        source = self.objects[index]
        run_dir = self.root / uuid.uuid4().hex
        row = self._row(index)
        row.run_dir = str(run_dir)
        row.status = "RUNNING"
        row.stage = "Preparing input"
        started = time.perf_counter()
        log = None
        try:
            if self.object_issues[index]:
                raise ValueError("; ".join(self.object_issues[index]))
            source_hash = fingerprint(source)
            prepare_selected(str(run_dir), epsilon_mm=self.epsilon_mm, obj=source,
                             straight_walls=self.straight_walls, operations=self.options,
                             preserve_nonmanifold=self.preserve_nonmanifold,
                             preserve_curve_segmentation=self.preserve_curve_segmentation)
            worker = Path(__file__).resolve().parents[1] / "cad_mesh_tool" / "worker.py"
            command = [bpy.app.binary_path, "--background", "--factory-startup",
                       "--python-exit-code", "1", "--python", str(worker), "--", str(run_dir)]
            log = (run_dir / "worker.log").open("w", encoding="utf-8")
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=flags)
            self.running[index] = {"index": index, "run_dir": run_dir, "process": process,
                                   "log": log, "log_position": 0, "phase": "Starting",
                                   "source_hash": source_hash, "started": started}
            row.stage = "Starting"
        except Exception as exc:
            if log is not None:
                log.close()
            stage = "preflight" if self.object_issues[index] else "prepare"
            _result_record(state, source, run_dir, "FAIL", str(exc), stage,
                           preserve_nonmanifold=self.preserve_nonmanifold,
                           row_index=self.row_offset + index,
                           normal_limit_deg=self.normal_limit_deg,
                           elapsed_seconds=time.perf_counter() - started)
            if self.routing["mode"] == "COLLECTION":
                _destination(state, source, "FAIL", self.routing)
            self.completed += 1

    def _finish_worker(self, index):
        state = self.scene.lcw_cad_reconstruction
        job = self.running.pop(index)
        self._read_worker_progress(job)
        exit_code = job["process"].returncode
        job["log"].close()
        source = self.objects[index]
        run_dir = job["run_dir"]
        manifest_path = run_dir / "manifest.json"
        failure_path = run_dir / "failure.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
            failure = json.loads(failure_path.read_text(encoding="utf-8")) if failure_path.exists() else {}
        except (OSError, ValueError) as exc:
            manifest = {}
            failure = {"error": f"Unreadable worker report: {exc}"}
        status = ("REVIEW" if exit_code == 0 and manifest.get("geometry_status") == "PASS"
                  and manifest.get("partial") else "PASS" if exit_code == 0
                  and manifest.get("geometry_status") == "PASS" else "FAIL")
        reason = (manifest.get("summary") or failure.get("message") or failure.get(
            "error", f"Worker exit code {exit_code}" if exit_code else ""))
        stage = manifest.get("review_stage") or failure.get("stage", "worker")
        output = None
        try:
            if fingerprint(source) != job["source_hash"]:
                raise RuntimeError("Source fingerprint changed during worker execution")
            if status != "FAIL":
                output = _import_result(state, source, run_dir, status, self.routing)
            elif self.routing["mode"] == "COLLECTION":
                _destination(state, source, "FAIL", self.routing)
        except Exception as exc:
            status = "FAIL"
            reason = f"Import/integrity failure: {exc}"
            stage = "import"
            if self.routing["mode"] == "COLLECTION":
                _destination(state, source, "FAIL", self.routing)
        _result_record(state, source, run_dir, status, reason, stage, output, manifest,
                       preserve_nonmanifold=self.preserve_nonmanifold,
                       row_index=self.row_offset + index,
                       normal_limit_deg=self.normal_limit_deg,
                       elapsed_seconds=time.perf_counter() - job["started"],
                       technical_reason=failure.get("error", "") if status == "FAIL" else "")
        if output is not None:
            from . import status_overlay

            status_overlay.refresh(state)
        self.completed += 1

    def cancel(self):
        self.cancelled = True
        deadline = time.monotonic() + 2.0
        for job in self.running.values():
            process = job["process"]
            if process.poll() is None:
                process.terminate()
        for job in self.running.values():
            process = job["process"]
            if process.poll() is None:
                try:
                    process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            job["log"].close()
        self.running.clear()
        rows = self.scene.lcw_cad_reconstruction.results
        for index in range(len(self.objects) - 1, -1, -1):
            row_index = self.row_offset + index
            if rows[row_index].status in {"PENDING", "RUNNING"}:
                rows.remove(row_index)
        state = self.scene.lcw_cad_reconstruction
        state.active_result = min(max(state.active_result, 0), max(len(rows) - 1, 0))
        state.progress = "Cancelled; completed results preserved"

    def step(self):
        state = self.scene.lcw_cad_reconstruction
        if self.cancelled:
            return False
        for index, job in sorted(self.running.items()):
            if job["process"].poll() is not None:
                self._finish_worker(index)
                self._progress()
                return True
            self._read_worker_progress(job)
        if self.next_index < len(self.objects) and len(self.running) < self.max_workers:
            index = self.next_index
            self.next_index += 1
            self._start_worker(index)
            self._progress()
            return True
        if not self.running and self.next_index >= len(self.objects):
            state.progress = f"Complete: {len(self.objects)} source object(s)"
            return False
        self._progress()
        return True
