from __future__ import annotations

import hashlib
import json
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import bmesh
import bpy
from bpy.props import StringProperty

from .audit import audit_snapshot
from .attributes import problem_face_indices
from .blender_seed import build_native_seed_edges, run_native_baselines
from .candidates import CandidateSettings, generate_candidates
from .confidence import calculate_confidence
from .jobs import AnalysisJob, ReconstructionJob
from .matching import solve_matching
from .models import (
    BatchReport,
    MatchingResult,
    MeshClassification,
    ObjectAnalysis,
    ObjectResult,
)
from .reconstruction import (
    create_diagnostic_attributes,
    create_output_copy,
    create_run_collection_tree,
    output_parent_for_scene,
    apply_matching_to_mesh,
    remove_empty_run_collection,
    remove_output_object,
    remove_run_collection,
    set_result_metadata,
    update_confidence_diagnostic,
)
from .regions import RegionSettings, build_triangle_regions
from .reporting import write_report_text, write_structured_text
from .scoring import scoring_weights_from_state
from .topology_snapshot import snapshot_object
from .validation import validate_existing_output, validate_reconstruction


def _state(context: bpy.types.Context):
    return context.scene.lcw_quad_reconstruction


def _mesh_objects(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    return sorted(
        (obj for obj in collection.all_objects if obj.type == "MESH"),
        key=lambda obj: (obj.name_full.casefold(), obj.data.name.casefold()),
    )


def _parent_depth(obj: bpy.types.Object) -> int:
    depth = 0
    parent = obj.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return depth


def _source_uuid(state, obj: bpy.types.Object) -> str:
    for item in state.source_identities:
        if item.source_object == obj:
            if not item.source_uuid:
                item.source_uuid = uuid.uuid4().hex
            return item.source_uuid
    item = state.source_identities.add()
    item.source_object = obj
    item.source_uuid = uuid.uuid4().hex
    return item.source_uuid


def _effective_protections(state) -> dict[str, bool]:
    if state.profile in {"STRICT", "ANALYZE_ONLY"}:
        return {"materials": True, "uv": True, "seams": True, "sharp_edges": True}
    return {
        "materials": True if state.profile == "BALANCED" else state.protect_materials,
        "uv": state.protect_uv,
        "seams": state.protect_seams,
        "sharp_edges": state.protect_sharp_edges,
    }


def _settings_payload(state) -> dict[str, object]:
    protections = _effective_protections(state)
    return {
        "profile": state.profile,
        "solver_backend": state.solver_backend,
        "protect_materials": protections["materials"],
        "protect_uv": protections["uv"],
        "protect_seams": protections["seams"],
        "protect_sharp_edges": protections["sharp_edges"],
        "process_open_meshes": state.process_open_meshes,
        "process_true_non_manifold_regions": state.process_true_non_manifold_regions,
        "preserve_existing_quads": state.preserve_existing_quads,
        "uv_tolerance": state.uv_tolerance,
        "area_tolerance": state.area_tolerance,
        "max_warp": state.max_warp,
        "exact_component_limit": state.exact_component_limit,
        "maximum_iterations": state.maximum_iterations,
        "parallel_core_processing": state.parallel_core_processing,
        "parallel_worker_count": state.parallel_worker_count,
        "parallel_triangle_threshold": state.parallel_triangle_threshold,
        "topology_influence": state.topology_influence,
        "create_face_diagnostics": state.create_face_diagnostics,
        "run_subdivision_validation": state.run_subdivision_validation,
        "scoring_weights": asdict(scoring_weights_from_state(state)),
    }


def _settings_hash(state) -> str:
    encoded = json.dumps(
        _settings_payload(state),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _region_settings(state) -> RegionSettings:
    protections = _effective_protections(state)
    return RegionSettings(
        protect_materials=protections["materials"],
        protect_uv=protections["uv"],
        protect_seams=protections["seams"],
        protect_sharp_edges=protections["sharp_edges"],
        process_open_meshes=state.process_open_meshes,
        process_true_non_manifold_regions=state.process_true_non_manifold_regions,
        uv_tolerance=state.uv_tolerance,
        area_tolerance=state.area_tolerance,
    )


def _populate_result(state, analysis: ObjectAnalysis) -> None:
    item = state.results.add()
    item.source_uuid = analysis.source_uuid
    item.source_object_name = analysis.source_object_name
    item.source_mesh_name = analysis.source_mesh_name
    item.fingerprint_unchanged = analysis.fingerprint_unchanged
    item.runtime_seconds = analysis.runtime_seconds
    if analysis.audit is None:
        item.classification = "UNSUPPORTED"
        item.status = "FAILED"
        item.warning_count = len(analysis.errors)
        item.details = " | ".join(analysis.errors)
        return
    item.classification = analysis.audit.classification.value
    item.status = "ANALYZED" if analysis.fingerprint_unchanged else "FAILED"
    item.triangle_count = analysis.audit.triangle_count
    item.quad_count = analysis.audit.quad_count
    item.ngon_count = analysis.audit.ngon_count
    item.region_count = len(analysis.regions)
    item.warning_count = len(analysis.audit.warnings) + len(analysis.errors)
    item.details = (
        f"{len(analysis.regions)} region(s), "
        f"{analysis.audit.boundary_edge_count} boundary, "
        f"{analysis.audit.true_non_manifold_edge_count} true non-manifold edge(s)"
    )


def _populate_reconstruction_result(state, result: ObjectResult) -> None:
    item = state.results.add()
    item.source_uuid = result.source_uuid
    item.source_object_name = result.source_object_name
    item.status = result.status
    item.runtime_seconds = result.runtime_seconds
    item.candidate_count = result.candidate_count
    if result.matching is not None:
        item.solver_backend = result.matching.backend
        item.solver_exact = result.matching.exact
        item.matching_pair_count = result.matching.cardinality
        item.unresolved_triangle_count = len(result.matching.unmatched_face_indices)
        denominator = result.matching.cardinality * 2 + len(result.matching.unmatched_face_indices)
        item.coverage = (result.matching.cardinality * 2 / denominator) if denominator else 1.0
    if result.validation is not None:
        item.validation_passed = result.validation.valid
        item.fingerprint_unchanged = result.validation.fingerprint_unchanged
    if result.confidence is not None:
        item.confidence_score = result.confidence.score
        item.confidence_label = result.confidence.label
        item.relaxation_count = result.confidence.relaxation_count
    if result.output_object_name:
        item.output_object = bpy.data.objects.get(result.output_object_name)
        if item.output_object is not None:
            item.source_mesh_name = item.output_object.data.name
            item.triangle_count = sum(
                len(face.vertices) == 3 for face in item.output_object.data.polygons
            )
            item.quad_count = sum(
                len(face.vertices) == 4 for face in item.output_object.data.polygons
            )
            item.ngon_count = sum(
                len(face.vertices) > 4 for face in item.output_object.data.polygons
            )
    item.details = result.error or (
        f"{item.matching_pair_count} pair(s), {item.unresolved_triangle_count} unresolved, "
        f"validation {'passed' if item.validation_passed else 'failed'}"
    )


def _native_seed_matching(regions, candidates, seed_edges) -> MatchingResult:
    selected = []
    matched_faces = set()
    seed_set = set(seed_edges)
    for candidate in sorted(candidates, key=lambda item: (item.cost, item.index)):
        if (
            candidate.hard_valid
            and candidate.dissolve_edge_index in seed_set
            and matched_faces.isdisjoint(candidate.face_indices)
        ):
            selected.append(candidate.index)
            matched_faces.update(candidate.face_indices)
    all_faces = tuple(sorted(face for region in regions for face in region.face_indices))
    return MatchingResult(
        backend="NATIVE_BASELINE",
        selected_candidate_indices=tuple(selected),
        unmatched_face_indices=tuple(face for face in all_faces if face not in matched_faces),
        cardinality=len(selected),
        total_cost=sum(candidates[index].cost for index in selected),
        exact=False,
        warnings=("Native Blender baseline is a comparison backend, not an optimal solver.",),
    )


def _matching_relaxation_flags(candidates, matching) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                flag
                for candidate_index in matching.selected_candidate_indices
                for flag in candidates[candidate_index].relaxation_flags
            }
        )
    )


def _collection_contains(root: bpy.types.Collection, target: bpy.types.Collection) -> bool:
    if root == target:
        return True
    return any(_collection_contains(child, target) for child in root.children)


class LCW_OT_quad_reconstruction_analyze(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_analyze"
    bl_label = "Analyze Quad Reconstruction"
    bl_description = (
        "Audit all mesh objects in the input collection, compare native hypotheses, "
        "and create a report without changing or duplicating mesh data"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(
            state
            and state.input_collection is not None
            and not state.active_run_id
        )

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        objects = _mesh_objects(state.input_collection)
        if not objects:
            self.report({"WARNING"}, "Input Collection contains no mesh objects.")
            return {"CANCELLED"}

        state.results.clear()
        state.job_status = "ANALYZING"
        state.job_message = "Analyzing collection..."
        state.progress = 0.0
        report_id = uuid.uuid4().hex
        batch_started = time.perf_counter()
        analyses = []
        batch_errors = []
        region_settings = _region_settings(state)
        protections = _effective_protections(state)

        for object_index, obj in enumerate(objects):
            object_started = time.perf_counter()
            source_uuid = _source_uuid(state, obj)
            try:
                snapshot_before = snapshot_object(obj, source_uuid)
                audit = audit_snapshot(snapshot_before, area_tolerance=state.area_tolerance)
                regions = build_triangle_regions(snapshot_before, region_settings)
                baselines = run_native_baselines(
                    obj.data,
                    protect_materials=protections["materials"],
                    protect_uv=protections["uv"],
                    protect_seams=protections["seams"],
                    protect_sharp_edges=protections["sharp_edges"],
                    topology_influence=state.topology_influence,
                )
                snapshot_after = snapshot_object(obj, source_uuid)
                fingerprint_unchanged = (
                    snapshot_before.fingerprint == snapshot_after.fingerprint
                )
                errors = () if fingerprint_unchanged else ("Source mesh fingerprint changed during analysis.",)
                analysis = ObjectAnalysis(
                    source_uuid=source_uuid,
                    source_object_name=obj.name,
                    source_mesh_name=obj.data.name,
                    fingerprint_before=snapshot_before.fingerprint,
                    fingerprint_after=snapshot_after.fingerprint,
                    fingerprint_unchanged=fingerprint_unchanged,
                    audit=audit,
                    regions=regions,
                    baselines=baselines,
                    runtime_seconds=time.perf_counter() - object_started,
                    errors=errors,
                )
            except Exception as exc:
                message = f"{obj.name}: {exc}"
                batch_errors.append(message)
                analysis = ObjectAnalysis(
                    source_uuid=source_uuid,
                    source_object_name=obj.name,
                    source_mesh_name=getattr(obj.data, "name", ""),
                    fingerprint_before="",
                    fingerprint_after="",
                    fingerprint_unchanged=False,
                    audit=None,
                    regions=(),
                    baselines=(),
                    runtime_seconds=time.perf_counter() - object_started,
                    errors=(str(exc),),
                )
            analyses.append(analysis)
            _populate_result(state, analysis)
            state.progress = (object_index + 1) / len(objects)

        report = BatchReport(
            report_id=report_id,
            settings_hash=_settings_hash(state),
            input_collection_name=state.input_collection.name,
            objects=tuple(analyses),
            runtime_seconds=time.perf_counter() - batch_started,
            errors=tuple(batch_errors),
            metadata={
                "mode": "ANALYZE_ONLY",
                "created_at": datetime.now(UTC).isoformat(),
                "mesh_outputs_created": "false",
            },
        )
        report_text = write_report_text(report)
        state.last_report_id = report_id
        state.last_report_text_name = report_text.name
        state.active_result_index = 0
        failed_count = sum(not item.fingerprint_unchanged for item in analyses)
        state.job_status = "FAILED" if failed_count == len(analyses) else "ANALYZED"
        state.job_message = (
            f"Analyzed {len(analyses)} object(s); {failed_count} failed. "
            f"Report: {report_text.name}"
        )
        self.report({"WARNING"} if failed_count else {"INFO"}, state.job_message)
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_reconstruct(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_reconstruct"
    bl_label = "Reconstruct Quad Topology"
    bl_description = (
        "Create independent output copies and safely dissolve globally matched triangle diagonals"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return (
            state is not None
            and state.input_collection is not None
            and state.profile != "ANALYZE_ONLY"
            and not state.active_run_id
        )

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        if state.output_collection is not None and _collection_contains(
            state.input_collection, state.output_collection
        ):
            self.report({"ERROR"}, "Output Collection cannot be inside the Input Collection.")
            return {"CANCELLED"}
        objects = _mesh_objects(state.input_collection)
        if not objects:
            self.report({"WARNING"}, "Input Collection contains no mesh objects.")
            return {"CANCELLED"}

        state.results.clear()
        state.job_status = "RECONSTRUCTING"
        state.job_message = "Reconstructing collection..."
        state.progress = 0.0
        run_id = uuid.uuid4().hex
        started = time.perf_counter()
        run_settings_hash = _settings_hash(state)
        output_parent = output_parent_for_scene(context.scene, state.output_collection)
        if _collection_contains(state.input_collection, output_parent):
            self.report({"ERROR"}, "Resolved output parent cannot be inside the Input Collection.")
            return {"CANCELLED"}
        run_collection, collection_map = create_run_collection_tree(
            state.input_collection,
            output_parent,
            run_id,
        )
        state.last_run_collection = run_collection
        pending = []
        object_results: list[ObjectResult] = []
        output_by_source: dict[int, bpy.types.Object] = {}
        region_settings = _region_settings(state)
        protections = _effective_protections(state)
        candidate_settings = CandidateSettings(
            profile=state.profile,
            protect_materials=protections["materials"],
            protect_uv=protections["uv"],
            protect_seams=protections["seams"],
            protect_sharp_edges=protections["sharp_edges"],
            geometry_tolerance=state.area_tolerance,
            uv_tolerance=state.uv_tolerance,
            max_warp=state.max_warp,
            weights=scoring_weights_from_state(state),
        )

        for object_index, source_obj in enumerate(objects):
            object_started = time.perf_counter()
            source_uuid = _source_uuid(state, source_obj)
            output_obj = None
            try:
                snapshot = snapshot_object(source_obj, source_uuid)
                audit = audit_snapshot(snapshot, area_tolerance=state.area_tolerance)
                if audit.classification == MeshClassification.UNSUPPORTED:
                    raise RuntimeError(
                        f"Skipped unsafe source classification: {audit.classification.value}."
                    )
                regions = build_triangle_regions(snapshot, region_settings)
                candidates = generate_candidates(snapshot, regions, candidate_settings)
                seed_edges = build_native_seed_edges(
                    source_obj.data,
                    protect_materials=protections["materials"],
                    protect_uv=protections["uv"],
                    protect_seams=protections["seams"],
                    protect_sharp_edges=protections["sharp_edges"],
                    topology_influence=state.topology_influence,
                )
                matching = (
                    _native_seed_matching(regions, candidates, seed_edges)
                    if state.solver_backend == "NATIVE_BASELINE"
                    else solve_matching(
                        state.solver_backend,
                        regions,
                        candidates,
                        seed_edge_indices=seed_edges,
                        exact_component_limit=state.exact_component_limit,
                        maximum_iterations=state.maximum_iterations,
                    )
                )
                source_before_apply = snapshot_object(source_obj, source_uuid)
                if source_before_apply.fingerprint != snapshot.fingerprint:
                    raise RuntimeError(
                        "Source fingerprint changed between analysis and reconstruction."
                    )
                output_obj = create_output_copy(
                    source_obj,
                    source_uuid,
                    run_id,
                    collection_map,
                    run_collection,
                )
                apply_matching_to_mesh(output_obj.data, snapshot, candidates, matching)
                if state.create_face_diagnostics:
                    create_diagnostic_attributes(output_obj.data, candidates, matching)
                output_by_source[source_obj.as_pointer()] = output_obj
                pending.append(
                    (source_obj, output_obj, snapshot, candidates, matching, object_started)
                )
            except Exception as exc:
                if state.debug_logging:
                    traceback.print_exc()
                if output_obj is not None:
                    remove_output_object(output_obj)
                object_results.append(
                    ObjectResult(
                        source_uuid=source_uuid,
                        source_object_name=source_obj.name,
                        output_object_name="",
                        status="FAILED",
                        candidate_count=0,
                        matching=None,
                        validation=None,
                        runtime_seconds=time.perf_counter() - object_started,
                        error=str(exc),
                    )
                )
            state.progress = 0.7 * (object_index + 1) / len(objects)

        validated_pending = []
        for validation_index, (
            source_obj,
            output_obj,
            snapshot,
            candidates,
            matching,
            object_started,
        ) in enumerate(pending):
            validation = validate_reconstruction(
                source_obj,
                snapshot,
                output_obj,
                candidates,
                matching,
                run_subdivision=state.run_subdivision_validation,
                area_tolerance=state.area_tolerance,
            )
            confidence = calculate_confidence(matching, candidates, validation)
            if not validation.valid:
                error = " | ".join(validation.errors)
                remove_output_object(output_obj)
                output_by_source.pop(source_obj.as_pointer(), None)
                object_results.append(
                    ObjectResult(
                        source_uuid=snapshot.source_uuid,
                        source_object_name=source_obj.name,
                        output_object_name="",
                        status="FAILED",
                        candidate_count=len(candidates),
                        matching=matching,
                        validation=validation,
                        runtime_seconds=time.perf_counter() - object_started,
                        confidence=confidence,
                        relaxation_flags=_matching_relaxation_flags(candidates, matching),
                        error=error,
                    )
                )
            else:
                update_confidence_diagnostic(output_obj.data, confidence)
                set_result_metadata(
                    output_obj,
                    profile=state.profile,
                    settings_hash=run_settings_hash,
                    source_fingerprint=snapshot.fingerprint,
                    report_id=run_id,
                    matching=matching,
                    confidence=confidence,
                    candidates=candidates,
                    runtime_seconds=time.perf_counter() - object_started,
                )
                validated_pending.append(
                    (
                        source_obj,
                        output_obj,
                        snapshot,
                        candidates,
                        matching,
                        validation,
                        confidence,
                        object_started,
                    )
                )
            state.progress = 0.7 + 0.2 * (validation_index + 1) / max(len(pending), 1)

        validated_pending.sort(
            key=lambda item: (_parent_depth(item[0]), item[0].name_full.casefold())
        )
        for parenting_index, (
            source_obj,
            output_obj,
            snapshot,
            candidates,
            matching,
            validation,
            confidence,
            object_started,
        ) in enumerate(validated_pending):
            try:
                world_matrix = source_obj.matrix_world.copy()
                generated_parent = (
                    output_by_source.get(source_obj.parent.as_pointer())
                    if source_obj.parent
                    else None
                )
                output_obj.parent = generated_parent or source_obj.parent
                output_obj.parent_type = source_obj.parent_type
                output_obj.parent_bone = source_obj.parent_bone
                output_obj.matrix_parent_inverse = source_obj.matrix_parent_inverse.copy()
                output_obj.matrix_world = world_matrix
                if output_obj.matrix_world != world_matrix:
                    raise RuntimeError("Output world transform changed while restoring parenting.")
                object_results.append(
                    ObjectResult(
                        source_uuid=snapshot.source_uuid,
                        source_object_name=source_obj.name,
                        output_object_name=output_obj.name,
                        status="RECONSTRUCTED",
                        candidate_count=len(candidates),
                        matching=matching,
                        validation=validation,
                        runtime_seconds=time.perf_counter() - object_started,
                        confidence=confidence,
                        relaxation_flags=_matching_relaxation_flags(candidates, matching),
                    )
                )
            except Exception as exc:
                if state.debug_logging:
                    traceback.print_exc()
                remove_output_object(output_obj)
                output_by_source.pop(source_obj.as_pointer(), None)
                object_results.append(
                    ObjectResult(
                        source_uuid=snapshot.source_uuid,
                        source_object_name=source_obj.name,
                        output_object_name="",
                        status="FAILED",
                        candidate_count=len(candidates),
                        matching=matching,
                        validation=validation,
                        runtime_seconds=time.perf_counter() - object_started,
                        confidence=None,
                        relaxation_flags=_matching_relaxation_flags(candidates, matching),
                        error=str(exc),
                    )
                )
            state.progress = 0.9 + 0.1 * (parenting_index + 1) / max(
                len(validated_pending), 1
            )

        object_results.sort(key=lambda item: (item.source_object_name.casefold(), item.source_uuid))
        for result in object_results:
            _populate_reconstruction_result(state, result)
        success_count = sum(result.status == "RECONSTRUCTED" for result in object_results)
        failure_count = len(object_results) - success_count
        if success_count == 0:
            remove_empty_run_collection(run_collection, run_id)
            state.last_run_collection = None
        payload = {
            "report_id": run_id,
            "mode": "RECONSTRUCT",
            "settings_hash": run_settings_hash,
            "settings": _settings_payload(state),
            "created_at": datetime.now(UTC).isoformat(),
            "runtime_seconds": time.perf_counter() - started,
            "objects": [asdict(result) for result in object_results],
        }
        report_text = write_structured_text("LCW_AIQ_Reconstruction_", run_id, payload)
        state.last_report_id = run_id
        state.last_report_text_name = report_text.name
        state.active_result_index = 0
        state.progress = 1.0
        state.job_status = "FAILED" if success_count == 0 else "RECONSTRUCTED"
        state.job_message = (
            f"Reconstructed {success_count} object(s); {failure_count} failed. "
            f"Report: {report_text.name}"
        )
        self.report({"WARNING"} if failure_count else {"INFO"}, state.job_message)
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_analyze_modal(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_analyze_modal"
    bl_label = "Analyze Quad Reconstruction"
    bl_description = (
        "Analyze in cooperative object batches without creating mesh outputs"
    )
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _job = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(
            state
            and state.input_collection is not None
            and not state.active_run_id
        )

    def _create_job(self, context: bpy.types.Context) -> AnalysisJob:
        state = _state(context)
        job = AnalysisJob(
            state,
            settings_payload=_settings_payload(state),
            protections=_effective_protections(state),
        )
        job.start()
        return job

    def _report_completion(self, state) -> None:
        level = {"WARNING"} if state.job_status in {"FAILED", "CANCELLED"} else {"INFO"}
        self.report(level, state.job_message)

    def execute(self, context: bpy.types.Context):
        try:
            self._job = self._create_job(context)
            stage = self._job.run_to_completion()
        except Exception as exc:
            state = _state(context)
            state.active_run_id = ""
            state.job_status = "FAILED"
            state.job_message = f"Quad reconstruction analysis failed to start: {exc}"
            self.report({"ERROR"}, state.job_message)
            return {"CANCELLED"}
        self._report_completion(_state(context))
        return {"CANCELLED"} if stage in {"FAILED", "CANCELLED"} else {"FINISHED"}

    def invoke(self, context: bpy.types.Context, _event):
        if context.window is None:
            return self.execute(context)
        try:
            self._job = self._create_job(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self._timer = context.window_manager.event_timer_add(
            0.01,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _remove_timer(self, context: bpy.types.Context) -> None:
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def modal(self, context: bpy.types.Context, event):
        if event.type == "ESC":
            self._job.state.cancel_requested = True
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        try:
            stage = self._job.step()
        except Exception as exc:
            if self._job is not None:
                self._job.cancel()
            self._remove_timer(context)
            self.report({"ERROR"}, f"Quad reconstruction analysis failed: {exc}")
            return {"CANCELLED"}
        if stage not in {"DONE", "FAILED", "CANCELLED"}:
            return {"RUNNING_MODAL"}
        self._remove_timer(context)
        self._report_completion(_state(context))
        return {"FINISHED"} if stage == "DONE" else {"CANCELLED"}

    def cancel(self, context: bpy.types.Context) -> None:
        if self._job is not None:
            self._job.cancel()
        self._remove_timer(context)


class LCW_OT_quad_reconstruction_reconstruct_modal(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_reconstruct_modal"
    bl_label = "Reconstruct Quad Topology"
    bl_description = (
        "Reconstruct in cooperative object and region batches so the UI remains responsive"
    )
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _job = None

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return (
            state is not None
            and state.input_collection is not None
            and state.profile != "ANALYZE_ONLY"
            and not state.active_run_id
        )

    def _create_job(self, context: bpy.types.Context) -> ReconstructionJob:
        state = _state(context)
        if state.output_collection is not None and _collection_contains(
            state.input_collection,
            state.output_collection,
        ):
            raise RuntimeError("Output Collection cannot be inside the Input Collection.")
        job = ReconstructionJob(
            context.scene,
            state,
            settings_payload=_settings_payload(state),
            protections=_effective_protections(state),
        )
        job.start()
        return job

    def _report_completion(self, state) -> None:
        level = {"INFO"}
        if state.job_status in {"FAILED", "CANCELLED"}:
            level = {"WARNING"}
        self.report(level, state.job_message)

    def execute(self, context: bpy.types.Context):
        try:
            self._job = self._create_job(context)
            stage = self._job.run_to_completion()
        except Exception as exc:
            state = _state(context)
            state.active_run_id = ""
            state.job_status = "FAILED"
            state.job_message = f"Quad reconstruction failed to start: {exc}"
            self.report({"ERROR"}, state.job_message)
            return {"CANCELLED"}
        self._report_completion(_state(context))
        return {"CANCELLED"} if stage in {"FAILED", "CANCELLED"} else {"FINISHED"}

    def invoke(self, context: bpy.types.Context, _event):
        if context.window is None:
            return self.execute(context)
        try:
            self._job = self._create_job(context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self._timer = context.window_manager.event_timer_add(
            0.01,
            window=context.window,
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _remove_timer(self, context: bpy.types.Context) -> None:
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    def modal(self, context: bpy.types.Context, event):
        if event.type == "ESC":
            self._job.request_cancel()
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        try:
            stage = self._job.step()
        except Exception as exc:
            if self._job is not None:
                self._job.request_cancel()
                self._job.cancel()
            self._remove_timer(context)
            self.report({"ERROR"}, f"Quad reconstruction failed: {exc}")
            return {"CANCELLED"}
        if stage not in {"DONE", "FAILED", "CANCELLED"}:
            return {"RUNNING_MODAL"}
        self._remove_timer(context)
        self._report_completion(_state(context))
        return {"FINISHED"} if stage == "DONE" else {"CANCELLED"}

    def cancel(self, context: bpy.types.Context) -> None:
        if self._job is not None:
            self._job.request_cancel()
            self._job.cancel()
        self._remove_timer(context)


class LCW_OT_quad_reconstruction_cancel(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_cancel"
    bl_label = "Cancel Quad Reconstruction"
    bl_description = "Request cooperative cancellation and cleanup of the active run"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(state and state.active_run_id)

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        state.cancel_requested = True
        state.progress_label = "Cancellation requested..."
        self.report({"INFO"}, "Cancellation requested; cleanup will run at the next job step.")
        return {"FINISHED"}


def _active_output_result(state):
    if not state.results:
        return None
    index = min(max(state.active_result_index, 0), len(state.results) - 1)
    item = state.results[index]
    return item if item.output_object is not None else None


class LCW_OT_quad_reconstruction_validate_outputs(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_validate_outputs"
    bl_label = "Validate Reconstruction Outputs"
    bl_description = "Run standalone safety validation on generated outputs"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(state and not state.active_run_id and state.results)

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        source_by_uuid = {
            item.source_uuid: item.source_object
            for item in state.source_identities
            if item.source_uuid and item.source_object is not None
        }
        payload = []
        passed = 0
        failed = 0
        for item in state.results:
            output_obj = item.output_object
            source_obj = source_by_uuid.get(item.source_uuid)
            if output_obj is None:
                continue
            if source_obj is None:
                item.validation_passed = False
                item.details = "Standalone validation failed: source object is unavailable."
                failed += 1
                payload.append(
                    {
                        "source_uuid": item.source_uuid,
                        "output_object": output_obj.name,
                        "valid": False,
                        "errors": ["Source object is unavailable."],
                    }
                )
                continue
            validation = validate_existing_output(
                source_obj,
                output_obj,
                run_subdivision=state.run_subdivision_validation,
            )
            item.validation_passed = validation.valid
            item.fingerprint_unchanged = validation.fingerprint_unchanged
            item.details = (
                "Standalone validation passed"
                if validation.valid
                else " | ".join(validation.errors)
            )
            passed += int(validation.valid)
            failed += int(not validation.valid)
            payload.append(
                {
                    "source_uuid": item.source_uuid,
                    "source_object": source_obj.name,
                    "output_object": output_obj.name,
                    **asdict(validation),
                }
            )
        report_id = uuid.uuid4().hex
        report = write_structured_text(
            "LCW_AIQ_Validation_",
            report_id,
            {
                "report_id": report_id,
                "mode": "VALIDATE_OUTPUTS",
                "created_at": datetime.now(UTC).isoformat(),
                "objects": payload,
            },
        )
        state.last_report_id = report_id
        state.last_report_text_name = report.name
        state.job_message = (
            f"Validated {passed + failed} output(s): {passed} passed, {failed} failed."
        )
        self.report({"WARNING"} if failed else {"INFO"}, state.job_message)
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_focus_output(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_focus_output"
    bl_label = "Focus Output"
    bl_description = "Select and frame the active reconstruction output"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(state and _active_output_result(state))

    def execute(self, context: bpy.types.Context):
        item = _active_output_result(_state(context))
        output_obj = item.output_object
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        output_obj.select_set(True)
        context.view_layer.objects.active = output_obj
        if context.area is not None and context.area.type == "VIEW_3D":
            try:
                bpy.ops.view3d.view_selected(use_all_regions=False)
            except RuntimeError:
                pass
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_select_problem_faces(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_select_problem_faces"
    bl_label = "Select Problem Faces"
    bl_description = "Enter Edit Mode and select faces marked by AIQ diagnostics"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(state and _active_output_result(state))

    def execute(self, context: bpy.types.Context):
        item = _active_output_result(_state(context))
        output_obj = item.output_object
        problem_indices = problem_face_indices(output_obj.data)
        if not problem_indices:
            self.report({"INFO"}, "The active output has no diagnostic problem faces.")
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        output_obj.select_set(True)
        context.view_layer.objects.active = output_obj
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(output_obj.data)
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            face.select = face.index in problem_indices
        bmesh.update_edit_mesh(output_obj.data, loop_triangles=False, destructive=False)
        self.report({"INFO"}, f"Selected {len(problem_indices)} diagnostic face(s).")
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_export_report(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_export_report"
    bl_label = "Export Reconstruction Report"
    bl_description = "Export the latest structured Text report as JSON"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(state and state.last_report_text_name)

    def invoke(self, context: bpy.types.Context, _event):
        state = _state(context)
        base = Path(bpy.data.filepath).parent if bpy.data.filepath else Path.home()
        self.filepath = str(base / f"{state.last_report_text_name}.json")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        text = bpy.data.texts.get(state.last_report_text_name)
        if text is None:
            self.report({"ERROR"}, "The latest Text report is no longer available.")
            return {"CANCELLED"}
        try:
            payload = json.loads(text.as_string())
            Path(self.filepath).write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except (OSError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not export report: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Report exported to {self.filepath}")
        return {"FINISHED"}


class LCW_OT_quad_reconstruction_clear_results(bpy.types.Operator):
    bl_idname = "lcw.quad_reconstruction_clear_results"
    bl_label = "Clear Generated Results"
    bl_description = "Delete only the latest internally identified reconstruction run"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        state = getattr(context.scene, "lcw_quad_reconstruction", None)
        return bool(
            state
            and not state.active_run_id
            and state.last_run_collection is not None
        )

    def invoke(self, context: bpy.types.Context, _event):
        return context.window_manager.invoke_confirm(self, _event)

    def execute(self, context: bpy.types.Context):
        state = _state(context)
        run_collection = state.last_run_collection
        run_id = str(run_collection.get("lcw_aiq_run_id", ""))
        try:
            remove_run_collection(run_collection, run_id)
        except RuntimeError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        state.results.clear()
        state.last_run_collection = None
        state.progress = 0.0
        state.progress_label = "Generated results cleared"
        state.job_status = "IDLE"
        state.job_message = "Generated reconstruction results were removed."
        self.report({"INFO"}, state.job_message)
        return {"FINISHED"}


CLASSES = (
    LCW_OT_quad_reconstruction_analyze,
    LCW_OT_quad_reconstruction_reconstruct,
    LCW_OT_quad_reconstruction_analyze_modal,
    LCW_OT_quad_reconstruction_reconstruct_modal,
    LCW_OT_quad_reconstruction_cancel,
    LCW_OT_quad_reconstruction_validate_outputs,
    LCW_OT_quad_reconstruction_focus_output,
    LCW_OT_quad_reconstruction_select_problem_faces,
    LCW_OT_quad_reconstruction_export_report,
    LCW_OT_quad_reconstruction_clear_results,
)
