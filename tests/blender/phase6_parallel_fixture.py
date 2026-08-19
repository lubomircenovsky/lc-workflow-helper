from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

import bpy


WORKSPACE_ROOT = r"E:\WORK\00_VIBE\Blender_automation_addon"
sys.path.insert(0, WORKSPACE_ROOT)

import LC_workflow_addon as addon
from LC_workflow_addon.quad_reconstruction.jobs import ReconstructionJob
from LC_workflow_addon.quad_reconstruction.operators import (
    _effective_protections,
    _settings_payload,
)
from LC_workflow_addon.quad_reconstruction.topology_snapshot import snapshot_object


def arguments():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--object", required=True)
    parser.add_argument("--parallel", choices=("true", "false"), required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cancel", action="store_true")
    return parser.parse_args(values)


try:
    args = arguments()
    addon.register()
    source_obj = bpy.data.objects[args.object]
    source_collection = bpy.data.collections.new("AIQ_Parallel_Fixture_Input")
    output_collection = bpy.data.collections.new("AIQ_Parallel_Fixture_Output")
    bpy.context.scene.collection.children.link(source_collection)
    bpy.context.scene.collection.children.link(output_collection)
    source_collection.objects.link(source_obj)
    fingerprint = snapshot_object(source_obj, "parallel-fixture").fingerprint

    state = bpy.context.scene.lcw_quad_reconstruction
    state.input_collection = source_collection
    state.output_collection = output_collection
    state.profile = "STRICT"
    state.solver_backend = "AUTO"
    state.run_subdivision_validation = False
    state.parallel_core_processing = args.parallel == "true"
    state.parallel_worker_count = args.workers
    state.parallel_triangle_threshold = 1000

    started = time.perf_counter()
    job = ReconstructionJob(
        bpy.context.scene,
        state,
        settings_payload=_settings_payload(state),
        protections=_effective_protections(state),
    )
    job.start()
    if args.cancel:
        job.step()
        task = job.current["parallel_task"]
        assert task is not None
        temp_dir = task.temp_dir
        job.cancel()
        assert job.stage == "CANCELLED"
        assert temp_dir is not None and not temp_dir.exists()
        assert snapshot_object(source_obj, "parallel-fixture").fingerprint == fingerprint
        print("LCW_PARALLEL_CANCEL_OK")
        sys.exit(0)
    assert job.run_to_completion() == "DONE"
    elapsed = time.perf_counter() - started
    report = json.loads(bpy.data.texts[state.last_report_text_name].as_string())
    object_report = report["objects"][0]
    assert object_report["status"] == "RECONSTRUCTED", json.dumps(
        object_report,
        indent=2,
        sort_keys=True,
    )
    assert snapshot_object(source_obj, "parallel-fixture").fingerprint == fingerprint
    print("LCW_PARALLEL_FIXTURE_OK")
    print(
        json.dumps(
            {
                "object": source_obj.name,
                "parallel": state.parallel_core_processing,
                "workers": args.workers,
                "elapsed_seconds": elapsed,
                "candidate_count": object_report["candidate_count"],
                "matching_pairs": object_report["matching"]["cardinality"],
                "phase_timings": dict(object_report["phase_timings"]),
                "fingerprint_unchanged": True,
            },
            indent=2,
            sort_keys=True,
        )
    )
    bpy.ops.lcw.quad_reconstruction_clear_results()
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    try:
        addon.unregister()
    except Exception:
        traceback.print_exc()
