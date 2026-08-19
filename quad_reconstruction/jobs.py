from __future__ import annotations

import time
import traceback
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

import bpy

from .audit import audit_snapshot
from .blender_seed import build_native_seed_edges, run_native_baselines
from .cache import CachedPreparation, PREPARATION_CACHE, preparation_cache_key
from .candidates import CandidateSettings, generate_candidates
from .confidence import calculate_confidence
from .matching import solve_matching
from .models import (
    BatchReport,
    MatchingResult,
    MeshClassification,
    ObjectAnalysis,
    ObjectResult,
)
from .parallel import ParallelCandidateTask
from .reconstruction import (
    apply_matching_to_mesh,
    create_diagnostic_attributes,
    create_output_copy,
    create_run_collection_tree,
    output_parent_for_scene,
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
from .validation import validate_reconstruction


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


def _native_seed_matching(regions, candidates, seed_edges) -> MatchingResult:
    region_indices = {region.index for region in regions}
    selected = []
    matched_faces = set()
    seed_set = set(seed_edges)
    for candidate in sorted(candidates, key=lambda item: (item.cost, item.index)):
        if (
            candidate.region_index in region_indices
            and candidate.hard_valid
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
        warnings=("Native Blender baseline is comparative, not an optimal solver.",),
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


def _combine_region_results(
    backend: str,
    regions,
    candidates,
    results: list[MatchingResult],
) -> MatchingResult:
    selected = tuple(
        sorted(
            candidate_index
            for result in results
            for candidate_index in result.selected_candidate_indices
        )
    )
    selected_faces = [
        face
        for candidate_index in selected
        for face in candidates[candidate_index].face_indices
    ]
    if len(selected_faces) != len(set(selected_faces)):
        raise RuntimeError("Region results contain overlapping matched triangle faces.")
    matched_faces = {
        face
        for candidate_index in selected
        for face in candidates[candidate_index].face_indices
    }
    all_faces = tuple(sorted(face for region in regions for face in region.face_indices))
    backends = {result.backend for result in results}
    result_backend = next(iter(backends)) if len(backends) == 1 else f"{backend}_MIXED"
    exact = all(result.exact for result in results)
    if not results:
        exact = backend in {"AUTO", "EXACT_BLOSSOM"}
        result_backend = "AUTO_EXACT_BLOSSOM" if backend == "AUTO" else backend
    return MatchingResult(
        backend=result_backend,
        selected_candidate_indices=selected,
        unmatched_face_indices=tuple(face for face in all_faces if face not in matched_faces),
        cardinality=len(selected),
        total_cost=sum(candidates[index].cost for index in selected),
        exact=exact,
        warnings=tuple(
            dict.fromkeys(warning for result in results for warning in result.warnings)
        ),
        hypothesis_margin=(
            sum(result.hypothesis_margin for result in results) / len(results)
            if results
            else 1.0
        ),
    )


def populate_reconstruction_result(state, result: ObjectResult) -> None:
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
        denominator = result.matching.cardinality * 2 + len(
            result.matching.unmatched_face_indices
        )
        item.coverage = (
            result.matching.cardinality * 2 / denominator if denominator else 1.0
        )
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


def populate_analysis_result(state, analysis: ObjectAnalysis) -> None:
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


class AnalysisJob:
    """Cooperative Analyze Only job; never creates object or mesh outputs."""

    def __init__(
        self,
        state,
        *,
        settings_payload: dict[str, object],
        protections: dict[str, bool],
    ) -> None:
        self.state = state
        self.settings_payload = settings_payload
        self.protections = protections
        self.objects = _mesh_objects(state.input_collection)
        self.report_id = uuid.uuid4().hex
        self.started = time.perf_counter()
        self.index = 0
        self.analyses: list[ObjectAnalysis] = []
        self.errors = []
        self.stage = "NEW"
        self.region_settings = RegionSettings(
            protect_materials=protections["materials"],
            protect_uv=protections["uv"],
            protect_seams=protections["seams"],
            protect_sharp_edges=protections["sharp_edges"],
            process_open_meshes=state.process_open_meshes,
            process_true_non_manifold_regions=state.process_true_non_manifold_regions,
            uv_tolerance=state.uv_tolerance,
            area_tolerance=state.area_tolerance,
        )

    def start(self) -> None:
        if not self.objects:
            raise RuntimeError("Input Collection contains no mesh objects.")
        self.state.results.clear()
        self.state.active_run_id = self.report_id
        self.state.cancel_requested = False
        self.state.job_status = "ANALYZING"
        self.state.job_message = "Analyzing collection..."
        self.state.progress = 0.0
        self.state.progress_label = "Preparing first object"
        self.stage = "ANALYZE"

    def _analyze_object(self) -> None:
        obj = self.objects[self.index]
        started = time.perf_counter()
        source_uuid = _source_uuid(self.state, obj)
        self.state.progress_label = f"Analyzing {obj.name}"
        try:
            before = snapshot_object(obj, source_uuid)
            audit = audit_snapshot(before, area_tolerance=self.state.area_tolerance)
            regions = build_triangle_regions(before, self.region_settings)
            baselines = run_native_baselines(
                obj.data,
                protect_materials=self.protections["materials"],
                protect_uv=self.protections["uv"],
                protect_seams=self.protections["seams"],
                protect_sharp_edges=self.protections["sharp_edges"],
                topology_influence=self.state.topology_influence,
            )
            after = snapshot_object(obj, source_uuid)
            unchanged = before.fingerprint == after.fingerprint
            errors = () if unchanged else (
                "Source mesh fingerprint changed during analysis.",
            )
            analysis = ObjectAnalysis(
                source_uuid=source_uuid,
                source_object_name=obj.name,
                source_mesh_name=obj.data.name,
                fingerprint_before=before.fingerprint,
                fingerprint_after=after.fingerprint,
                fingerprint_unchanged=unchanged,
                audit=audit,
                regions=regions,
                baselines=baselines,
                runtime_seconds=time.perf_counter() - started,
                errors=errors,
            )
        except Exception as exc:
            self.errors.append(f"{obj.name}: {exc}")
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
                runtime_seconds=time.perf_counter() - started,
                errors=(str(exc),),
            )
        self.analyses.append(analysis)
        populate_analysis_result(self.state, analysis)
        self.index += 1
        self.state.progress = self.index / len(self.objects)

    def _finalize(self) -> None:
        import hashlib
        import json

        settings_hash = hashlib.sha256(
            json.dumps(
                self.settings_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        report = BatchReport(
            report_id=self.report_id,
            settings_hash=settings_hash,
            input_collection_name=self.state.input_collection.name,
            objects=tuple(self.analyses),
            runtime_seconds=time.perf_counter() - self.started,
            errors=tuple(self.errors),
            metadata={
                "mode": "ANALYZE_ONLY",
                "created_at": datetime.now(UTC).isoformat(),
                "mesh_outputs_created": "false",
            },
        )
        text = write_report_text(report)
        failed = sum(not analysis.fingerprint_unchanged for analysis in self.analyses)
        self.state.last_report_id = self.report_id
        self.state.last_report_text_name = text.name
        self.state.active_result_index = 0
        self.state.active_run_id = ""
        self.state.progress = 1.0
        self.state.progress_label = "Analysis complete"
        self.state.job_status = "FAILED" if failed == len(self.analyses) else "ANALYZED"
        self.state.job_message = (
            f"Analyzed {len(self.analyses)} object(s); {failed} failed. Report: {text.name}"
        )
        self.stage = "DONE"

    def cancel(self) -> None:
        self.state.results.clear()
        self.state.active_run_id = ""
        self.state.progress = 0.0
        self.state.progress_label = "Analysis cancelled"
        self.state.job_status = "CANCELLED"
        self.state.job_message = "Quad reconstruction analysis cancelled; no mesh data created."
        self.stage = "CANCELLED"

    def step(self) -> str:
        if self.state.cancel_requested:
            self.cancel()
        elif self.stage == "ANALYZE" and self.index < len(self.objects):
            self._analyze_object()
        elif self.stage == "ANALYZE":
            self._finalize()
        return self.stage

    def run_to_completion(self) -> str:
        while self.stage not in {"DONE", "FAILED", "CANCELLED"}:
            self.step()
        return self.stage


class ReconstructionJob:
    """Cooperative main-thread reconstruction state machine."""

    def __init__(
        self,
        scene: bpy.types.Scene,
        state,
        *,
        settings_payload: dict[str, object],
        protections: dict[str, bool],
    ) -> None:
        self.scene = scene
        self.state = state
        self.settings_payload = settings_payload
        self.protections = protections
        self.objects = _mesh_objects(state.input_collection)
        self.run_id = uuid.uuid4().hex
        self.started = time.perf_counter()
        self.stage = "NEW"
        self.object_index = 0
        self.validation_index = 0
        self.parenting_index = 0
        self.current = None
        self.pending = []
        self.validated_pending = []
        self.object_results: list[ObjectResult] = []
        self.output_by_source: dict[int, bpy.types.Object] = {}
        self.run_collection = None
        self.collection_map = {}
        self.error = ""
        self.settings_hash = self._settings_hash()
        self.region_settings = RegionSettings(
            protect_materials=protections["materials"],
            protect_uv=protections["uv"],
            protect_seams=protections["seams"],
            protect_sharp_edges=protections["sharp_edges"],
            process_open_meshes=state.process_open_meshes,
            process_true_non_manifold_regions=state.process_true_non_manifold_regions,
            uv_tolerance=state.uv_tolerance,
        )
        self.candidate_settings = CandidateSettings(
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

    def _settings_hash(self) -> str:
        import hashlib
        import json

        encoded = json.dumps(
            self.settings_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def start(self) -> None:
        if not self.objects:
            raise RuntimeError("Input Collection contains no mesh objects.")
        output_parent = output_parent_for_scene(self.scene, self.state.output_collection)
        self.run_collection, self.collection_map = create_run_collection_tree(
            self.state.input_collection,
            output_parent,
            self.run_id,
        )
        self.state.results.clear()
        self.state.last_run_collection = self.run_collection
        self.state.active_run_id = self.run_id
        self.state.cancel_requested = False
        self.state.job_status = "RECONSTRUCTING"
        self.state.job_message = "Reconstructing collection..."
        self.state.progress = 0.0
        self.state.progress_label = "Preparing first object"
        self.stage = "PROCESS"

    def request_cancel(self) -> None:
        self.state.cancel_requested = True

    def _record_failure(
        self,
        source_obj,
        source_uuid,
        started,
        exc,
        candidate_count=0,
        timings=None,
    ):
        if self.state.debug_logging:
            traceback.print_exc()
        self.object_results.append(
            ObjectResult(
                source_uuid=source_uuid,
                source_object_name=source_obj.name,
                output_object_name="",
                status="FAILED",
                candidate_count=candidate_count,
                matching=None,
                validation=None,
                runtime_seconds=time.perf_counter() - started,
                error=str(exc),
                phase_timings=tuple(sorted((timings or {}).items())),
            )
        )

    def _prepare_object(self) -> None:
        source_obj = self.objects[self.object_index]
        object_started = time.perf_counter()
        source_uuid = _source_uuid(self.state, source_obj)
        self.state.progress_label = f"Preparing {source_obj.name}"
        timings = {}
        try:
            phase_started = time.perf_counter()
            snapshot = snapshot_object(source_obj, source_uuid)
            timings["snapshot"] = time.perf_counter() - phase_started
            cache_key = preparation_cache_key(
                snapshot.fingerprint,
                self.state.area_tolerance,
                self.region_settings,
                self.candidate_settings,
            )
            phase_started = time.perf_counter()
            cached = PREPARATION_CACHE.get(cache_key)
            if cached is None:
                audit = audit_snapshot(snapshot, area_tolerance=self.state.area_tolerance)
                regions = build_triangle_regions(snapshot, self.region_settings)
                if audit.classification == MeshClassification.UNSUPPORTED:
                    raise RuntimeError(
                        f"Skipped unsafe source classification: {audit.classification.value}."
                    )
                use_parallel = (
                    self.state.parallel_core_processing
                    and audit.triangle_count >= self.state.parallel_triangle_threshold
                    and bool(regions)
                )
                parallel_task = None
                if use_parallel:
                    parallel_task = ParallelCandidateTask(
                        snapshot,
                        regions,
                        self.candidate_settings,
                        self.state.parallel_worker_count,
                    )
                    parallel_task.start()
                    candidates = None
                    timings["parallel_workers"] = float(len(parallel_task.processes))
                else:
                    candidates = generate_candidates(
                        snapshot,
                        regions,
                        self.candidate_settings,
                    )
                    PREPARATION_CACHE.put(
                        cache_key,
                        CachedPreparation(audit, regions, candidates),
                    )
                    timings["parallel_workers"] = 0.0
                timings["preparation_cache_hit"] = 0.0
            else:
                audit = cached.audit
                regions = cached.regions
                candidates = cached.candidates
                parallel_task = None
                timings["preparation_cache_hit"] = 1.0
            timings["audit_candidates"] = time.perf_counter() - phase_started
            phase_started = time.perf_counter()
            seed_edges = build_native_seed_edges(
                source_obj.data,
                protect_materials=self.protections["materials"],
                protect_uv=self.protections["uv"],
                protect_seams=self.protections["seams"],
                protect_sharp_edges=self.protections["sharp_edges"],
                topology_influence=self.state.topology_influence,
            )
            timings["native_seed"] = time.perf_counter() - phase_started
            self.current = {
                "source_obj": source_obj,
                "source_uuid": source_uuid,
                "object_started": object_started,
                "snapshot": snapshot,
                "regions": regions,
                "candidates": candidates,
                "seed_edges": seed_edges,
                "region_index": 0,
                "region_results": [],
                "timings": timings,
                "parallel_task": parallel_task,
                "cache_key": cache_key,
                "parallel_started": time.perf_counter(),
            }
        except Exception as exc:
            self._record_failure(
                source_obj,
                source_uuid,
                object_started,
                exc,
                timings=timings,
            )
            self.object_index += 1

    def _poll_parallel_candidates(self) -> None:
        current = self.current
        task = current["parallel_task"]
        if not task.done():
            self.state.progress_label = (
                f"Generating candidates for {current['source_obj'].name} "
                f"({len(task.processes)} worker(s))"
            )
            return
        try:
            candidates = task.result()
        finally:
            task.cleanup()
        current["candidates"] = candidates
        current["parallel_task"] = None
        current["timings"]["audit_candidates"] += (
            time.perf_counter() - current["parallel_started"]
        )
        PREPARATION_CACHE.put(
            current["cache_key"],
            CachedPreparation(
                audit_snapshot(
                    current["snapshot"],
                    area_tolerance=self.state.area_tolerance,
                ),
                current["regions"],
                candidates,
            ),
        )

    def _match_region(self) -> None:
        current = self.current
        region = current["regions"][current["region_index"]]
        self.state.progress_label = (
            f"Matching {current['source_obj'].name}: region "
            f"{current['region_index'] + 1}/{len(current['regions'])}"
        )
        phase_started = time.perf_counter()
        if self.state.solver_backend == "NATIVE_BASELINE":
            result = _native_seed_matching(
                (region,),
                current["candidates"],
                current["seed_edges"],
            )
        else:
            result = solve_matching(
                self.state.solver_backend,
                (region,),
                current["candidates"],
                seed_edge_indices=current["seed_edges"],
                exact_component_limit=self.state.exact_component_limit,
                maximum_iterations=self.state.maximum_iterations,
            )
        current["region_results"].append(result)
        current["region_index"] += 1
        current["timings"]["matching"] = (
            current["timings"].get("matching", 0.0)
            + time.perf_counter()
            - phase_started
        )

    def _apply_current(self) -> None:
        current = self.current
        source_obj = current["source_obj"]
        output_obj = None
        phase_started = time.perf_counter()
        try:
            matching = _combine_region_results(
                self.state.solver_backend,
                current["regions"],
                current["candidates"],
                current["region_results"],
            )
            if (
                snapshot_object(source_obj, current["source_uuid"]).fingerprint
                != current["snapshot"].fingerprint
            ):
                raise RuntimeError(
                    "Source fingerprint changed between analysis and reconstruction."
                )
            output_obj = create_output_copy(
                source_obj,
                current["source_uuid"],
                self.run_id,
                self.collection_map,
                self.run_collection,
            )
            apply_matching_to_mesh(
                output_obj.data,
                current["snapshot"],
                current["candidates"],
                matching,
            )
            if self.state.create_face_diagnostics:
                create_diagnostic_attributes(
                    output_obj.data,
                    current["candidates"],
                    matching,
                )
            self.output_by_source[source_obj.as_pointer()] = output_obj
            self.pending.append(
                (
                    source_obj,
                    output_obj,
                    current["snapshot"],
                    current["candidates"],
                    matching,
                    current["object_started"],
                    current["timings"],
                )
            )
        except Exception as exc:
            if output_obj is not None:
                remove_output_object(output_obj)
            self._record_failure(
                source_obj,
                current["source_uuid"],
                current["object_started"],
                exc,
                len(current["candidates"]),
                current["timings"],
            )
        current["timings"]["application"] = time.perf_counter() - phase_started
        self.current = None
        self.object_index += 1

    def _process_step(self) -> None:
        if self.object_index >= len(self.objects):
            self.stage = "VALIDATE"
            self.state.progress = 0.7
            self.state.progress_label = "Validating generated outputs"
            return
        if self.current is None:
            self._prepare_object()
        elif self.current["parallel_task"] is not None:
            try:
                self._poll_parallel_candidates()
            except Exception as exc:
                task = self.current.get("parallel_task")
                if task is not None:
                    task.cancel()
                self._record_failure(
                    self.current["source_obj"],
                    self.current["source_uuid"],
                    self.current["object_started"],
                    exc,
                    timings=self.current["timings"],
                )
                self.current = None
                self.object_index += 1
        elif self.current["region_index"] < len(self.current["regions"]):
            try:
                self._match_region()
            except Exception as exc:
                self._record_failure(
                    self.current["source_obj"],
                    self.current["source_uuid"],
                    self.current["object_started"],
                    exc,
                    len(self.current["candidates"]),
                )
                self.current = None
                self.object_index += 1
        else:
            self._apply_current()
        object_fraction = self.object_index
        if self.current is not None:
            region_count = max(len(self.current["regions"]), 1)
            object_fraction += 0.25 + 0.5 * self.current["region_index"] / region_count
        self.state.progress = 0.7 * object_fraction / len(self.objects)

    def _validate_step(self) -> None:
        if self.validation_index >= len(self.pending):
            self.validated_pending.sort(
                key=lambda item: (_parent_depth(item[0]), item[0].name_full.casefold())
            )
            self.stage = "PARENT"
            self.state.progress = 0.9
            self.state.progress_label = "Restoring output hierarchy"
            return
        (
            source_obj,
            output_obj,
            snapshot,
            candidates,
            matching,
            object_started,
            timings,
        ) = self.pending[self.validation_index]
        self.state.progress_label = f"Validating {source_obj.name}"
        phase_started = time.perf_counter()
        try:
            validation = validate_reconstruction(
                source_obj,
                snapshot,
                output_obj,
                candidates,
                matching,
                run_subdivision=self.state.run_subdivision_validation,
                area_tolerance=self.state.area_tolerance,
            )
            timings["validation"] = time.perf_counter() - phase_started
            confidence = calculate_confidence(matching, candidates, validation)
        except Exception as exc:
            timings["validation"] = time.perf_counter() - phase_started
            if self.state.debug_logging:
                traceback.print_exc()
            remove_output_object(output_obj)
            self.output_by_source.pop(source_obj.as_pointer(), None)
            self.object_results.append(
                ObjectResult(
                    source_uuid=snapshot.source_uuid,
                    source_object_name=source_obj.name,
                    output_object_name="",
                    status="FAILED",
                    candidate_count=len(candidates),
                    matching=matching,
                    validation=None,
                    runtime_seconds=time.perf_counter() - object_started,
                    relaxation_flags=_matching_relaxation_flags(candidates, matching),
                    error=str(exc),
                    phase_timings=tuple(sorted(timings.items())),
                )
            )
            self.validation_index += 1
            return
        if not validation.valid:
            remove_output_object(output_obj)
            self.output_by_source.pop(source_obj.as_pointer(), None)
            self.object_results.append(
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
                    error=" | ".join(validation.errors),
                    phase_timings=tuple(sorted(timings.items())),
                )
            )
        else:
            update_confidence_diagnostic(output_obj.data, confidence)
            set_result_metadata(
                output_obj,
                profile=self.state.profile,
                settings_hash=self.settings_hash,
                source_fingerprint=snapshot.fingerprint,
                report_id=self.run_id,
                matching=matching,
                confidence=confidence,
                candidates=candidates,
                runtime_seconds=time.perf_counter() - object_started,
            )
            self.validated_pending.append(
                (
                    source_obj,
                    output_obj,
                    snapshot,
                    candidates,
                    matching,
                    validation,
                    confidence,
                    object_started,
                    timings,
                )
            )
        self.validation_index += 1
        self.state.progress = 0.7 + 0.2 * self.validation_index / max(
            len(self.pending), 1
        )

    def _parent_step(self) -> None:
        if self.parenting_index >= len(self.validated_pending):
            self.stage = "FINALIZE"
            self.state.progress = 0.98
            self.state.progress_label = "Writing reconstruction report"
            return
        (
            source_obj,
            output_obj,
            snapshot,
            candidates,
            matching,
            validation,
            confidence,
            object_started,
            timings,
        ) = self.validated_pending[self.parenting_index]
        self.state.progress_label = f"Restoring hierarchy for {source_obj.name}"
        try:
            world_matrix = source_obj.matrix_world.copy()
            generated_parent = (
                self.output_by_source.get(source_obj.parent.as_pointer())
                if source_obj.parent
                else None
            )
            output_obj.parent = generated_parent or source_obj.parent
            output_obj.parent_type = source_obj.parent_type
            output_obj.parent_bone = source_obj.parent_bone
            output_obj.matrix_parent_inverse = source_obj.matrix_parent_inverse.copy()
            output_obj.matrix_world = world_matrix
            if output_obj.matrix_world != world_matrix:
                raise RuntimeError(
                    "Output world transform changed while restoring parenting."
                )
            self.object_results.append(
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
                    phase_timings=tuple(sorted(timings.items())),
                )
            )
        except Exception as exc:
            if self.state.debug_logging:
                traceback.print_exc()
            remove_output_object(output_obj)
            self.output_by_source.pop(source_obj.as_pointer(), None)
            self.object_results.append(
                ObjectResult(
                    source_uuid=snapshot.source_uuid,
                    source_object_name=source_obj.name,
                    output_object_name="",
                    status="FAILED",
                    candidate_count=len(candidates),
                    matching=matching,
                    validation=validation,
                    runtime_seconds=time.perf_counter() - object_started,
                    error=str(exc),
                    phase_timings=tuple(sorted(timings.items())),
                )
            )
        self.parenting_index += 1
        self.state.progress = 0.9 + 0.08 * self.parenting_index / max(
            len(self.validated_pending), 1
        )

    def _finalize(self) -> None:
        self.object_results.sort(
            key=lambda item: (item.source_object_name.casefold(), item.source_uuid)
        )
        self.state.results.clear()
        for result in self.object_results:
            populate_reconstruction_result(self.state, result)
        success_count = sum(
            result.status == "RECONSTRUCTED" for result in self.object_results
        )
        failure_count = len(self.object_results) - success_count
        if success_count == 0:
            remove_empty_run_collection(self.run_collection, self.run_id)
            self.state.last_run_collection = None
        payload = {
            "report_id": self.run_id,
            "mode": "RECONSTRUCT",
            "settings_hash": self.settings_hash,
            "settings": self.settings_payload,
            "created_at": datetime.now(UTC).isoformat(),
            "runtime_seconds": time.perf_counter() - self.started,
            "preparation_cache": PREPARATION_CACHE.info(),
            "objects": [asdict(result) for result in self.object_results],
        }
        report_text = write_structured_text(
            "LCW_AIQ_Reconstruction_",
            self.run_id,
            payload,
        )
        self.state.last_report_id = self.run_id
        self.state.last_report_text_name = report_text.name
        self.state.active_result_index = 0
        self.state.progress = 1.0
        self.state.progress_label = "Complete"
        self.state.active_run_id = ""
        self.state.job_status = "FAILED" if success_count == 0 else "RECONSTRUCTED"
        self.state.job_message = (
            f"Reconstructed {success_count} object(s); {failure_count} failed. "
            f"Report: {report_text.name}"
        )
        self.stage = "DONE"

    def cancel(self) -> None:
        try:
            if self.current is not None and self.current.get("parallel_task") is not None:
                self.current["parallel_task"].cancel()
            if self.run_collection is not None:
                remove_run_collection(self.run_collection, self.run_id)
            self.state.results.clear()
            self.state.last_run_collection = None
            self.state.active_run_id = ""
            self.state.progress = 0.0
            self.state.progress_label = "Cancelled and cleaned up"
            self.state.job_status = "CANCELLED"
            self.state.job_message = "Quad reconstruction cancelled; generated data removed."
            self.stage = "CANCELLED"
        except Exception as exc:
            self.error = str(exc)
            self.state.active_run_id = ""
            self.state.job_status = "FAILED"
            self.state.job_message = f"Cancellation cleanup failed: {exc}"
            self.stage = "FAILED"

    def step(self) -> str:
        if self.state.cancel_requested:
            self.cancel()
            return self.stage
        if self.stage == "PROCESS":
            self._process_step()
        elif self.stage == "VALIDATE":
            self._validate_step()
        elif self.stage == "PARENT":
            self._parent_step()
        elif self.stage == "FINALIZE":
            self._finalize()
        return self.stage

    def run_to_completion(self) -> str:
        while self.stage not in {"DONE", "FAILED", "CANCELLED"}:
            self.step()
            if (
                self.current is not None
                and self.current.get("parallel_task") is not None
                and not self.current["parallel_task"].done()
            ):
                time.sleep(0.01)
        return self.stage
