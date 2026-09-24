"""Optional CAD benchmark: BLEND --python SCRIPT -- RUN_DIR WORKERS [priority]."""

import ctypes
import json
import sys
import time
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import LC_workflow_addon as addon
from LC_workflow_addon.cad_reconstruction import jobs
from LC_workflow_addon.cad_mesh_tool.mesh_io import fingerprint


class ProcessMemory(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def working_set(pid):
    if sys.platform != "win32":
        return 0
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        return 0
    try:
        counters = ProcessMemory()
        counters.cb = ctypes.sizeof(counters)
        if ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize
        return 0
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


args = sys.argv[sys.argv.index("--") + 1:]
run_root = Path(args[0])
workers = int(args[1])
addon.register()
try:
    scene = bpy.context.scene
    state = scene.lcw_cad_reconstruction
    state.mode = "SELECTED"
    state.concurrent_workers = workers
    state.epsilon_mm = .4
    state.normal_override = False
    for name in ("circular_holes", "perimeter_loops", "arcs", "outer_cylinders",
                 "background_cleanup", "straight_walls"):
        setattr(state, name, True)
    priority = scene.objects.get("Těleso1.027")
    assert priority is not None and priority.type == "MESH"
    objects = [priority] + sorted(
        (obj for obj in scene.objects if obj.type == "MESH" and obj != priority),
        key=lambda obj: obj.name)
    if len(args) > 2 and args[2] == "priority":
        objects = [priority]
    original = {obj.name: fingerprint(obj) for obj in objects}
    run_root.mkdir(parents=True, exist_ok=True)
    batch = jobs.CADBatch(bpy.context, objects, run_root, preserve_nonmanifold=True)
    start = time.perf_counter()
    max_running = 0
    peak_workers_mb = 0.0
    while batch.step():
        max_running = max(max_running, len(batch.running))
        used = sum(working_set(job["process"].pid) for job in batch.running.values())
        peak_workers_mb = max(peak_workers_mb, used / (1024 * 1024))
        time.sleep(.05)
    rows = list(state.results)[batch.row_offset:batch.row_offset + len(objects)]
    unchanged = all(fingerprint(obj) == original[obj.name] for obj in objects)
    result = {
        "workers": workers,
        "total_seconds": time.perf_counter() - start,
        "max_running": max_running,
        "peak_worker_working_set_mb": peak_workers_mb,
        "source_fingerprints_unchanged": unchanged,
        "objects": [{"name": row.source.name if row.source else "",
                     "status": row.status, "elapsed_seconds": row.elapsed_seconds,
                     "run_dir": row.run_dir, "reason": row.reason[:200]}
                    for row in rows],
    }
    (run_root / "benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("CAD_BATCH_BENCHMARK", json.dumps(result), flush=True)
    assert unchanged
finally:
    addon.unregister()
